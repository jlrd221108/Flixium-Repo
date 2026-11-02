"""Local lyric parsing; no network requests or third-party dependencies."""
import re

TIMESTAMP = re.compile(r"\[(\d+):(\d{2})(?:[.:](\d{1,3}))?\]")
OFFSET = re.compile(r"\[offset:([+-]?\d+)\]", re.I)
MAX_TAG = 8 * 1024 * 1024


def decode_text(data):
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeError:
            pass
    return data.decode("utf-8", "replace")


def parse_lyrics(text):
    """Return sorted (seconds, line) pairs and plain text; apply LRC offset."""
    if re.search(r"<(?:\w+:)?tt[\s>]", text):
        from lyrics_timed import parse_ttml
        return parse_ttml(text)
    offset_match = OFFSET.search(text)
    offset = int(offset_match.group(1)) / 1000.0 if offset_match else 0.0
    timed, plain = [], []
    for line in text.replace("\r", "").split("\n"):
        stamps = list(TIMESTAMP.finditer(line))
        if stamps:
            words = TIMESTAMP.sub("", line).strip()
            # Enhanced LRC word timestamps are removed for line-level display.
            words = re.sub(r"<\d+:\d{2}(?:\.\d+)?>", "", words)
            for stamp in stamps:
                fraction = stamp.group(3) or "0"
                seconds = int(stamp.group(1)) * 60 + int(stamp.group(2))
                timed.append((max(0.0, seconds + int(fraction) / 10 ** len(fraction) + offset), words))
        elif not re.fullmatch(r"\s*\[[a-z]+:.*\]\s*", line, re.I):
            plain.append(line)
    timed.sort(key=lambda entry: entry[0])
    return timed, "\n".join(plain).strip()


def synchsafe(data):
    result = 0
    for byte in data:
        result = (result << 7) | (byte & 127)
    return result


def take_string(data, encoding):
    step = 2 if encoding in (1, 2) else 1
    for pos in range(0, len(data) - step + 1, step):
        if data[pos:pos + step] == b"\0" * step:
            return data[:pos], data[pos + step:]
    return data, b""


def id3_text(data, encoding):
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(encoding, "utf-8")
    if encoding == 1 and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        codec = "utf-16-le"
    return data.decode(codec, "replace").strip("\0")


def read_id3_lyrics(header, data):
    version, flags = header[3], header[5]
    if version not in (3, 4):
        return [], ""
    if version == 3 and flags & 128:
        data = data.replace(b"\xff\0", b"\xff")
    pos = 0
    if flags & 64 and len(data) >= 4:
        pos = (synchsafe(data[:4]) if version == 4 else int.from_bytes(data[:4], "big") + 4)
    fallback = ""
    while pos + 10 <= len(data):
        name, size_data, flag_data = data[pos:pos + 4], data[pos + 4:pos + 8], data[pos + 8:pos + 10]
        size = synchsafe(size_data) if version == 4 else int.from_bytes(size_data, "big")
        if not name.strip(b"\0") or size <= 0 or pos + 10 + size > len(data):
            break
        frame = data[pos + 10:pos + 10 + size]
        pos += 10 + size
        if name not in (b"USLT", b"SYLT"):
            continue
        # Compressed/encrypted frames cannot be decoded here.
        if flag_data[1] & (0x0C if version == 4 else 0xC0):
            continue
        if flag_data[1] & (0x40 if version == 4 else 0x20):
            frame = frame[1:]
        if version == 4 and flag_data[1] & 1:
            frame = frame[4:]
        if version == 4 and (flags & 128 or flag_data[1] & 2):
            frame = frame.replace(b"\xff\0", b"\xff")
        if len(frame) < 4:
            continue
        encoding = frame[0]
        if name == b"USLT":
            _, content = take_string(frame[4:], encoding)
            text = id3_text(content, encoding)
            lines, plain = parse_lyrics(text)
            if lines:
                return lines, ""
            fallback = plain or fallback
        elif len(frame) >= 6 and frame[4] == 2:
            _, content = take_string(frame[6:], encoding)
            entries = []
            while content:
                words, content = take_string(content, encoding)
                if len(content) < 4:
                    break
                timestamp = int.from_bytes(content[:4], "big") / 1000.0
                content = content[4:]
                entries.append((timestamp, id3_text(words, encoding)))
            if entries:
                return sorted(entries), ""
    return [], fallback


def read_flac_comments(data):
    """Read LRC/plain text from common Vorbis comment lyric keys."""
    if len(data) < 8:
        return [], ""
    vendor_size = int.from_bytes(data[:4], "little")
    pos = 4 + vendor_size
    if pos + 4 > len(data):
        return [], ""
    count = int.from_bytes(data[pos:pos + 4], "little")
    pos += 4
    plain = ""
    for _ in range(min(count, 10000)):
        if pos + 4 > len(data):
            break
        size = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4
        if pos + size > len(data):
            break
        comment = data[pos:pos + size].decode("utf-8", "replace")
        pos += size
        key, sep, value = comment.partition("=")
        if sep and key.upper() in ("LYRICS", "UNSYNCEDLYRICS", "SYNCEDLYRICS", "SYNCHRONIZEDLYRICS"):
            lines, text = parse_lyrics(value)
            if lines:
                return lines, ""
            plain = text or plain
    return [], plain


def embedded_lyrics(handle):
    """Read bounded MP3/FLAC metadata through a Kodi VFS handle."""
    header = bytes(handle.readBytes(10))
    if len(header) == 10 and header.startswith(b"ID3"):
        size = synchsafe(header[6:10])
        if size <= MAX_TAG:
            return read_id3_lyrics(header, bytes(handle.readBytes(size)))
    elif header.startswith(b"fLaC"):
        handle.seek(4, 0)
        total = 0
        while total < MAX_TAG:
            block = bytes(handle.readBytes(4))
            if len(block) != 4:
                break
            size = int.from_bytes(block[1:], "big")
            total += size + 4
            if total > MAX_TAG:
                break
            if block[0] & 127 == 4:
                result = read_flac_comments(bytes(handle.readBytes(size)))
                if result[0] or result[1]:
                    return result
            else:
                handle.seek(size, 1)
            if block[0] & 128:
                break
    return [], ""
