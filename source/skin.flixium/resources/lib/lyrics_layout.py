"""Cached static glyph measurements/masks for the native GPU renderer only."""
from collections import OrderedDict
import math
import os
import re
from lyrics_motion import letter_capable, motion_words, units

def text_width(font, text):
    return font.getlength(text) if hasattr(font, "getlength") else font.getsize(text)[0]

class CachedGlyphLayout:
    def __init__(self):
        self.layouts, self.word_layouts, self.motion_layouts = OrderedDict(), OrderedDict(), OrderedDict()
        self.font, self.fonts = None, {}

    def layout(self, text, align="center", font_size=36, height=180):
        key = (text, align, font_size, height)
        if key in self.layouts:
            self.layouts.move_to_end(key)
            return self.layouts[key]
        from PIL import Image, ImageDraw, ImageFont
        scale = 1
        if font_size not in self.fonts:
            self.fonts[font_size] = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "..", "..", "fonts", "SpotifyMixUI-Bold.ttf"), font_size * scale)
        font = self.fonts[font_size]
        self.font = self.fonts.get(36)
        mask = Image.new("L", (978 * scale, height * scale))
        draw = ImageDraw.Draw(mask)
        ranges = []
        for paragraph in re.finditer(r"[^\n]+", text):
            first, end = paragraph.start(), paragraph.start()
            for token in re.finditer(r"\S+\s*", paragraph.group()):
                last = paragraph.start() + token.end()
                if end > first and text_width(font, text[first:last].rstrip()) > 930 * scale:
                    ranges.append((first, end))
                    first = paragraph.start() + token.start()
                end = last
            if end > first:
                ranges.append((first, end))
        ascent, descent = font.getmetrics()
        line_height = ascent + descent + 4 * scale
        boxes = []
        for first, last in ranges:
            value = text[first:last].rstrip()
            if hasattr(font, "getbbox"):
                box = font.getbbox(value)
            else:
                offset = font.getoffset(value)
                size = font.getsize(value)
                box = (offset[0], offset[1], size[0], size[1])
            boxes.append(box)
        if not boxes:
            raise ValueError("Empty timed lyric")
        top = min(box[1] + i * line_height for i, box in enumerate(boxes))
        bottom = max(box[3] + i * line_height for i, box in enumerate(boxes))
        y = (mask.height - (bottom - top)) / 2 - top
        rows = []
        for i, (first, last) in enumerate(ranges):
            value = text[first:last].rstrip()
            width = text_width(font, value)
            x = 24 if align == "left" else mask.width - 24 - width if align == "right" else (mask.width - width) / 2
            row_y = y + i * line_height
            draw.text((x, row_y), value, font=font, fill=255)
            rows.append((first, first + len(value), x, row_y + boxes[i][1], row_y + boxes[i][3]))
        result = mask, font, rows
        self.layouts[key] = result
        while len(self.layouts) > 4:
            self.layouts.popitem(last=False)
        return result

    def motion_layout(self, line, text, align, font_size, height, letter_mode="refreshed"):
        key = (text, tuple(line.words), align, font_size, height, letter_mode)
        if key in self.motion_layouts:
            self.motion_layouts.move_to_end(key)
            return self.motion_layouts[key]
        _, font, rows = self.layout(text, align, font_size, height)
        _, _, crop = self.word_layout(text, line.words, align, font_size, height)
        words, plan = (tuple(line.words) if letter_mode in ("spicy", "simple") else motion_words(line)), []
        for word_index, cue in enumerate(words):
            for first, last, x, top, bottom in rows:
                begin, end = max(first, cue.first), min(last, cue.last)
                if begin >= end:
                    continue
                left = x + text_width(font, text[first:begin]) - crop[0]
                right = x + text_width(font, text[first:end]) - crop[0]
                # Adjacent syllables must share one pixel boundary, not overlap
                # floor/ceil slices which separate when their scales differ.
                box = (round(left) if begin > first and not text[begin - 1].isspace() else math.floor(left),
                       math.floor(top - crop[1]) - 1,
                       round(right) if end < last and not text[end].isspace() else math.ceil(right),
                       math.ceil(bottom - crop[1]) + 1)
                glyphs = []
                # Never split a word that wraps, or a script that needs shaping.
                pieces = units(text[begin:end], allow_complex=letter_mode in ("spicy", "simple"))
                capable = (bool(pieces) and cue.end - cue.start >= 1 if letter_mode == "spicy"
                           else bool(pieces) and len(pieces) <= 12 and cue.end - cue.start >= 1.05
                           if letter_mode == "simple" else letter_capable(text[begin:end], cue))
                if begin == cue.first and end == cue.last and capable:
                    offset = begin
                    for index, piece in enumerate(pieces):
                        following = offset + len(piece)
                        a = box[0] if index == 0 else round(x + text_width(font, text[first:offset]) - crop[0])
                        b = box[2] if index == len(pieces) - 1 else round(x + text_width(font, text[first:following]) - crop[0])
                        if b > a:
                            glyphs.append(((a, box[1], b, box[3]), index, len(pieces)))
                        offset = following
                plan.append((cue, word_index == len(words) - 1, box, tuple(glyphs)))
        self.motion_layouts[key] = plan
        while len(self.motion_layouts) > 8:
            self.motion_layouts.popitem(last=False)
        return plan

    def word_layout(self, text, words, align="center", font_size=36, height=180):
        """Measure word spans once per line, and blur only occupied pixels.

        A 24px margin retains the existing 8px Gaussian halo. The public frame
        remains 978x180, so Kodi's positioning and lyric-bank slides do not move.
        """
        key = (text, tuple(words), align, font_size, height)
        if key in self.word_layouts:
            self.word_layouts.move_to_end(key)
            return self.word_layouts[key]
        mask, font, rows = self.layout(text, align, font_size, height)
        bounds = mask.getbbox() or (0, 0, mask.width, mask.height)
        crop = (max(0, bounds[0] - 24), max(0, bounds[1] - 24),
                min(mask.width, bounds[2] + 24), min(mask.height, bounds[3] + 24))
        spans = []
        for cue in words:
            boxes = []
            for first, last, x, top, bottom in rows:
                begin, end = max(first, cue.first), min(last, cue.last)
                if begin >= end:
                    continue
                left = x + text_width(font, text[first:begin]) - crop[0]
                right = x + text_width(font, text[first:end]) - crop[0]
                boxes.append((left, top - crop[1], right, bottom - crop[1]))
            spans.append(boxes)
        result = mask.crop(crop), spans, crop
        self.word_layouts[key] = result
        while len(self.word_layouts) > 4:
            self.word_layouts.popitem(last=False)
        return result
