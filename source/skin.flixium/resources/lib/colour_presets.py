"""Validated, portable user colour palettes, stored with the skin settings."""

from localization import localize as L
import json
import re
import uuid
from urllib.parse import quote, unquote

COLOURS = ('Window', 'Panel', 'Card', 'Focus', 'Highlight', 'Dialog', 'DialogHeader')
FLAGS = ('WindowCustom', 'HighlightCustom', 'DialogCustom')
KEYS = COLOURS + FLAGS + ('Scheme', 'BackgroundPreset', 'BackgroundPresetName')


def name(value):
    if not isinstance(value, str):
        raise ValueError(L(31769))
    value = value.strip()
    if not 1 <= len(value) <= 60 or re.search(r'[\x00-\x1f"\\]', value):
        raise ValueError(L(31770))
    return value


def palette(values):
    if not isinstance(values, dict):
        raise ValueError(L(31771))
    result = {}
    for key in KEYS:
        value = values.get(key, '')
        if not isinstance(value, str):
            raise ValueError(L(31776))
        if key in COLOURS:
            if value and not re.fullmatch(r'[0-9A-Fa-f]{8}', value):
                raise ValueError(L(31779))
            value = value.upper()
        elif key in FLAGS:
            if value not in ('', 'true'):
                raise ValueError(L(31780))
        elif key in ('Scheme', 'BackgroundPreset'):
            if value and not re.fullmatch(r'\d{1,3}', value):
                raise ValueError(L(31781))
        elif value:
            value = name(value)
        result[key] = value
    return result


def validate(rows):
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError(L(31772))
    result, ids, names = [], set(), set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'[a-f0-9]{32}', row['id']):
            raise ValueError(L(31777))
        label = name(row.get('name', ''))
        if row['id'] in ids or label.casefold() in names:
            raise ValueError(L(31778))
        ids.add(row['id']); names.add(label.casefold())
        result.append({'id': row['id'], 'name': label, 'colours': palette(row.get('colours'))})
    return result


def decode(value):
    if not value:
        return []
    if len(value) > 200000:
        raise ValueError(L(31773))
    return validate(json.loads(unquote(value)))


def encode(rows):
    return quote(json.dumps(validate(rows), ensure_ascii=False, separators=(',', ':')), safe='')


def save(rows, label, colours, preset_id=None):
    rows = validate(rows)
    label = name(label)
    if any(row['name'].casefold() == label.casefold() and row['id'] != preset_id for row in rows):
        raise ValueError(L(31774))
    if preset_id is not None and not any(row['id'] == preset_id for row in rows):
        raise ValueError(L(31775))
    entry = {'id': preset_id or uuid.uuid4().hex, 'name': label, 'colours': palette(colours)}
    return validate([entry if row['id'] == entry['id'] else row for row in rows] if preset_id else rows + [entry])
