"""Portable, validated Flixium archives. No Kodi imports or archive extraction."""

from localization import localize as L
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit, parse_qsl, urlencode
import zipfile
FORMAT = 'flixium-settings'
VERSION = 2
ADDON_ID = 'skin.flixium'
ASSET_PREFIX = 'flixium-backup://'
MAX_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_SETTINGS = 32768
NAME = re.compile('^[A-Za-z0-9_.-]{1,200}$')
ASSET_NAME = re.compile('^assets/[0-9]{4}\\.(xsp|png|jpg|jpeg|webp|gif|bmp|tbn)$')
CATEGORIES = ('general', 'customisation', 'artwork', 'ratings', 'osd')
CATEGORY_LABELS = ('General', 'Customisation', 'Artwork', 'Ratings', 'On screen display')
LEGACY_CATEGORIES = ('basics', 'flixium', 'views', 'widgets')
LEGACY_LABELS = ('General and home settings', 'Flixium and player settings', 'Flix and view customisation', 'Widget setup and customisation')

def sensitive(name):
    return bool(re.search('api.?key|password|secret|token|credential|^mdblist_key_migrated$', name, re.I))

def category(name):
    """Follow the current Skin Settings pages, including their nested editors."""
    name = name.lower()
    if name in ('flixium.glass.gradient', 'flixium.glass.panel', 'flixium.glass.dialog', 'flixium.glass.sidebar') or name.startswith('flixium.backup.'):
        return None
    if name.startswith(('flixium.rating', 'flixiumratings', 'flixium.mdblist', 'mdblist_')):
        return 'ratings'
    if name.startswith(('osd', 'flixiummusic', 'flixium.lyrics', 'flixium.playback', 'flixium.subtitle')):
        return 'osd'
    if name in ('no_fanart', 'background_overlay', 'show_musicvideoposter', 'flixium.useselectedsettingsbackground') or name.startswith(('homefanart', 'weatherfanart', 'moviegenrefanart')):
        return 'artwork'
    if name.startswith('flixium.settings'):
        return 'general'
    if name.startswith(('flixium', 'flix_', 'view_', 'home_')):
        return 'customisation'
    return 'general'

def legacy_category(name):
    """Version-one archives retain the exact category boundaries they saved."""
    name = name.lower()
    if name in ('flixium.glass.gradient', 'flixium.glass.panel', 'flixium.glass.dialog', 'flixium.glass.sidebar'):
        return None
    if name.startswith('flixium.backup.'):
        return None
    if name.startswith('flixium.homemenu.'):
        return 'basics'
    if name.startswith('flixium.widgets.'):
        return 'widgets'
    if name.startswith(('flix_', 'view_', 'flixium.blur', 'flixium.agerating', 'flixium.default')) and name != 'flixium.defaultsversion' or name in ('flixium.flixthumbsettingsmigrated', 'hide_mediaflags', 'show_musicvideoposter', 'circle_userrating', 'circle_rating', 'circle_none'):
        return 'views'
    if name.startswith(('flixium', 'mdblist_')):
        return 'flixium'
    return 'basics'

def scrub_credentials(value):
    """Remove authentication embedded in source URLs when sensitive data is excluded."""
    if '://' not in value:
        return value
    try:
        parsed = urlsplit(value)
        netloc = parsed.netloc.rsplit('@', 1)[-1]
        query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if not sensitive(key)]
        if netloc == parsed.netloc and len(query) == len(parse_qsl(parsed.query, keep_blank_values=True)):
            return value
        return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), parsed.fragment))
    except ValueError:
        return value

def selected_rows(rows, categories, include_sensitive, addon=False, legacy=False):
    classifier = legacy_category if legacy else category
    addon_category = 'flixium' if legacy else 'ratings'
    return [row for row in rows if (addon_category if addon else classifier(row['id'])) in categories and (include_sensitive or not sensitive(row['id']))]

def restore_selection(manifest):
    categories = LEGACY_CATEGORIES if manifest.get('version') == 1 else CATEGORIES
    return manifest.get('selection', {'categories': list(categories), 'sensitive': True})

def selection_labels(manifest):
    groups, labels = (LEGACY_CATEGORIES, LEGACY_LABELS) if manifest.get('version') == 1 else (CATEGORIES, CATEGORY_LABELS)
    selected = restore_selection(manifest)['categories']
    return [label for group, label in zip(groups, labels) if group in selected]

