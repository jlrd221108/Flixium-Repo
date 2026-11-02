"""Cached glyph atlases and a clock bridge to the native lyric renderer.

No animation images are generated: masks/glow are prepared on content changes,
then the GPU evaluates word fill and choreography from the shared song clock.
"""
from collections import OrderedDict
import mmap
import os
import re
import struct
import time
from contextlib import contextmanager
from functools import wraps


def bridge_write(method):
    """POSIX file locking supplies ordering on ARM as well as mutual exclusion."""
    @wraps(method)
    def locked(self, *args, **kwargs):
        if self.windows:
            return method(self, *args, **kwargs)
        if method.__name__ != "clear" and time.monotonic() < self.retry:
            return False
        try:
            if self.mapping is None:
                if method.__name__ == "clear" or (method.__name__ == "update" and not self.enabled()):
                    return method(self, *args, **kwargs)
                self.open()
            with self.transaction():
                return method(self, *args, **kwargs)
        except Exception as error:
            self.log("{}: {}".format(type(error).__name__, error))
            self.owned = False
            self.published = False
            self.window.clearProperty("flixium.lyrics.native.active")
            self.retry = time.monotonic() + 5
            return False
    return locked


CAPACITY = 24 * 1024 * 1024
HEADER = 128
ROWS = 23
MAX_SPRITES = 512
MAGIC = b"FLXLYR02"
FLAGS = ("words", "glow", "motion", "letters", "smooth", "ripple")


