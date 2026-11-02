"""Build interlude rows once, without changing the original timed sidecar data."""
import math

from lyrics_timed import LyricLine


def interlude(start, end):
    line = LyricLine(start, "\u2022 \u2022 \u2022", (), end)
    line.kind = "interlude"
    return line


def with_interludes(lines, enabled):
    if not enabled or not lines:
        return lines
    result = []
    if lines[0][0] >= 3:
        result.append(interlude(0, lines[0][0] - .35))
    busy_until = 0
    for index, line in enumerate(lines):
        result.append(line)
        if index + 1 >= len(lines):
            continue
        next_start = lines[index + 1][0]
        # LRC supplies starts, not vocal ends. Do not invent instrumental gaps
        # inside a line whose duration is unknown.
        end = getattr(line, "end", None)
        busy_until = max(busy_until, next_start if end is None else end)
        for background in getattr(line, "background", ()):
            busy_until = max(busy_until, next_start if background.end is None else background.end)
        if next_start - busy_until >= 3:
            result.append(interlude(busy_until + .2, next_start - .35))
    return result


def dot_colors(line, position):
    duration = max(.001, line.end - line[0])
    colors = []
    for index in range(3):
        phase = max(0, min(1, (position - line[0]) / duration * 3 - index))
        amount = .5 - .5 * math.cos(math.pi * phase)
        alpha = round(64 + (255 - 64) * amount)
        colors.append("{:02X}FFFFFF".format(alpha))
    return tuple(colors)
