"""On-demand Flixium palette selection; no service, reload or artwork processing."""

from flixium_localization import localize as L
import re
import json
from pathlib import Path
import sys
import xbmc
from flixium_reload import request_reload
import xbmcgui
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'resources' / 'lib'))
import colour_presets
PREFIX = 'Flixium.Theme.'
PRESETS = ((L(31311), None, None, None), (L(31561), '1E1E1E', 'E9EEF5', '202124'), (L(31562), '17232E', '4DD9FF', '152735'), (L(31563), '241D30', 'BA95FF', '2A2038'), (L(31564), '162923', '64E6B0', '17312E'), (L(31565), '2B1B21', 'FF637C', '341D2B'), (L(31566), '28221A', 'E7C58B', '30271E'))
KEYS = ('Window', 'Panel', 'Card', 'Focus', 'Highlight', 'Dialog', 'DialogHeader', 'Scheme', 'Name', 'WindowCustom', 'HighlightCustom', 'DialogCustom')
COLOURS = ((L(31567), '252525'), (L(31568), '32363C'), (L(31569), '17232E'), (L(31570), '241D30'), (L(31571), '17312E'), (L(31572), '341D2B'), (L(31573), '30271E'), (L(31574), 'E9EEF5'), (L(31575), '4DD9FF'), (L(31576), 'BA95FF'), (L(31577), '64E6B0'), (L(31578), 'FF637C'), (L(31579), 'E7C58B'), (L(31580), '72ACFF'), (L(31581), 'FF967D'))

def presets():
    if xbmc.getCondVisibility('Skin.HasSetting(Flixium.Glass.Enabled)'):
        rows = json.loads(Path(__file__).with_name('glass-palettes.json').read_text())
        return tuple(((p['name'], p['window'], p['highlight'], p['dialog']) if i else (p['name'], None, None, None) for i, p in enumerate(rows)))
    return PRESETS

def get(key):
    return xbmc.getInfoLabel('Skin.String(' + PREFIX + key + ')')

def set_value(key, value):
    if value:
        xbmc.executebuiltin('Skin.SetString({},"{}")'.format(PREFIX + key, value), True)
    else:
        xbmc.executebuiltin('Skin.Reset({})'.format(PREFIX + key), True)


def user_presets():
    return colour_presets.decode(get('UserPresets'))


def current_colours():
    values = {key: get(key) for key in colour_presets.KEYS if not key.startswith('Background')}
    for key in ('BackgroundPreset', 'BackgroundPresetName'):
        values[key] = xbmc.getInfoLabel('Skin.String(Flixium.Glass.' + key + ')')
    return colour_presets.palette(values)


def apply_user_preset(row):
    values = colour_presets.palette(row['colours'])
    for key in KEYS:
        set_value(key, values.get(key, ''))
    for key in ('BackgroundPreset', 'BackgroundPresetName'):
        value = values[key]
        xbmc.executebuiltin('Skin.SetString(Flixium.Glass.{},"{}")'.format(key, value) if value
                           else 'Skin.Reset(Flixium.Glass.{})'.format(key), True)
    set_value('UserPreset', row['id'])
    set_value('Name', row['name'])


def manage_user_presets(action):
    dialog = xbmcgui.Dialog()
    rows = user_presets()
    if action == 'save':
        label = dialog.input(L(31296), defaultt=L(31588))
        if not label.strip():
            return
        rows = colour_presets.save(rows, label, current_colours())
        set_value('UserPresets', colour_presets.encode(rows))
        apply_user_preset(rows[-1])
        refresh(9184)
        return
    if not rows:
        dialog.ok(L(31297), L(31582))
        return
    index = dialog.select(L(31297), [row['name'] for row in rows])
    if index < 0:
        return
    row = rows[index]
    selected = dialog.select(row['name'], [L(31583), L(31584), L(31585), L(31586)])
    if selected < 0:
        return
    if selected == 0:
        apply_user_preset(row)
        refresh(9185)
        return
    if selected == 1:
        label = dialog.input(L(31587), defaultt=row['name'])
        if not label.strip():
            return
        rows = colour_presets.save(rows, label, row['colours'], row['id'])
        if get('UserPreset') == row['id']:
            set_value('Name', colour_presets.name(label) + (' (custom)' if get('Name').endswith(' (custom)') else ''))
    elif selected == 2:
        if not dialog.yesno(L(31590), L(31595).format(row['name'])):
            return
        rows = colour_presets.save(rows, row['name'], current_colours(), row['id'])
        apply_user_preset(rows[index])
    elif selected == 3:
        if not dialog.yesno(L(31592), L(31596).format(row['name'])):
            return
        rows = [saved for saved in rows if saved['id'] != row['id']]
        if get('UserPreset') == row['id']:
            set_value('UserPreset', '')
            set_value('Name', L(31593))
    set_value('UserPresets', colour_presets.encode(rows))
    refresh(9185)

