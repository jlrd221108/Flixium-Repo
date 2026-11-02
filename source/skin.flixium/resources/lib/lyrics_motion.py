"""Deterministic lyric choreography driven by song time, including seeks/pauses.

These curves are computed from timing data, never inferred from the audio.
No mutable animation clock or per-frame font measurement is needed.
"""
from collections import namedtuple
import math
import unicodedata

from lyrics_timed import Word

Pose = namedtuple("Pose", "scale x y glow")
REST = Pose(1.0, 0.0, 0.0, 0.0)


def clamp(value):
    return max(0.0, min(1.0, value))


def ease(value):
    value = clamp(value)
    return value * value * (3 - 2 * value)


def units(text, allow_complex=False):
    """Keep combining marks/emoji together; preserve complex shaping as a word.

    Splitting Arabic or Brahmic conjuncts into independently scaled glyphs can
    break shaping. Those scripts retain the ordinary whole-word animation.
    """
    if any(unicodedata.bidirectional(char) in ("R", "AL", "AN")
           or (not allow_complex and (0x900 <= ord(char) <= 0x109f or 0x1780 <= ord(char) <= 0x17ff))
           for char in text):
        return ()
    result = []
    for index, char in enumerate(text):
        combining = unicodedata.category(char).startswith("M") or ord(char) in (0xfe0e, 0xfe0f, 0x200d)
        join = index > 0 and (text[index - 1] == "\u200d" or
                             (allow_complex and any(tag in unicodedata.name(text[index - 1], "")
                                                    for tag in ("VIRAMA", "SIGN COENG", "ASAT"))))
        modifier = 0x1f3fb <= ord(char) <= 0x1f3ff
        regional_pair = (result and 0x1f1e6 <= ord(char) <= 0x1f1ff
                         and len(result[-1]) == 1 and 0x1f1e6 <= ord(result[-1]) <= 0x1f1ff)
        if result and (combining or join or modifier or regional_pair):
            result[-1] += char
        else:
            result.append(char)
    return tuple(result)


def motion_words(line):
    """Rejoin adjacent timed syllables for motion, retaining original fill cues."""
    text, result = line[1], []
    for cue in sorted(getattr(line, "words", ()), key=lambda word: word.first):
        first, last = max(0, cue.first), min(len(text), cue.last)
        while first < last and text[first].isspace():
            first += 1
        while last > first and text[last - 1].isspace():
            last -= 1
        if last <= first:
            continue
        if result and result[-1].last == first:
            previous = result.pop()
            result.append(Word(min(previous.start, cue.start), max(previous.end, cue.end), previous.first, last))
        else:
            result.append(Word(cue.start, cue.end, first, last))
    return tuple(result)


def letter_capable(text, cue):
    letters = units(text)
    return (cue.end - cue.start >= 1.0 and not any(char.isspace() for char in text)
            and 2 <= len(letters) <= 7 and any(char.isalpha() for char in text))


def word_pose(cue, position, last=False):
    duration = cue.end - cue.start
    if duration <= 0 or not cue.start < position < cue.end:
        return REST
    phase = (position - cue.start) / duration
    swell = math.sin(math.pi * ease(phase)) ** 2
    # Brief syllables stay restrained; held words get more room to breathe.
    amount = min(1.0, max(.3, duration / 1.5)) * (1.15 if last else 1)
    return Pose(1 + .035 * swell * amount, 0, -3.5 * swell * amount, .18 * swell * amount)


def letter_pose(cue, index, count, position, last=False):
    duration = max(1.0, cue.end - cue.start)
    strength = min(1.25, .45 + .22 * duration) * (1.25 if last else 1)
    # Overlapping swells launch left-to-right. Even the final letter gets a
    # full rise/fall, and settles after the note instead of snapping at its end.
    start = cue.start + .4 * duration * index / max(1, count - 1)
    length = duration * (.85 if last else .75)
    phase = (position - start) / length
    if phase <= 0 or phase >= 1:
        return REST
    swell = math.sin(math.pi * ease(phase)) ** 2
    spread = (index - (count - 1) / 2) * .7 * swell * strength
    return Pose(1 + .13 * swell * strength, spread,
                -5 * swell * strength, .45 * swell * strength)


def motion_end(cue, last=False):
    return cue.start + max(1.0, cue.end - cue.start) * (1.25 if last else 1.15)


def moving(line, position, options):
    if not options.words or not (options.motion or options.letters):
        return False
    words = motion_words(line)
    for index, cue in enumerate(words):
        emphasis = options.letters and letter_capable(line[1][cue.first:cue.last], cue)
        if not emphasis and not options.motion:
            continue
        end = motion_end(cue, index == len(words) - 1) if emphasis else cue.end
        if cue.start <= position < end:
            return True
    return False


def pose_key(poses):
    # The same song time yields the same image after pause, seek or repeat.
    return tuple((round(p.scale, 4), round(p.x, 3), round(p.y, 3), round(p.glow, 3)) for p in poses)