class NativeLyrics:
    def __init__(self, window, words, enabled=lambda: False, log=lambda _: None):
        self.window, self.words, self.enabled, self.log = window, words, enabled, log
        self.mapping = None
        self.key = None
        self.sequence = 0
        self.clock_sequence = 0
        self.owned = False
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.retry = 0
        self.prepared_at = 0
        self.published = None
        self.windows = os.name == "nt"
        self.channel_fd = None
        self.channel_path = None
        self.lock_depth = 0
        self.async_prepare = not self.windows
        self.executor = None
        self.pending = None
        self.requested = None

    def prepare(self, key, row_lines, backgrounds, identity, transition, options):
        if not self.async_prepare:
            return self.scene(row_lines, backgrounds, int(identity[2]), transition, options)
        if self.requested is None or self.requested[0] != key:
            self.requested = (key, dict(row_lines), dict(backgrounds), int(identity[2]), transition, options)
        if self.pending is not None:
            pending_key, future = self.pending
            if not future.done():
                return None
            self.pending = None
            data = future.result()
            if pending_key == key:
                return data
        if self.executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="flixium-glyphs")
        # One running job, no growing queue; obsolete results are not published.
        self.pending = (key, self.executor.submit(self.scene, *self.requested[1:]))
        return None

    @contextmanager
    def transaction(self):
        if self.windows or self.channel_fd is None:
            yield
            return
        import fcntl
        if self.lock_depth == 0:
            fcntl.flock(self.channel_fd, fcntl.LOCK_EX)
        self.lock_depth += 1
        try:
            yield
        finally:
            self.lock_depth -= 1
            if self.lock_depth == 0:
                fcntl.flock(self.channel_fd, fcntl.LOCK_UN)

    def open(self):
        if self.mapping is not None:
            return
        if self.windows:
            import ctypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetTickCount64.restype = ctypes.c_ulonglong
            self.ticks = kernel.GetTickCount64
            self.mapping = mmap.mmap(-1, CAPACITY, tagname="Local\\FlixiumLyrics-v2-" + str(os.getpid()))
        else:
            import stat
            import xbmcvfs
            self.ticks = lambda: time.monotonic_ns() // 1000000
            self.channel_path = xbmcvfs.translatePath("special://temp/flixium-lyrics-v2-{}.map".format(os.getpid()))
            fd = os.open(self.channel_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode) or (hasattr(os, "getuid") and details.st_uid != os.getuid()):
                os.close(fd)
                raise OSError("Unsafe lyric shared-memory file")
            self.channel_fd = fd
            try:
                with self.transaction():
                    os.ftruncate(fd, CAPACITY)
                    self.mapping = mmap.mmap(fd, CAPACITY, access=mmap.ACCESS_WRITE)
            except Exception:
                os.close(fd)
                self.channel_fd = None
                raise
        with self.transaction():
            self.mapping[:HEADER] = bytes(HEADER)
            struct.pack_into("<8sII", self.mapping, 0, MAGIC, 2, CAPACITY)
            struct.pack_into("<I", self.mapping, 68, int.from_bytes(os.urandom(4), "little"))

    def sprites(self, line, backing=False, letters=True, simple=False, words=True, glow=True):
        from PIL import Image, ImageFilter
        text = line[1].replace("[", "［").replace("]", "］")
        key = (text, tuple(line.words), getattr(line, "align", "center"), backing, line[0], line.end, letters, simple, words, glow)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        size, height = (27, 72) if backing else (36, 180)
        mask, spans, crop = self.words.word_layout(text, line.words, key[2], size, height)
        # Motion groups rejoin timed syllables while fill cues retain their timing.
        if line.words and words:
            plan = self.words.motion_layout(line, text, key[2], size, height, letter_mode="simple" if simple else "spicy")
        else:
            bounds = mask.getbbox() or (0, 0, 1, 1)
            plan = [(None, False, bounds, ())]
        result = []
        tokens = list(re.finditer(r"\S+", text))
        for cue, last, box, glyphs in plan:
            group = next((token.start() + 1 for token in tokens
                          if cue and token.start() <= cue.first < token.end()), 0)
            pieces = [(bounds, index, count) for bounds, index, count in glyphs] if glyphs and letters else [(box, -1, 0)]
            for bounds, index, count in pieces:
                pad = 24
                width, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
                alpha = Image.new("L", (width + 2 * pad, h + 2 * pad))
                alpha.paste(mask.crop(bounds), (pad, pad))
                empty = Image.new("L", alpha.size) if not glow else None
                image = Image.merge("RGBA", (alpha,
                    alpha.filter(ImageFilter.GaussianBlur(2)) if glow else empty,
                    alpha.filter(ImageFilter.GaussianBlur(5)) if glow else empty,
                    alpha.filter(ImageFilter.GaussianBlur(8)) if glow else empty))
                fills = []
                for original, boxes in (zip(line.words, spans) if words else ()):
                    for left, top, right, bottom in boxes:
                        if bottom > bounds[1] and top < bounds[3] and right > bounds[0] and left < bounds[2]:
                            fills.append((original.start, original.end, left - bounds[0] + pad, right - bounds[0] + pad))
                if len(fills) > 16:
                    raise ValueError("Native glyph exceeds 16 fill segments")
                # Coordinates remain in the established 978px logical row plane.
                result.append((image, crop[0] + bounds[0] - pad, crop[1] + bounds[1] - pad,
                               (cue.start + (.021 if simple and count else 0)) if cue else line[0],
                               (cue.end + (.04 if simple else -.25) if count else cue.end) if cue else (line.end or line[0] + 1),
                               index, count, last, fills, crop[0] + (box[0] + box[2]) / 2,
                               crop[1] + (box[1] + box[3]) / 2, group))
        self.cache[key] = result
        self.cache_bytes += sum(part[0].width * part[0].height * 4 for part in result)
        while len(self.cache) > 12 or self.cache_bytes > 8 * 1024 * 1024:
            _, old = self.cache.popitem(last=False)
            self.cache_bytes -= sum(part[0].width * part[0].height * 4 for part in old)
        return result

    def scene(self, row_lines, backgrounds, anchor, transition, options):
        from PIL import Image, ImageDraw
        from lyrics_timed import LyricLine
        names = ("before2", "before1", "current", "after1", "after2")
        # Ordinary LRC rows are (start, text) tuples without TTML attributes.
        # Their highlight lasts until the next timestamp, with no invented cues.
        row_lines = dict(row_lines)
        for index, name in enumerate(names):
            line, active = row_lines.get(name, (None, False))
            if line is not None and not hasattr(line, "words"):
                following = next((row_lines[key][0][0] for key in names[index + 1:]
                                  if row_lines.get(key, (None, False))[0] is not None), None)
                row_lines[name] = (LyricLine(line[0], line[1], end=following), active)
        tiles = []
        for offset, name in enumerate(names):
            line, _ = row_lines.get(name, (None, False))
            if line is None:
                continue
            groups = [(line, False)]
            if backgrounds.get(name) is not None:
                groups.append((backgrounds[name], True))
            for item, backing in groups:
                is_dot = getattr(item, "kind", "") == "interlude"
                if is_dot:
                    alpha = Image.new("L", (72, 72))
                    # Spicy's dot is a bullet glyph at 1.3em, not a 30px disc.
                    # Use the skin's typeface so its ink scales with lyric text.
                    from PIL import ImageFont
                    font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "..", "..", "fonts", "SpotifyMixUI-Bold.ttf"), 47)
                    ImageDraw.Draw(alpha).text((0, 0), "\u2022", font=font, fill=255)
                    ink = alpha.crop(alpha.getbbox())
                    alpha = Image.new("L", (72, 72))
                    alpha.paste(ink, ((72 - ink.width) // 2, (72 - ink.height) // 2))
                    from PIL import ImageFilter
                    image = Image.merge("RGBA", (alpha, alpha.filter(ImageFilter.GaussianBlur(2)),
                                                  alpha.filter(ImageFilter.GaussianBlur(5)), alpha.filter(ImageFilter.GaussianBlur(8))))
                    parts = [(image, center - 786 - 36, 54, item[0], item.end, i, 0, False, [], 1275 - 786, 90, 0)
                             for i, center in enumerate((1255, 1275, 1295))]
                else:
                    parts = self.sprites(item, backing, options.words and options.letters, options.simple,
                                         words=options.words, glow=options.glow)
                for image, x, y, start, end, glyph, count, last, fills, pivot_x, pivot_y, group in parts:
                    meta = [0.] * (ROWS * 4)
                    top = 189 + offset * 131 + (116 if backing else 0)
                    meta[0:4] = [786 + x, top + y, image.width, image.height]
                    meta[8:12] = [786 + x + image.width / 2, top + y + image.height / 2, start, end]
                    meta[12:16] = [glyph, count, float(last), float(backing)]
                    meta[16:20] = [item[0], (item.end + (.35 if is_dot else 0)) if item.end is not None else 1e9, offset - 2, float(backing)]
                    meta[20:24] = [len(fills), float(is_dot), glyph if is_dot else group, float(backgrounds.get(name) is not None)]
                    for i, fill in enumerate(fills):
                        meta[24 + i * 4:28 + i * 4] = fill
                    meta[88:92] = [786 + pivot_x, top + pivot_y, 36,
                                   float(not getattr(item, "words", ()) and not is_dot)]
                    tiles.append((image, meta))
        if len(tiles) > MAX_SPRITES:
            raise ValueError("Native scene exceeds sprite budget")
        width, x, y, shelf = 2048, 0, 0, 0
        placements = []
        for image, meta in tiles:
            if image.width > width:
                raise ValueError("Native glyph exceeds atlas width")
            if x + image.width > width:
                x, y, shelf = 0, y + shelf, 0
            placements.append((image, meta, x, y))
            x += image.width
            shelf = max(shelf, image.height)
        height = max(1, y + shelf)
        if height > 2048:
            raise ValueError("Native scene exceeds atlas memory budget")
        atlas = Image.new("RGBA", (width, height))
        for image, meta, left, top in placements:
            atlas.paste(image, (left, top))
            meta[4:8] = [left / width, top / height, image.width / width, image.height / height]
        metadata = b"".join(struct.pack("<4f", *meta[row * 4:row * 4 + 4])
                            for row in range(ROWS) for _, meta in tiles)
        pixels = atlas.tobytes()
        header = struct.pack("<IIIIiiII", width, height, len(tiles), ROWS, anchor,
                             int(transition == "forward"), len(metadata), len(pixels))
        return header + metadata + pixels

    @bridge_write
    def set_background(self, enabled):
        if time.monotonic() < self.retry:
            return
        try:
            self.open()
            # Separate from the lyric clock, so a background-only scene also works.
            struct.pack_into("<I", self.mapping, 72, 1 if enabled else 2)
        except Exception as error:
            self.log("{}: {}".format(type(error).__name__, error))
            self.retry = time.monotonic() + 5

    def update(self, identity, row_lines, backgrounds, position, options, transition, paused, seeking=False):
        if not self.enabled():
            self.clear()
            return False
        if time.monotonic() < self.retry:
            return False
        try:
            self.open()
            key = (identity, tuple((name, bg[1] if bg else "", tuple(bg.words) if bg else ()) for name, bg in backgrounds.items()))
            # Image/layout preparation must never hold the native clock lock.
            data = self.prepare(key, row_lines, backgrounds, identity, transition, options) if key != self.key else None
            with self.transaction():
                return self._publish(key, data, position, options, paused, seeking)
        except Exception as error:
            self.log("{}: {}".format(type(error).__name__, error))
            self.clear()
            self.retry = time.monotonic() + 5
            return False

    def _publish(self, key, data, position, options, paused, seeking):
            if data is not None:
                if len(data) + HEADER > CAPACITY:
                    raise ValueError("Native scene exceeds shared-memory capacity")
                self.sequence += 2
                struct.pack_into("<I", self.mapping, 16, self.sequence - 1)
                self.mapping[HEADER:HEADER + len(data)] = data
                struct.pack_into("<I", self.mapping, 24, len(data))
                struct.pack_into("<I", self.mapping, 16, self.sequence)
                self.key, self.prepared_at = key, self.ticks()
            now = self.ticks()
            ack = struct.unpack_from("<I", self.mapping, 28)[0]
            heartbeat = struct.unpack_from("<Q", self.mapping, 32)[0]
            status = struct.unpack_from("<I", self.mapping, 64)[0]
            live = status == 1 and 0 <= now - heartbeat < 750
            self.owned = live and (ack == self.sequence or self.owned)
            flags = 1 | (2 if paused else 0) | (4 if seeking else 0) | (512 if self.owned else 0) | (1024 if options.simple else 0)
            for i, field in enumerate(FLAGS):
                if getattr(options, field) and (field not in ("motion", "letters") or options.words):
                    flags |= 8 << i
            self.clock_sequence += 2
            struct.pack_into("<I", self.mapping, 20, self.clock_sequence - 1)
            struct.pack_into("<QdII", self.mapping, 40, now, position, flags, options.fps)
            struct.pack_into("<I", self.mapping, 20, self.clock_sequence)
            if self.published != self.owned:
                if self.owned:
                    self.window.setProperty("flixium.lyrics.native.active", "true")
                else:
                    self.window.clearProperty("flixium.lyrics.native.active")
                self.published = self.owned
            # Plain Kodi text remains visible during warmup; avoid PNG generation.
            return live or now - self.prepared_at < 3000

    @bridge_write
    def clear(self):
        if self.mapping is not None:
            struct.pack_into("<I", self.mapping, 56, 0)
        self.owned = False
        self.key = None
        if self.published is not False:
            self.window.clearProperty("flixium.lyrics.native.active")
            self.published = False

    def close(self):
        if self.executor is not None:
            self.executor.shutdown(wait=True)
            self.executor = None
            self.pending = None
            self.requested = None
        self.clear()
        if self.mapping is not None:
            self.mapping.close()
            self.mapping = None
        if self.channel_fd is not None:
            inode = os.fstat(self.channel_fd).st_ino
            os.close(self.channel_fd)
            self.channel_fd = None
            try:
                if os.stat(self.channel_path).st_ino == inode:
                    os.unlink(self.channel_path)
            except OSError:
                pass
