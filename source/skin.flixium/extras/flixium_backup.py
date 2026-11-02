"""Back up and restore the active profile's complete Flixium configuration."""

from flixium_localization import localize as L
import os
import re
import sys
from datetime import datetime
import uuid
import xml.etree.ElementTree as ET
import zipfile
import xbmc
from flixium_reload import request_reload
import xbmcaddon
import xbmcgui
import xbmcvfs
SKIN = xbmcvfs.translatePath('special://skin/')
sys.path.insert(0, os.path.join(SKIN, 'resources', 'lib'))
from skin_backup import ADDON_ID, ASSET_PREFIX, MAX_BYTES, MAX_FILE_BYTES, NAME, commands, foreign_path, map_value, pack, portable_path, restore_values, unpack, CATEGORIES, CATEGORY_LABELS, selected_rows, scrub_credentials, restore_selection, selection_labels
PROFILE = 'special://profile/addon_data/{}/'.format(ADDON_ID)
EXTENSIONS = ('.xsp', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tbn')

def read_file(path, limit=MAX_BYTES):
    handle = xbmcvfs.File(path)
    try:
        if handle.size() > limit:
            raise ValueError(L(31719))
        return bytes(handle.readBytes())
    finally:
        handle.close()

def write_file(path, data):
    handle = xbmcvfs.File(path, 'w')
    try:
        if not handle.write(data):
            raise OSError(L(31447))
    finally:
        handle.close()

def join(folder, name):
    return folder.rstrip('/\\') + '/' + name

def schema():
    root = ET.parse(os.path.join(SKIN, 'resources', 'settings.xml')).getroot()
    return {node.get('id'): node.get('type') for node in root.iter('setting') if node.get('id')}

def setting_names():
    """Include unknown/older saved settings, static references and dynamic widgets."""
    names = {}

    def add(name, kind):
        if name and NAME.fullmatch(name):
            names[name.lower()] = (name, kind)
    saved = PROFILE + 'settings.xml'
    if xbmcvfs.exists(saved):
        root = ET.fromstring(read_file(saved))
        for node in root.iter('setting'):
            kind = node.get('type')
            if kind in ('bool', 'string'):
                add(node.get('id'), kind)
    patterns = (('Skin\\.(?:HasSetting|SetBool|ToggleSetting)\\(\\s*([A-Za-z0-9_.-]+)\\s*[,)]', 'bool'), ('Skin\\.(?:String|SetString|SetNumeric|SetPath|SetFile|SetImage|SetLargeImage|SetAddon|SetColor)\\(\\s*([A-Za-z0-9_.-]+)\\s*[,)]', 'string'))
    for directory in ('xml', 'extras', 'resources/lib'):
        for folder, _, files in os.walk(os.path.join(SKIN, directory)):
            for filename in files:
                if not filename.endswith(('.xml', '.py')):
                    continue
                with open(os.path.join(folder, filename), encoding='utf-8-sig') as source:
                    text = source.read()
                for pattern, kind in patterns:
                    for match in re.finditer(pattern, text, re.I):
                        add(match.group(1), kind)
                for selection in re.findall('Skin\\.SelectBool\\(([^)]+)\\)', text, re.I):
                    for name in re.findall('\\|\\s*([A-Za-z0-9_.-]+)', selection):
                        add(name, 'bool')
    add('Flixium.Widgets.Configured', 'bool')
    add('Flixium.Widgets.GlobalAppearance', 'string')
    add('Flixium.Theme.UserPresets', 'string')
    add('Flixium.Theme.UserPreset', 'string')
    for section in ('movies', 'tvshows', 'music'):
        for suffix in ('Config', 'Count'):
            add('Flixium.Widgets.{}.{}'.format(section, suffix), 'string')
        for slot in range(1, 7):
            for suffix in ('Id', 'Path', 'Title', 'Artwork', 'Limit', 'Progress'):
                add('Flixium.Widgets.{}.{}.{}'.format(section, slot, suffix), 'string')
    return sorted(names.values(), key=lambda item: item[0].lower())

def capture():
    settings = []
    for name, kind in setting_names():
        value = xbmc.getCondVisibility('Skin.HasSetting({})'.format(name)) if kind == 'bool' else xbmc.getInfoLabel('Skin.String({})'.format(name))
        settings.append({'id': name, 'type': kind, 'value': value})
    addon = xbmcaddon.Addon(ADDON_ID)
    addon_settings = []
    for name, kind in schema().items():
        value = addon.getSetting(name)
        addon_settings.append({'id': name, 'type': 'bool' if kind == 'boolean' else 'string', 'value': value.lower() == 'true' if kind == 'boolean' else value})
    return (settings, addon_settings)

def backup_options():
    categories = [name for name in CATEGORIES if not xbmc.getCondVisibility('Skin.HasSetting(Flixium.Backup.Exclude{})'.format(name.title()))]
    private = xbmc.getCondVisibility('Skin.HasSetting(Flixium.Backup.IncludeSensitive)')
    return (categories, private)

def create_backup(strict=True, categories=None, include_sensitive=False):
    settings, addon_settings = capture()
    categories = list(CATEGORIES if categories is None else categories)
    if not categories:
        raise ValueError(L(31718))
    settings = selected_rows(settings, categories, include_sensitive)
    addon_settings = selected_rows(addon_settings, categories, include_sensitive, addon=True)
    roots = {'special://skin/': SKIN, 'special://profile/': xbmcvfs.translatePath('special://profile/'), 'special://home/': xbmcvfs.translatePath('special://home/')}
    files, paths, external = ({}, {}, set())

    def bundle(value):
        if not include_sensitive:
            value = scrub_credentials(value)
        portable = portable_path(value, roots)
        if portable.startswith('special://skin/'):
            return portable
        if portable.lower().endswith(EXTENSIONS) and ('/' in portable or '\\' in portable or xbmcvfs.exists(value)):
            if portable in paths:
                return ASSET_PREFIX + paths[portable]
            if not xbmcvfs.exists(value):
                if not strict:
                    return portable
                raise ValueError(L(31723) + value)
            path = L(31451).format(len(paths), os.path.splitext(portable)[1].lower())
            paths[portable] = path
            payload = read_file(value, MAX_FILE_BYTES)
            if path.endswith('.xsp'):
                root = ET.fromstring(payload)
                if root.tag != 'smartplaylist':
                    raise ValueError(L(31727))
                for node in root.iter():
                    if node.text:
                        node.text = map_value(node.text, bundle)
                payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            files[path] = payload
            if sum(map(len, files.values())) > MAX_BYTES:
                raise ValueError(L(31724))
            return ASSET_PREFIX + path
        if foreign_path(portable):
            external.add(portable)
        return portable
    for row in settings + addon_settings:
        row['value'] = map_value(row['value'], bundle)
    return (pack(settings, addon_settings, files, xbmcaddon.Addon(ADDON_ID).getAddonInfo('version'), {'categories': categories, 'sensitive': include_sensitive}), external)

def apply_settings(manifest):
    selection = restore_selection(manifest)
    current, _ = capture()
    reset = [{'id': row['id'], 'type': row['type'], 'value': False if row['type'] == 'bool' else ''} for row in selected_rows(current, selection['categories'], selection['sensitive'], legacy=manifest.get('version') == 1)]
    restored_ids = {row['id'].lower() for row in manifest['settings']}
    reset = [row for row in reset if row['id'].lower() not in restored_ids]
    for command in commands(reset + manifest['settings']):
        xbmc.executebuiltin(command, True)
    addon = xbmcaddon.Addon(ADDON_ID)
    for row in manifest['addon_settings']:
        value = str(row['value']).lower() if row['type'] == 'bool' else row['value']
        if not addon.setSetting(row['id'], value):
            raise RuntimeError(L(31720))

def prepare_restore(data, include_sensitive=False):
    manifest, files = unpack(data)
    selection = restore_selection(manifest)
    include_sensitive = include_sensitive and selection['sensitive']
    manifest['selection'] = {'categories': selection['categories'], 'sensitive': include_sensitive}
    legacy = manifest.get('version') == 1
    manifest['settings'] = selected_rows(manifest['settings'], selection['categories'], include_sensitive, legacy=legacy)
    manifest['addon_settings'] = selected_rows(manifest['addon_settings'], selection['categories'], include_sensitive, addon=True, legacy=legacy)
    definitions = schema()
    for row in manifest['addon_settings']:
        if row['id'] not in definitions:
            raise ValueError(L(31721))
        expected = 'bool' if definitions[row['id']] == 'boolean' else 'string'
        if row['type'] != expected:
            raise ValueError(L(31722))
    destination = PROFILE + 'restored/' + uuid.uuid4().hex + '/'
    locations = {path: destination + path for path in files}
    restored = restore_values(manifest, locations)
    prepared, external = ({}, set())

    def resolve(value):
        if not include_sensitive:
            value = scrub_credentials(value)
        if value.startswith(ASSET_PREFIX):
            path = value[len(ASSET_PREFIX):]
            if path not in locations:
                raise ValueError(L(31725))
            return locations[path]
        if foreign_path(value):
            external.add(value)
        return value
    for row in restored['settings'] + restored['addon_settings']:
        row['value'] = map_value(row['value'], resolve)
    for path, payload in files.items():
        if path.endswith('.xsp'):
            root = ET.fromstring(payload)
            if root.tag != 'smartplaylist':
                raise ValueError(L(31726))
            for node in root.iter():
                if node.text:
                    node.text = map_value(node.text, resolve)
            payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        prepared[locations[path]] = payload
    return (restored, prepared, external)

def backup():
    dialog = xbmcgui.Dialog()
    categories, private = backup_options()
    if not categories:
        raise ValueError(L(31718))
    folder = dialog.browse(0, L(31435), 'files', '', False, True)
    if not folder:
        return
    data, external = create_backup(categories=categories, include_sensitive=private)
    filename = L(31442).format(datetime.now().strftime('%Y%m%d-%H%M%S'), uuid.uuid4().hex[:6])
    destination = join(folder, filename)
    write_file(destination, data)
    unpack(read_file(destination))
    message = L(31436) + destination
    if external:
        message += L(31437)
    dialog.ok(L(31438), message)

def restore():
    dialog = xbmcgui.Dialog()
    source = dialog.browse(1, L(31439), 'files', '.zip', False, False)
    if not source:
        return
    _, private = backup_options()
    restored, files, external = prepare_restore(read_file(source), include_sensitive=private)
    labels = selection_labels(restored)
    message = L(31443).format(', '.join(labels))
    if external:
        message += L(31440)
    if not dialog.yesno(L(31444), message):
        return
    original_settings, original_addon = capture()
    safety, _ = create_backup(strict=False, include_sensitive=private)
    folder = PROFILE + 'backups/'
    if not xbmcvfs.mkdirs(folder) and (not xbmcvfs.exists(folder)):
        raise OSError(L(31445))
    safety_path = folder + 'before-restore-{}-{}.zip'.format(datetime.now().strftime('%Y%m%d-%H%M%S'), uuid.uuid4().hex[:6])
    write_file(safety_path, safety)
    unpack(read_file(safety_path))
    for path, payload in files.items():
        parent = path.rsplit('/', 1)[0] + '/'
        if not xbmcvfs.mkdirs(parent) and (not xbmcvfs.exists(parent)):
            raise OSError(L(31448))
        write_file(path, payload)
        if read_file(path) != payload:
            raise OSError(L(31449))
    try:
        apply_settings(restored)
    except Exception:
        apply_settings({'settings': original_settings, 'addon_settings': original_addon})
        raise
    dialog.ok(L(31441), L(31446) + safety_path)
    xbmcgui.Window(10000).clearProperty('flixium.glass.ready')
    request_reload()

def main():
    if xbmc.getSkinDir().lower() != ADDON_ID.lower():
        return
    home = xbmcgui.Window(10000)
    if home.getProperty('flixium.backup.running'):
        return
    home.setProperty('flixium.backup.running', 'true')
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'restore':
            restore()
        else:
            backup()
    except (OSError, ValueError, TypeError, RuntimeError, ET.ParseError, zipfile.BadZipFile) as error:
        xbmcgui.Dialog().ok(L(31450), str(error))
    finally:
        home.clearProperty('flixium.backup.running')
if __name__ == '__main__':
    main()