def map_value(value, transform):
    """Also map paths inside widget JSON, including its percent-encoded form."""
    if isinstance(value, list):
        return [map_value(item, transform) for item in value]
    if isinstance(value, dict):
        return {key: map_value(item, transform) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    decoded = unquote(value)
    if decoded.startswith(('[', '{')):
        try:
            parsed = json.loads(decoded)
        except ValueError:
            pass
        else:
            mapped = json.dumps(map_value(parsed, transform), ensure_ascii=False, separators=(',', ':'))
            return quote(mapped, safe='') if decoded != value else mapped
    return transform(value)

def portable_path(value, roots):
    for special, local in sorted(roots.items(), key=lambda item: len(item[1]), reverse=True):
        base = local.replace('\\', '/').rstrip('/')
        path = value.replace('\\', '/')
        if path.lower() == base.lower() or path.lower().startswith(base.lower() + '/'):
            return special.rstrip('/') + path[len(base):]
    if value.startswith('\\\\'):
        return 'smb:' + value.replace('\\', '/')
    return value

def foreign_path(value):
    return bool(re.match('^[A-Za-z]:[\\\\/]|^/(?!/)', value))

def validate_settings(rows):
    if not isinstance(rows, list) or len(rows) > MAX_SETTINGS:
        raise ValueError(L(31752))
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or (not NAME.fullmatch(row['id'])):
            raise ValueError(L(31754))
        identity = row['id'].lower()
        if identity in seen:
            raise ValueError(L(31755))
        seen.add(identity)
        kind, value = (row.get('type'), row.get('value'))
        if kind == 'bool':
            valid = type(value) is bool
        elif kind == 'string':
            valid = isinstance(value, str) and len(value) <= 1024 * 1024 and ('\x00' not in value)
        else:
            valid = False
        if not valid:
            raise ValueError(L(31756))

def pack(settings, addon_settings, files, skin_version, selection=None):
    manifest = {'format': FORMAT, 'version': VERSION, 'skin': ADDON_ID, 'skin_version': skin_version, 'created': datetime.now(timezone.utc).isoformat(), 'settings': settings, 'addon_settings': addon_settings, 'files': [{'path': path, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for path, data in sorted(files.items())]}
    if selection is not None:
        manifest['selection'] = selection
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        for path, data in files.items():
            archive.writestr(path, data)
    result = output.getvalue()
    unpack(result)
    return result

def unpack(data):
    if len(data) > MAX_BYTES:
        raise ValueError(L(31753))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > 2048 or len(names) != len(set(names)):
            raise ValueError(L(31757))
        if sum((item.file_size for item in entries)) > MAX_BYTES:
            raise ValueError(L(31758))
        if any((item.file_size > MAX_FILE_BYTES or item.flag_bits & 1 for item in entries)):
            raise ValueError(L(31759))
        if 'manifest.json' not in names:
            raise ValueError(L(31760))
        manifest = json.loads(archive.read('manifest.json'))
        if not isinstance(manifest, dict) or manifest.get('format') != FORMAT or manifest.get('skin') != ADDON_ID:
            raise ValueError(L(31760))
        if type(manifest.get('version')) is not int or manifest['version'] not in (1, VERSION):
            raise ValueError(L(31761))
        validate_settings(manifest.get('settings'))
        validate_settings(manifest.get('addon_settings'))
        selection = manifest.get('selection')
        allowed_categories = LEGACY_CATEGORIES if manifest['version'] == 1 else CATEGORIES
        if selection is not None:
            if not isinstance(selection, dict) or not isinstance(selection.get('categories'), list) or (not selection['categories']) or any((item not in allowed_categories for item in selection['categories'])) or (type(selection.get('sensitive')) is not bool):
                raise ValueError(L(31764))
        records = manifest.get('files')
        if not isinstance(records, list) or len(records) > 2047:
            raise ValueError(L(31762))
        files = {}
        for entry in records:
            if not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or (not ASSET_NAME.fullmatch(entry['path'])):
                raise ValueError(L(31765))
            path = entry['path']
            if path in files or path not in names:
                raise ValueError(L(31766))
            payload = archive.read(path)
            if len(payload) != entry.get('size') or hashlib.sha256(payload).hexdigest() != entry.get('sha256'):
                raise ValueError(L(31767))
            files[path] = payload
        if set(names) != {'manifest.json', *files}:
            raise ValueError(L(31763))
        return (manifest, files)

def restore_values(manifest, locations):
    restored = deepcopy(manifest)

    def resolve(value):
        if value.startswith(ASSET_PREFIX):
            path = value[len(ASSET_PREFIX):]
            if path not in locations:
                raise ValueError(L(31768))
            return locations[path]
        return value
    for row in restored['settings'] + restored['addon_settings']:
        row['value'] = map_value(row['value'], resolve)
    return restored

def quoted(value):
    """Quote one Kodi builtin argument, preserving slashes, commas and quotes."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'

def commands(settings):
    validate_settings(settings)
    result = []
    for row in settings:
        if row['type'] == 'bool':
            result.append('Skin.SetBool({},{})'.format(row['id'], str(row['value']).lower()))
        else:
            result.append('Skin.SetString({},{})'.format(row['id'], quoted(row['value'])))
    return result
