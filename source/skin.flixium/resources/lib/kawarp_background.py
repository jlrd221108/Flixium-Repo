"""Kawarp 1.3.1's spatial warp, cached as native true-colour animations.

Shader math adapted from @kawarp/core (MIT, Copyright 2026 Better Lyrics).
See resources/licenses/kawarp-MIT.txt. No browser or per-frame Python work.
"""
import hashlib
import json
import math
import os
import shutil
import threading
import time
import tempfile
import io
import struct
import zlib
import traceback
from functools import lru_cache

import xbmcvfs
from cover_flow import PREFIX, atomic_image, motion_mode, valid_image

VERSION = "kawarp-1.3.1-apng-2"
SIZE = (480, 270)
PROFILES = {"Gentle": ((160, 90), 30, 300), "Full": ((160, 90), 60, 600)}
FIELDS = ("base", "sequence", "mode", "ready", "layer1", "layer2", "layer3")


def simplex(x, y):
    """Scalar port of Kawarp's GLSL snoise(vec2), including its permutation."""
    skew = (x + y) * .366025403784439
    ix, iy = math.floor(x + skew), math.floor(y + skew)
    unskew = (ix + iy) * .211324865405187
    x0, y0 = x - ix + unskew, y - iy + unskew
    dx, dy = (1, 0) if x0 > y0 else (0, 1)
    corners = ((x0, y0, 0, 0),
               (x0 - dx + .211324865405187, y0 - dy + .211324865405187, dx, dy),
               (x0 - .577350269189626, y0 - .577350269189626, 1, 1))
    ix, iy = ix % 289, iy % 289
    def permute(v):
        return ((v * 34 + 1) * v) % 289
    result = 0
    for a, b, ox, oy in corners:
        p = permute(permute(iy + oy) + ix + ox)
        gradient = 2 * ((p * .024390243902439) % 1) - 1
        h = abs(gradient) - .5
        a0 = gradient - math.floor(gradient + .5)
        m = max(.5 - a * a - b * b, 0) ** 4
        m *= 1.79284291400159 - .85373472095314 * (a0 * a0 + h * h)
        result += m * (a0 * a + h * b)
    return 130 * result


def warp_uv(u, v, seconds):
    t = seconds * .05
    radius = min(1, math.hypot(u - .5, v - .5) / .7)
    weight = 1 - radius * radius * (3 - 2 * radius)
    n1 = simplex(u * .35 + t, v * .35 + t * .7)
    n2 = simplex(u * .35 - t * .8 + 50, v * .35 + t * .5 + 50)
    n3 = simplex(u * .9 + t * 1.2 + 100, v * .9 - t)
    n4 = simplex(u * .9 - t, v * .9 + t * 1.1 + 100)
    return (max(0, min(1, u + (n1 * .65 + n3 * .35) * weight)),
            max(0, min(1, v + (n2 * .65 + n4 * .35) * weight)))


def kawase(image):
    """Eight four-tap passes, offsets 0.5 .. 7.5, clamped at the edges."""
    from PIL import Image, ImageChops
    image = image.convert("RGBA")
    backing = Image.new("RGBA", image.size, (0, 0, 0, 255))
    image = Image.alpha_composite(backing, image).convert("RGB").resize((128, 128), Image.BILINEAR)
    # Padding implements CLAMP_TO_EDGE instead of wrapping opposite edges.
    for index in range(8):
        pad = 9
        padded = image.resize((146, 146), Image.BILINEAR)
        padded.paste(image, (pad, pad))
        padded.paste(image.crop((0, 0, 1, 128)).resize((pad, 128)), (0, pad))
        padded.paste(image.crop((127, 0, 128, 128)).resize((pad, 128)), (137, pad))
        padded.paste(padded.crop((0, pad, 146, pad + 1)).resize((146, pad)), (0, 0))
        padded.paste(padded.crop((0, 136, 146, 137)).resize((146, pad)), (0, 137))
        offset = index + .5
        taps = [padded.transform((128, 128), Image.AFFINE, (1, 0, pad + x * offset, 0, 1, pad + y * offset), Image.BILINEAR)
                for x, y in ((-1, -1), (1, -1), (-1, 1), (1, 1))]
        image = ImageChops.blend(ImageChops.blend(taps[0], taps[1], .5), ImageChops.blend(taps[2], taps[3], .5), .5)
    return image


@lru_cache(maxsize=2)
def vignette_mask(size):
    from PIL import Image
    width, height = size
    mask = Image.new("L", size)
    mask.putdata([round(255 * (1 - .3 * ((x / width - .5) ** 2 + (y / height - .5) ** 2)))
                  for y in range(height) for x in range(width)])
    return mask.convert("RGB")


