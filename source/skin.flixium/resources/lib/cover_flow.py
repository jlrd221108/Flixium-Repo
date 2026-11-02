"""Cached cover-derived colour fields; Kodi owns all per-frame animation."""
import colorsys
import hashlib
import json
import math
import os
import tempfile
import time

import xbmcvfs

PREFIX = "flixium.playback.flow."
FIELDS = ("base", "layer1", "layer2", "layer3", "mode", "ready")
MODES = ("Static", "Gentle", "Full")
VERSION = "cover-flow-1"
BASE_SIZE = (480, 270)
LAYER_SIZE = (384, 384)


def motion_mode(get_label):
    mode = get_label("Skin.String(Flixium.MusicBackgroundMotion)")
    if mode in MODES:
        return mode
    quality = get_label("Skin.String(Flixium.LyricsQuality)")
    return "Static" if quality == "Low" else "Full" if quality == "High" else "Gentle"


def palette_from(image):
    from PIL import Image
    sample = image.convert("RGBA")
    sample.thumbnail((96, 96), getattr(Image, "Resampling", Image).LANCZOS)
    backing = Image.new("RGBA", sample.size, (24, 24, 28, 255))
    sample = Image.alpha_composite(backing, sample).convert("RGB")
    quantized = sample.quantize(colors=12, method=getattr(Image, "Quantize", Image).MEDIANCUT)
    colors = quantized.getpalette()
    total = sample.width * sample.height
    choices = [(count / total, tuple(colors[index * 3:index * 3 + 3]))
               for count, index in quantized.getcolors() if count / total >= .01]
    choices.sort(key=lambda item: item[0] * (.65 + colorsys.rgb_to_hsv(*(c / 255 for c in item[1]))[1]), reverse=True)
    selected = [choices.pop(0)[1]]
    while choices and len(selected) < 4:
        def score(item):
            distance = min(sum((a - b) ** 2 for a, b in zip(item[1], kept)) for kept in selected)
            return distance * math.sqrt(item[0])
        choice = max(choices, key=score)
        selected.append(choice[1])
        choices.remove(choice)
    while len(selected) < 4:
        selected.append(selected[0])
    toned = []
    for color in selected:
        hue, saturation, value = colorsys.rgb_to_hsv(*(c / 255 for c in color))
        toned.append(tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, min(.88, saturation * 1.08), .15 + .57 * value)))
    return toned


def base_field(palette):
    from PIL import Image
    image = Image.new("RGB", (160, 90))
    centers = ((-.1, .1), (.9, -.1), (.2, 1.1), (1.1, .9))
    pixels = []
    for y in range(image.height):
        for x in range(image.width):
            u, v = x / (image.width - 1), y / (image.height - 1)
            weights = [1 / (1 + 5 * ((u - a) ** 2 + (v - b) ** 2)) ** 2 for a, b in centers]
            total = sum(weights)
            # The right-hand lyric area stays darker even when the cover is white.
            shade = .87 - .25 * u
            pixels.append(tuple(round(sum(color[c] * weight for color, weight in zip(palette, weights)) / total * shade)
                                for c in range(3)))
    image.putdata(pixels)
    return image.resize(BASE_SIZE, getattr(Image, "Resampling", Image).LANCZOS)


def floating_field(palette, index):
    from PIL import Image
    size = 128
    image = Image.new("RGBA", (size, size))
    first, second = palette[(index + 1) % 4], palette[(index + 2) % 4]
    pixels = []
    for y in range(size):
        for x in range(size):
            u, v = x / (size - 1), y / (size - 1)
            a = math.exp(-(((u - .37) / .24) ** 2 + ((v - .42) / .28) ** 2))
            b = .7 * math.exp(-(((u - .66) / .23) ** 2 + ((v - .64) / .25) ** 2))
            total = a + b
            rgb = tuple(round((first[c] * a + second[c] * b) / max(.00001, total)) for c in range(3))
            # Smooth alpha falls to transparent at the texture's edges.
            edge = max(0, min(1, min(u, v, 1 - u, 1 - v) * 12))
            pixels.append(rgb + (round(min(175, total * 155) * edge),))
    image.putdata(pixels)
    return image.resize(LAYER_SIZE, getattr(Image, "Resampling", Image).LANCZOS)