def rgb(value):
    return tuple((int(value[-6:][i:i + 2], 16) for i in (0, 2, 4)))

def hex_rgb(values):
    return 'FF' + ''.join(('{:02X}'.format(max(0, min(255, round(v)))) for v in values))

def surface(value):
    parts = rgb(value)
    scale = min(1, 64 / max(max(parts), 1))
    return hex_rgb([v * scale for v in parts])

def apply_component(component, value, custom=False):
    if component == 'window':
        base = hex_rgb(rgb(value)) if custom else surface(value)
        set_value('Window', base)
        for key, lift in (('Panel', 7), ('Card', 13)):
            set_value(key, hex_rgb([v + lift for v in rgb(base)]))
    elif component == 'highlight':
        set_value('Highlight', hex_rgb(rgb(value)))
        set_value('Focus', hex_rgb([v * 0.25 + 22 for v in rgb(value)]))
    elif component == 'dialog':
        base = hex_rgb(rgb(value)) if custom else surface(value)
        set_value('Dialog', base)
        set_value('DialogHeader', hex_rgb([v * 0.78 for v in rgb(base)]))

def scheme_index():
    try:
        return max(0, min(len(presets()) - 1, int(get('Scheme') or '0')))
    except ValueError:
        return 0

def apply_preset(index):
    name, window, highlight, dialog = presets()[index]
    for key in KEYS:
        set_value(key, '')
    set_value('UserPreset', '')
    if index:
        for component, value in (('window', window), ('highlight', highlight), ('dialog', dialog)):
            apply_component(component, value)
        set_value('Scheme', str(index))
        set_value('Name', name)

def refresh(focus, prepare_glass=True):
    xbmc.sleep(100)
    if prepare_glass:
        from flixium_glass import prepare
        prepare()
        xbmc.sleep(100)
    request_reload(focus)

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'scheme'
    dialog = xbmcgui.Dialog()
    if action == 'scheme':
        labels = []
        for name, window, highlight, popup in presets():
            item = xbmcgui.ListItem(label=name, label2=L(31591))
            item.setArt({'thumb': 'special://skin/extras/themes/{}scheme-{}.png'.format('glass-' if presets() != PRESETS else '', len(labels))})
            labels.append(item)
        saved = user_presets()
        for row in saved:
            labels.append(xbmcgui.ListItem(label=row['name'], label2=L(31594)))
        current = next((len(presets()) + i for i, row in enumerate(saved) if row['id'] == get('UserPreset')), scheme_index())
        index = dialog.select(L(31286), labels, preselect=current, useDetails=True)
        if index >= 0:
            if index < len(presets()):
                apply_preset(index)
            else:
                apply_user_preset(saved[index - len(presets())])
            refresh(9050)
    elif action in ('save', 'manage'):
        manage_user_presets(action)
    elif action == 'reset':
        saved = next((row for row in user_presets() if row['id'] == get('UserPreset')), None)
        if saved:
            apply_user_preset(saved)
        else:
            apply_preset(scheme_index())
        refresh(9054)
    elif action == 'round':
        current = 0 if xbmc.getCondVisibility('Skin.HasSetting(Flixium.Unrounded)') else 2 if xbmc.getCondVisibility('Skin.HasSetting(Flixium.ExtraRounded)') else 1
        index = dialog.select(L(31289), [L(31360), L(31362), L(31361)], preselect=current)
        if index < 0:
            return
        for key, enabled in (('Flixium.Unrounded', index == 0), ('Flixium.ExtraRounded', index == 2)):
            xbmc.executebuiltin('Skin.{}({})'.format('SetBool' if enabled else 'Reset', key), True)
        refresh(9055)
    elif action in ('window', 'highlight', 'dialog'):
        title = {'window': L(31292), 'highlight': L(31293), 'dialog': L(31294)}[action]
        from flixium_colour_picker import choose
        current = get(action.title()) or {'window': 'FF1E1E1E', 'highlight': 'FFFFFFFF', 'dialog': 'FF252525'}[action]
        value = choose(title, current)
        if value is None:
            return
        apply_component(action, value, custom=True)
        set_value(action.title() + L(31312), 'true')
        saved = next((row for row in user_presets() if row['id'] == get('UserPreset')), None)
        set_value('Name', (saved['name'] if saved else presets()[scheme_index()][0]) + ' (custom)')
        refresh({'window': 9051, 'highlight': 9052, 'dialog': 9053}[action])
if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        xbmcgui.Dialog().ok(L(31589), str(error))
