"""Offline selected-media metadata: bounded MP4/MOV tags and GPS place lookup."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
import os
import re
import struct
import sys

VIDEO_EXTENSIONS = frozenset('mp4 mov m4v 3gp 3g2 avi mkv webm mts m2ts ts mpg mpeg wmv flv vob'.split())


def coordinate(value, latitude=True):
    """Read Kodi's decimal or DMS EXIF strings, preserving S/W hemispheres."""
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().upper()
    numbers = re.findall(r'[+-]?\d+(?:[.,]\d+)?', text)
    if not 1 <= len(numbers) <= 3:
        return None
    parts = [float(n.replace(',', '.')) for n in numbers]
    if len(parts) > 1 and not 0 <= parts[1] < 60:
        return None
    if len(parts) > 2 and not 0 <= parts[2] < 60:
        return None
    result = abs(parts[0]) + (parts[1] / 60 if len(parts) > 1 else 0) + (parts[2] / 3600 if len(parts) > 2 else 0)
    if text.startswith('-') or parts[0] < 0 or re.search(r'[SW]\s*$', text):
        result = -result
    if not math.isfinite(result) or abs(result) > (90 if latitude else 180):
        return None
    return result


def iso6709(text):
    match = re.search(r'([+-]\d{2}(?:\.\d+)?)([+-]\d{3}(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?/?', text)
    if not match:
        return {}
    lat, lon = float(match[1]), float(match[2])
    if abs(lat) > 90 or abs(lon) > 180:
        return {}
    result = {'lat': lat, 'lon': lon}
    if match[3]:
        result['altitude'] = float(match[3])
    return result


@lru_cache(maxsize=512)
def reverse_location(lat, lon):
    """Offline place-name lookup is omitted from this lightweight build."""
    return {}


def location_details(metadata, native=None, lookup=reverse_location):
    native = native or {}
    lat, lon = metadata.get('lat'), metadata.get('lon')
    if lat is None:
        lat = coordinate(native.get('lat'))
    if lon is None:
        lon = coordinate(native.get('lon'), latitude=False)
    place = {}
    if lat is not None and lon is not None:
        place = lookup(round(lat, 6), round(lon, 6))
    rows = []
    if native.get('city'):
        rows.append(('City', native['city']))
    elif place.get('city'):
        rows.append((place.get('label', 'Nearest city'), place['city']))
    country = native.get('country') or place.get('country')
    if country:
        rows.append(('Country', country))
    if lat is not None:
        rows.append(('Latitude', '{:.6f}'.format(lat)))
    if lon is not None:
        rows.append(('Longitude', '{:.6f}'.format(lon)))
    altitude = metadata.get('altitude', native.get('altitude'))
    if altitude is not None and altitude != '':
        rows.append(('Altitude', '{}{}'.format(altitude, ' m' if isinstance(altitude, (int, float)) else '')))
    return rows