def render(source, seconds, size=SIZE):
    from PIL import Image, ImageChops, ImageEnhance
    width, height = size
    columns, rows = 32, 18
    vertices = {}
    for y in range(rows + 1):
        for x in range(columns + 1):
            # GL image textures have a bottom-up UV axis; Pillow uses top-down.
            u, v = warp_uv(x / columns, 1 - y / rows, seconds)
            # Pixel centres stay inside the last texel, matching GL CLAMP_TO_EDGE.
            vertices[x, y] = (.5 + u * 127, .5 + (1 - v) * 127)
    mesh = []
    for y in range(rows):
        for x in range(columns):
            box = (round(x * width / columns), round(y * height / rows),
                   round((x + 1) * width / columns), round((y + 1) * height / rows))
            quad = sum((vertices[a, b] for a, b in ((x, y), (x, y + 1), (x + 1, y + 1), (x + 1, y))), ())
            mesh.append((box, quad))
    image = source.transform(size, Image.MESH, mesh, Image.BILINEAR)
    image = ImageChops.multiply(image, vignette_mask(size))
    image = ImageEnhance.Color(image).enhance(1.5)  # Kawarp output shader.
    image = ImageEnhance.Color(image).enhance(2.5)  # Spicy Lyrics page CSS.
    return ImageEnhance.Brightness(image).enhance(.65)


class Cancelled(Exception):
    pass


