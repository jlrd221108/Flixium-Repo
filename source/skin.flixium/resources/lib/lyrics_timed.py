"""TTML and KRC sidecars, preserving character ranges and real word timings."""
from collections import namedtuple
import re
import xml.etree.ElementTree as ET
import zlib

Word = namedtuple("Word", "start end first last")
KRC_KEY = bytes((0x40, 0x47, 0x61, 0x77, 0x5e, 0x32, 0x74, 0x47,
                 0x51, 0x36, 0x31, 0x2d, 0xce, 0xd2, 0x6e, 0x69))
MAX_LYRICS = 2 * 1024 * 1024


class LyricLine(tuple):
    """Remain compatible with existing (seconds, text) lyric consumers."""
    def __new__(cls, start, text, words=(), end=None, agent="", align="center", background=()):
        line = tuple.__new__(cls, (start, text))
        line.words, line.end = tuple(words), end
        line.agent, line.align, line.background = agent, align, tuple(background)
        return line


def clock(value, frame_rate=30, tick_rate=1):
    value = value.strip()
    match = re.fullmatch(r"([\d.]+)(ms|h|m|s|f|t)", value)
    if match:
        return float(match[1]) * {"ms": .001, "h": 3600, "m": 60,
                                  "s": 1, "f": 1 / frame_rate, "t": 1 / tick_rate}[match[2]]
    parts = value.split(":")
    if len(parts) == 4:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + float(parts[3]) / frame_rate
    result = 0.0
    for part in parts:
        result = result * 60 + float(part)
    return result


def local_name(name):
    return name.rsplit("}", 1)[-1]


def parse_ttml(text):
    if len(text) > MAX_LYRICS or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Unsupported or oversized lyric XML")
    root = ET.fromstring(text)
    if local_name(root.tag) != "tt":
        raise ValueError("Not a TTML document")
    attrs = {local_name(key): value for key, value in root.attrib.items()}
    rate = float(attrs.get("frameRate", 30))
    multiplier = attrs.get("frameRateMultiplier", "1 1").split()
    rate *= float(multiplier[0]) / float(multiplier[-1])
    tick = float(attrs.get("tickRate", 1))

    def timing(node, parent_start, parent_end):
        def absolute(value):
            # Apple Music clock timestamps are absolute; offset expressions
            # use the enclosing time container as their origin.
            return clock(value, rate, tick) + (parent_start if re.search(r"[a-z]$", value) else 0)
        start = absolute(node.get("begin")) if node.get("begin") else parent_start
        end = absolute(node.get("end")) if node.get("end") else parent_end
        if node.get("dur"):
            end = start + clock(node.get("dur"), rate, tick)
        return start, end

    rows, plain = [], []
    agent_ids = []
    for node in root.iter():
        if local_name(node.tag) == "agent":
            identity = next((v for k, v in node.attrib.items() if local_name(k) == "id"), "")
            if identity and identity not in agent_ids:
                agent_ids.append(identity)

    def attribute(node, name, default=""):
        return next((v for k, v in node.attrib.items() if local_name(k) == name), default)

    # Some sidecars omit the metadata declarations but still identify singers.
    for node in root.iter():
        identity = attribute(node, "agent")
        if identity and identity not in agent_ids:
            agent_ids.append(identity)
    primary_agent = "v1" if "v1" in agent_ids else next(iter(agent_ids), "")

    def alignment(agent):
        if len(agent_ids) < 2 or not agent:
            return "center"
        return "left" if agent == primary_agent else "right"

    def visit(node, parent_start=0.0, parent_end=None, parent_agent=""):
        start, end = timing(node, parent_start, parent_end)
        agent = attribute(node, "agent", parent_agent)
        if local_name(node.tag) != "p":
            for child in node:
                visit(child, start, end, agent)
            return

        line = extract(node, parent_start, parent_end, agent)
        if not line[1] and not line.background:
            return
        if node.get("begin") or line.words:
            rows.append(line)
        elif line[1]:
            plain.append(line[1])

    def extract(node, parent_start, parent_end, agent):
        start, end = timing(node, parent_start, parent_end)
        fragments, cues, backgrounds = [], [], []

        def append(value):
            if value and not (value.isspace() and ("\n" in value or "\t" in value)):
                fragments.append(re.sub(r"\s+", " ", value))

        def flatten(element, inherited_start, inherited_end):
            role = next((v for k, v in element.attrib.items() if local_name(k) == "role"), "")
            if role in ("x-translation", "x-roman"):
                return
            begin, finish = timing(element, inherited_start, inherited_end)
            first = sum(map(len, fragments))
            append(element.text)
            children_with_timing = False
            for child in element:
                if attribute(child, "role") == "x-bg":
                    background = extract(child, begin, finish, attribute(child, "agent", agent))
                    if background[1]:
                        backgrounds.append(background)
                elif local_name(child.tag) == "br":
                    fragments.append("\n")
                else:
                    before = len(cues)
                    flatten(child, begin, finish)
                    children_with_timing |= len(cues) > before
                append(child.tail)
            last = sum(map(len, fragments))
            if element is not node and element.get("begin") and not children_with_timing and finish is not None and last > first:
                cues.append(Word(begin, max(begin, finish), first, last))

        flatten(node, parent_start, parent_end)
        raw = "".join(fragments)
        left = len(raw) - len(raw.lstrip())
        content = raw.strip()
        words = [Word(c.start, c.end, max(0, c.first - left), min(len(content), c.last - left))
                 for c in cues if c.last > left and c.first - left < len(content)]
        if not words and node.get("begin") and local_name(node.tag) == "span" and end is not None and content:
            words = [Word(start, max(start, end), 0, len(content))]
        # A paragraph containing only a backing vocal still needs a lead row;
        # otherwise an entirely valid standalone echo would appear blank.
        if not content and backgrounds:
            first = backgrounds.pop(0)
            return LyricLine(first[0], first[1], first.words, first.end,
                             first.agent, first.align, backgrounds)
        begin = start if node.get("begin") or not words else min(c.start for c in words)
        if end is None and words:
            end = max(c.end for c in words)
        return LyricLine(max(0, begin), content, words, end, agent, alignment(agent), backgrounds)

    body = next((node for node in root if local_name(node.tag) == "body"), None)
    if body is not None:
        visit(body)
    rows.sort(key=lambda line: line[0])
    return rows, "\n".join(plain) if not rows else ""