def atomic_image(image, path):
    handle, temporary = tempfile.mkstemp(prefix="flow-", suffix=".tmp", dir=os.path.dirname(path))
    os.close(handle)
    try:
        image.save(temporary, "PNG", compress_level=1)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def valid_image(path, size, mode):
    from PIL import Image
    try:
        with Image.open(path) as image:
            if image.size != size or image.mode != mode:
                return False
            image.verify()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def cached_fields(directory, identity, image_path, count):
    """Read the artwork only on a new palette; mode changes reuse its metadata."""
    from PIL import Image
    os.makedirs(directory, exist_ok=True)
    digest = hashlib.sha256((VERSION + repr(identity)).encode("utf-8")).hexdigest()
    stem = os.path.join(directory, digest)
    metadata = stem + ".json"
    try:
        with open(metadata, encoding="utf-8") as handle:
            palette = json.load(handle)
        if (not isinstance(palette, list) or len(palette) != 4
                or any(not isinstance(c, list) or len(c) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in c) for c in palette)):
            raise ValueError("Invalid cached palette")
    except (OSError, ValueError, TypeError):
        with Image.open(image_path) as image:
            palette = palette_from(image)
        handle, temporary = tempfile.mkstemp(prefix="flow-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(palette, output)
            os.replace(temporary, metadata)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    base = stem + "-base.png"
    if not valid_image(base, BASE_SIZE, "RGB"):
        atomic_image(base_field(palette), base)
    layers = []
    for index in range(count):
        path = stem + "-layer{}.png".format(index + 1)
        if not valid_image(path, LAYER_SIZE, "RGBA"):
            atomic_image(floating_field(palette, index), path)
        layers.append(path)
    os.utime(metadata, None)
    prune(directory, digest)
    return base, layers


def prune(directory, current):
    """Keep 24 cover palettes; only remove files in this dedicated cache."""
    try:
        manifests = sorted((item for item in os.scandir(directory) if item.name.endswith(".json")),
                           key=lambda item: item.stat().st_mtime, reverse=True)
        for manifest in manifests[24:]:
            digest = manifest.name[:-5]
            if digest == current or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                continue
            for suffix in (".json", "-base.png", "-layer1.png", "-layer2.png", "-layer3.png"):
                try:
                    os.remove(os.path.join(directory, digest + suffix))
                except OSError:
                    pass
    except OSError:
        pass


class CoverFlow:
    def __init__(self, window, log=None):
        self.window = window
        self.log = log
        self.key = None
        self.mode = "Gentle"
        self.next_mode_check = 0
        self.retry_at = 0
        self.published = {}
        self.attempt_identity = None

    def publish(self, field, value):
        if self.published.get(field) != value:
            self.window.setProperty(PREFIX + field, value)
            self.published[field] = value

    def update(self, image_path, identity, get_label, is_current=lambda: True):
        now = time.monotonic()
        if now >= self.next_mode_check:
            self.mode = motion_mode(get_label)
            self.next_mode_check = now + .5
        self.publish("mode", self.mode)
        if identity != self.attempt_identity:
            self.retry_at = 0
            self.attempt_identity = identity
        count = {"Static": 0, "Gentle": 2, "Full": 3}[self.mode]
        key = (identity, count)
        if key == self.key or now < self.retry_at:
            return bool(self.published.get("ready"))
        try:
            directory = xbmcvfs.translatePath("special://temp/flixium-cover-flow/")
            base, layers = cached_fields(directory, identity, image_path, count)
            if not is_current():
                return False
            self.publish("base", base)
            for index in range(3):
                self.publish("layer" + str(index + 1), layers[index] if index < len(layers) else "")
            self.publish("ready", "true")
            self.key, self.retry_at = key, 0
            return True
        except Exception as error:
            # Keep the old soft fields/blur while a missing derivative is retried.
            self.retry_at = now + 5
            if self.log:
                self.log(str(error))
            return False

    def clear(self):
        for field in FIELDS:
            if field in self.published or self.window.getProperty(PREFIX + field):
                self.window.clearProperty(PREFIX + field)
        self.published.clear()
        self.key, self.retry_at, self.next_mode_check = None, 0, 0
        self.attempt_identity = None