def animation_valid(path, size, count):
    try:
        # Kodi's Pillow cannot read APNG metadata either. Validate the container
        # directly; Kodi's FFmpeg texture decoder handles actual playback.
        with open(path, "rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            dimensions, declared, controls, sequence = None, None, 0, 0
            while True:
                prefix = handle.read(8)
                if len(prefix) != 8:
                    return False
                length, kind = struct.unpack(">I4s", prefix)
                if length > 64 * 1024 * 1024:
                    return False
                data, crc = handle.read(length), handle.read(4)
                if len(data) != length or len(crc) != 4:
                    return False
                if struct.unpack(">I", crc)[0] != zlib.crc32(kind + data) & 0xffffffff:
                    return False
                if kind == b"IHDR":
                    dimensions = struct.unpack_from(">II", data)
                elif kind == b"acTL":
                    declared, loops = struct.unpack(">II", data)
                    if declared != count or loops != 0:
                        return False
                elif kind in (b"fcTL", b"fdAT"):
                    if struct.unpack_from(">I", data)[0] != sequence:
                        return False
                    sequence += 1
                    if kind == b"fcTL":
                        controls += 1
                elif kind == b"IEND":
                    return dimensions == size and controls == declared == count
    except (OSError, ValueError, struct.error):
        return False


def save_animation(source, path, profile, cancelled):
    """Actual deformation frames, no fades. APNG avoids GIF palette flicker."""
    size, fps, count = PROFILES[profile]
    half = count // 2
    frames = []
    for index in range(half + 1):
        if cancelled():
            raise Cancelled()
        seconds = 4 * (1 - math.cos(math.pi * index / half))
        frames.append(render(source, seconds, size))
    # Forward/backward path closes with matching velocity and no duplicated end frame.
    ordered = frames + frames[-2:0:-1]
    handle, temporary = tempfile.mkstemp(prefix="motion-", suffix=".tmp", dir=os.path.dirname(path))
    os.close(handle)
    try:
        # APNG has millisecond timing rather than GIF's coarse centisecond delays.
        # Kodi resets its animation timer to the current GUI tick. Alternating
        # 33/34 ms delays would alternate between two and three ticks at 60 Hz.
        # A small margin below 1/fps lets each frame occupy a consistent tick count.
        delay = round(1000 / fps) - 1
        write_apng(ordered, temporary, count, delay, cancelled)
        if cancelled():
            raise Cancelled()
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def write_apng(frames, path, count, delay, cancelled=lambda: False):
    """APNG framing around ordinary PNGs, compatible with Kodi's Pillow 5.1.

    Older Pillow has a PNG encoder but no SAVE_ALL['PNG']. Encoding each RGB
    frame normally and framing its IDAT chunks avoids that unsupported API.
    """
    def chunk(output, kind, data):
        output.write(struct.pack(">I", len(data)))
        output.write(kind + data)
        output.write(struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    with open(path, "wb") as output:
        output.write(b"\x89PNG\r\n\x1a\n")
        sequence, written = 0, 0
        dimensions = None
        for index, frame in enumerate(frames):
            if cancelled():
                raise Cancelled()
            buffer = io.BytesIO()
            frame.convert("RGB").save(buffer, "PNG", compress_level=1)
            encoded = buffer.getvalue()
            offset, payloads, header = 8, [], None
            while offset < len(encoded):
                length = struct.unpack_from(">I", encoded, offset)[0]
                kind = encoded[offset + 4:offset + 8]
                data = encoded[offset + 8:offset + 8 + length]
                if kind == b"IHDR":
                    header = data
                elif kind == b"IDAT":
                    payloads.append(data)
                offset += length + 12
            if not header or not payloads:
                raise ValueError("PNG frame has no image data")
            width, height = struct.unpack_from(">II", header)
            if index == 0:
                dimensions = (width, height)
                chunk(output, b"IHDR", header)
                chunk(output, b"acTL", struct.pack(">II", count, 0))
            elif dimensions != (width, height):
                raise ValueError("APNG frame dimensions changed")
            control = struct.pack(">IIIIIHHBB", sequence, width, height, 0, 0, delay, 1000, 0, 0)
            chunk(output, b"fcTL", control)
            sequence += 1
            for data in payloads:
                if index == 0:
                    chunk(output, b"IDAT", data)
                else:
                    chunk(output, b"fdAT", struct.pack(">I", sequence) + data)
                    sequence += 1
            written += 1
        if written != count:
            raise ValueError("APNG frame count mismatch")
        chunk(output, b"IEND", b"")


def cached_animation(directory, identity, image_path, animated, load_source=None, cancelled=lambda: False):
    """Publish only a complete animation; never expose a partially written file."""
    from PIL import Image
    digest = hashlib.sha256((VERSION + repr(identity)).encode("utf-8")).hexdigest()
    folder = os.path.join(directory, digest)
    os.makedirs(folder, exist_ok=True)
    source_path, base = os.path.join(folder, "source.png"), os.path.join(folder, "base.png")
    if not valid_image(source_path, (128, 128), "RGB"):
        image = load_source() if load_source else Image.open(image_path)
        if image is None:
            raise ValueError("Cover is unavailable")
        try:
            atomic_image(kawase(image), source_path)
        finally:
            image.close()
    with Image.open(source_path) as image:
        source = image.copy()
    if not valid_image(base, SIZE, "RGB"):
        atomic_image(render(source, 0), base)
    if cancelled():
        return None
    marker = os.path.join(folder, "complete.json")
    sequence = ""
    if animated:
        profile = animated if animated in PROFILES else "Full"
        size, _, count = PROFILES[profile]
        sequence = os.path.join(folder, profile.lower() + ".apng")
        if not animation_valid(sequence, size, count):
            try:
                save_animation(source, sequence, profile, cancelled)
            except Cancelled:
                return None
    with open(marker, "w", encoding="utf-8") as handle:
        json.dump({"version": VERSION, "animated": animated}, handle)
    prune(directory, digest)
    return base, sequence if animated else ""


def prune(directory, current):
    # Dedicated cache, bounded to eight albums. Reject all unexpected names.
    try:
        folders = [item for item in os.scandir(directory) if item.is_dir(follow_symlinks=False)
                   and len(item.name) == 64 and all(c in "0123456789abcdef" for c in item.name)]
        folders.sort(key=lambda item: os.path.getmtime(os.path.join(item.path, "complete.json"))
                     if os.path.isfile(os.path.join(item.path, "complete.json")) else 0, reverse=True)
        for item in folders[8:]:
            if item.name != current:
                shutil.rmtree(item.path)
    except OSError:
        pass


class KawarpBackground:
    def __init__(self, window, log=None):
        self.window, self.log = window, log
        self.published = {}
        self.mode, self.next_mode_check = "Gentle", 0
        self.key, self.desired, self.retry_at = None, None, 0
        self.thread, self.result = None, None
        self.cancel = threading.Event()

    def publish(self, field, value):
        if self.published.get(field) != value:
            self.window.setProperty(PREFIX + field, value)
            self.published[field] = value

    def update(self, image_path, identity, get_label, is_current=lambda: True, load_source=None):
        now = time.monotonic()
        if now >= self.next_mode_check:
            self.mode = motion_mode(get_label)
            self.next_mode_check = now + .5
            self.publish("mode", self.mode)
        key = (identity, self.mode if self.mode != "Static" else False)
        if key != self.desired:
            self.cancel.set()
            self.desired, self.retry_at = key, 0
        if self.thread is not None and not self.thread.is_alive():
            result, self.result, self.thread = self.result, None, None
            if result and result[0] == key and is_current():
                _, paths, error = result
                if error:
                    self.retry_at = now + 5
                    if self.log:
                        self.log(str(error))
                elif paths:
                    self.publish("base", paths[0])
                    self.publish("sequence", paths[1])
                    self.publish("ready", "true")
                    self.key = key
        if self.key == key or self.thread is not None or now < self.retry_at:
            return self.key == key
        self.cancel = threading.Event()
        cancel = self.cancel
        # Translate on Kodi's service thread. The worker never writes GUI properties.
        try:
            directory = xbmcvfs.translatePath("special://temp/flixium-kawarp/")
        except Exception as error:
            self.retry_at = now + 5
            if self.log:
                self.log(str(error))
            return False
        def work():
            try:
                paths = cached_animation(directory, identity, image_path, key[1], load_source, cancel.is_set)
                self.result = (key, paths, None)
            except Exception as error:
                self.result = (key, None, "{}: {}\n{}".format(type(error).__name__, error, traceback.format_exc()))
        self.thread = threading.Thread(target=work, name="FlixiumKawarp", daemon=True)
        self.thread.start()
        return False

    def clear(self):
        self.cancel.set()
        self.desired, self.key = None, None
        self.retry_at, self.next_mode_check = 0, 0
        for field in FIELDS:
            if field in self.published or self.window.getProperty(PREFIX + field):
                self.window.clearProperty(PREFIX + field)
        self.published.clear()