def duration_label(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return '{}:{:02d}:{:02d}'.format(hours, minutes, seconds) if hours else '{}:{:02d}'.format(minutes, seconds)


def video_details(metadata):
    rows = []
    if metadata.get('width') and metadata.get('height'):
        rows.append(('Dimensions', '{} × {}'.format(metadata['width'], metadata['height'])))
    if metadata.get('duration'):
        rows.append(('Duration', duration_label(metadata['duration'])))
    codecs = {'hvc1': 'HEVC / H.265', 'hev1': 'HEVC / H.265', 'avc1': 'H.264',
              'avc3': 'H.264', 'mp4a': 'AAC', 'av01': 'AV1', 'vp09': 'VP9',
              'ac-3': 'AC-3', 'ec-3': 'E-AC-3', 'alac': 'Apple Lossless'}
    for key, caption in [('video_codec', 'Video codec'), ('audio_codec', 'Audio codec'),
                         ('captured', 'Captured'), ('make', 'Camera make'), ('model', 'Camera model')]:
        if metadata.get(key):
            value = metadata[key]
            if key.endswith('_codec'):
                value = codecs.get(value, value)
            elif key == 'captured':
                try:
                    value = datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat(sep=' ', timespec='seconds')
                except ValueError:
                    pass
            rows.append((caption, value))
    if metadata.get('fps'):
        rows.append(('Frame rate', '{:.2f} fps'.format(metadata['fps'])))
    return rows


def format_rows(rows):
    # Embedded captions may contain Kodi markup; keep them plain text.
    return '[CR]'.join('{} · {}'.format(label, str(value).replace('[', '(').replace(']', ')')) for label, value in rows)


def read_mp4(stream, length, cancelled=lambda: False):
    """Read bounded QuickTime/ISO-BMFF headers, seeking past encoded media.

    Supports Apple mdta keys/ilst, legacy ©xyz location, Android location tags,
    movie creation time, track dimensions, duration, codecs and sample count.
    No frame decoding, executable dependency, or full-file reads.
    """
    result, tracks = {}, []
    budget, count = [4 * 1024 * 1024], [0]

    def read_at(position, size):
        if cancelled() or size < 0 or size > budget[0]:
            return b''
        stream.seek(position)
        data = stream.read(size)
        budget[0] -= len(data)
        return data

    def atoms(start, end):
        while start + 8 <= end and count[0] < 20000 and not cancelled():
            header = read_at(start, 8)
            if len(header) != 8:
                return
            size, kind = struct.unpack('>I4s', header)
            offset = 8
            if size == 1:
                extra = read_at(start + 8, 8)
                if len(extra) != 8:
                    return
                size, offset = struct.unpack('>Q', extra)[0], 16
            elif size == 0:
                size = end - start
            if size < offset or start + size > end:
                return
            count[0] += 1
            yield kind, start + offset, start + size
            start += size

    def tag(name, data):
        text = data.decode('utf-8', errors='replace').strip('\0')
        if 'location' in name.lower() or name == '©xyz':
            result.update(iso6709(text))
        for suffix, key in [('creationdate', 'captured'), ('make', 'make'), ('model', 'model')]:
            if name.lower().endswith(suffix):
                result[key] = text
        if name in ('©day', '©mak', '©mod'):
            result[{'©day': 'captured', '©mak': 'make', '©mod': 'model'}[name]] = text

    def metadata(start, end, depth):
        # QuickTime also permits meta without the ISO full-box version header.
        head = read_at(start, min(8, end - start))
        start += 4 if head[:4] == b'\0\0\0\0' else 0
        children = list(atoms(start, end))
        keys = {}
        for kind, body, stop in children:
            if kind == b'keys':
                data = read_at(body, min(stop - body, 256 * 1024))
                if len(data) < 8:
                    continue
                position = 8
                for index in range(1, min(struct.unpack_from('>I', data, 4)[0], 4096) + 1):
                    if position + 8 > len(data):
                        break
                    size = struct.unpack_from('>I', data, position)[0]
                    if size < 8 or position + size > len(data):
                        break
                    keys[index] = data[position + 8:position + size].decode('utf-8', errors='replace')
                    position += size
        for kind, body, stop in children:
            if kind == b'ilst':
                for item, value, limit in atoms(body, stop):
                    name = keys.get(int.from_bytes(item, 'big'), item.decode('latin-1'))
                    for child, payload, finish in atoms(value, limit):
                        if child == b'data':
                            tag(name, read_at(payload + 8, min(max(0, finish - payload - 8), 64 * 1024)))

    def walk(start, end, depth=0, track=None):
        if depth > 12:
            return
        for kind, body, stop in atoms(start, end):
            size = stop - body
            if kind == b'meta':
                metadata(body, stop, depth + 1)
            elif kind == b'trak':
                child_track = {}
                walk(body, stop, depth + 1, child_track)
                tracks.append(child_track)
            elif kind in (b'moov', b'udta', b'mdia', b'minf', b'stbl'):
                walk(body, stop, depth + 1, track)
            elif kind in (b'mvhd', b'mdhd'):
                data = read_at(body, min(size, 40))
                if len(data) < 20:
                    continue
                version = data[0]
                if version == 1 and len(data) >= 32:
                    created, scale, duration = struct.unpack_from('>Q', data, 4)[0], struct.unpack_from('>I', data, 20)[0], struct.unpack_from('>Q', data, 24)[0]
                elif version == 0:
                    created, _, scale, duration = struct.unpack_from('>IIII', data, 4)
                else:
                    continue
                target = result if kind == b'mvhd' else track
                if target is not None and scale and duration not in (0, 0xffffffff, 0xffffffffffffffff):
                    target['duration'] = duration / scale
                if kind == b'mvhd' and created:
                    try:
                        date = datetime(1904, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=created)
                        if date.year >= 1970:
                            result.setdefault('captured', date.strftime('%Y-%m-%d %H:%M:%S UTC'))
                    except (ValueError, OverflowError):
                        pass
            elif kind == b'tkhd' and track is not None and size >= 8:
                data = read_at(stop - 8, 8)
                if len(data) == 8:
                    width, height = struct.unpack('>II', data)
                    if width and height:
                        track.update(width=round(width / 65536), height=round(height / 65536))
            elif kind == b'hdlr' and track is not None:
                data = read_at(body, min(size, 12))
                if len(data) >= 12:
                    track['handler'] = data[8:12]
            elif kind == b'stsd' and track is not None:
                data = read_at(body, min(size, 16))
                if len(data) >= 16:
                    track['codec'] = data[12:16].decode('ascii', errors='replace')
            elif kind == b'stsz' and track is not None:
                data = read_at(body, min(size, 12))
                if len(data) >= 12:
                    track['samples'] = struct.unpack_from('>I', data, 8)[0]
            elif kind in (b'\xa9xyz', b'\xa9day', b'\xa9mak', b'\xa9mod'):
                data = read_at(body, min(size, 64 * 1024))
                if len(data) >= 4 and int.from_bytes(data[:2], 'big') <= len(data) - 4:
                    data = data[4:]
                tag(kind.decode('latin-1'), data)
    walk(0, length)
    for track in tracks:
        if track.get('handler') == b'vide' or track.get('width'):
            result.update({key: track[key] for key in ('width', 'height') if key in track})
            if track.get('codec'):
                result['video_codec'] = track['codec']
            if track.get('duration') and track.get('samples'):
                result['fps'] = track['samples'] / track['duration']
        elif track.get('handler') == b'soun' and track.get('codec'):
            result['audio_codec'] = track['codec']
    return result