def parse_krc(data):
    from lyrics_local import decode_text, parse_lyrics
    if data.startswith(b"krc1"):
        payload = bytes(value ^ KRC_KEY[i % 16] for i, value in enumerate(data[4:]))
        decoder = zlib.decompressobj()
        try:
            decoded = decoder.decompress(payload, MAX_LYRICS + 1)
        except zlib.error as error:
            raise ValueError("Invalid compressed KRC: {}".format(error))
        if len(decoded) > MAX_LYRICS or not decoder.eof:
            raise ValueError("Invalid or oversized compressed KRC")
        text = decode_text(decoded)
    else:
        text = decode_text(data)
    # Some exporters write LRC (or enhanced LRC) under the .krc extension.
    if not re.search(r"^\[\d+,\d+\]", text, re.M):
        return parse_lyrics(text)
    offset = re.search(r"\[offset:([+-]?\d+)\]", text, re.I)
    offset = int(offset[1]) / 1000 if offset else 0
    rows = []
    for match in re.finditer(r"^\[(\d+),(\d+)\](.*)$", text, re.M):
        start = int(match[1]) / 1000 + offset
        content, cues = "", []
        payload = match[3].rstrip("\r")
        pieces = list(re.finditer(r"<(\d+),(\d+),\d+>([^<]*)", payload))
        for piece in pieces:
            first = len(content)
            content += piece[3]
            begin = start + int(piece[1]) / 1000
            cues.append(Word(max(0, begin), max(0, begin + int(piece[2]) / 1000), first, len(content)))
        if not pieces:
            content = payload
        rows.append(LyricLine(max(0, start), content, cues, max(0, start + int(match[2]) / 1000)))
    rows.sort(key=lambda line: line[0])
    return rows, ""


def parse_sidecar(data, extension):
    from lyrics_local import decode_text, parse_lyrics
    if extension.lower() == ".krc" or data.startswith(b"krc1"):
        return parse_krc(data)
    text = decode_text(data)
    if extension.lower() == ".ttml" or re.search(r"<(?:\w+:)?tt[\s>]", text):
        return parse_ttml(text)
    return parse_lyrics(text)
