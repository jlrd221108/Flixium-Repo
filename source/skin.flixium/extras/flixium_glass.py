"""Enable/prepare glass only on explicit changes or startup; no polling."""

from flixium_localization import localize as L
import importlib.util
import os
import json
from pathlib import Path
import sys
import xbmc
from flixium_reload import request_reload
import xbmcaddon
import xbmcgui
import xbmcvfs
PREFIX = 'Flixium.Glass.'

def get(key):
    return xbmc.getInfoLabel('Skin.String(' + key + ')')

def setting(key, value):
    xbmc.executebuiltin('Skin.SetString({},{})'.format(key, value))

def active():
    return xbmc.getCondVisibility('Skin.HasSetting(Flixium.Glass.Enabled) + System.AddonIsEnabled(script.flixium.helper)')

def prepare(force=False):
    if not force and (not active()):
        return False
    addon = xbmcaddon.Addon('script.flixium.helper')
    path = xbmcvfs.translatePath(os.path.join(addon.getAddonInfo('path'), 'resources', 'lib', 'glass_cache.py'))
    spec = importlib.util.spec_from_file_location('flixium_glass_cache', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    palettes = json.loads(Path(__file__).with_name('glass-palettes.json').read_text())
    try:
        index = max(0, min(len(palettes) - 1, int(get('Flixium.Theme.Scheme') or '0')))
    except ValueError:
        index = 0
    palette = dict(palettes[index])
    override = get(PREFIX + 'BackgroundPreset')
    if override:
        try:
            palette['background'] = palettes[int(override)]['background']
        except (ValueError, IndexError):
            pass
    config = module.configuration(get('Flixium.Theme.Window'), get('Flixium.Theme.Highlight'), get('Flixium.Theme.Dialog'), get(PREFIX + 'BackgroundResolution'), get(PREFIX + 'PanelResolution'), rounded=xbmc.getCondVisibility('Skin.HasSetting(Flixium.ExtraRounded)'), palette=palette, unrounded=xbmc.getCondVisibility('Skin.HasSetting(Flixium.Unrounded)'))
    cache = xbmcvfs.translatePath('special://profile/addon_data/script.flixium.helper/glass_cache')
    paths, generated = module.ensure_cache(cache, config)
    current = module.configuration(get('Flixium.Theme.Window'), get('Flixium.Theme.Highlight'), get('Flixium.Theme.Dialog'), get(PREFIX + 'BackgroundResolution'), get(PREFIX + 'PanelResolution'), rounded=xbmc.getCondVisibility('Skin.HasSetting(Flixium.ExtraRounded)'), palette=palette, unrounded=xbmc.getCondVisibility('Skin.HasSetting(Flixium.Unrounded)'))
    if module.signature(current) != module.signature(config):
        return False
    changed = generated
    for key, name in (('Gradient', 'gradient'), ('Panel', 'panel'), ('Dialog', 'dialog'), ('Sidebar', 'sidebar')):
        if get(PREFIX + key) != paths[name]:
            setting(PREFIX + key, paths[name])
            changed = True
    setting(PREFIX + 'Tint', 'FF' + palette['glass'])
    home = xbmcgui.Window(10000)
    home.setProperty('flixium.glass.ready', 'true')
    home.setProperty('flixium.glass.profile', xbmc.getInfoLabel('System.ProfileName'))
    return changed

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'prepare'
    try:
        if action == 'prepare':
            if prepare():
                xbmc.sleep(100)
                request_reload()
            return
        if action == 'toggle':
            if active():
                xbmc.executebuiltin('Skin.Reset(Flixium.Glass.Enabled)')
            else:
                prepare(True)
                xbmc.executebuiltin('Skin.SetBool(Flixium.Glass.Enabled)')
            focus = 9060
        elif action == 'backgroundpreset':
            palettes = json.loads(Path(__file__).with_name('glass-palettes.json').read_text())
            choices = [xbmcgui.ListItem(label=L(31220), label2=L(31470))]
            for index, palette in enumerate(palettes):
                item = xbmcgui.ListItem(label=palette['name'], label2=L(31471))
                item.setArt({'thumb': 'special://skin/extras/themes/glass-background-{}.png'.format(index)})
                choices.append(item)
            current = get(PREFIX + 'BackgroundPreset')
            selected = int(current) + 1 if current.isdigit() and int(current) < len(palettes) else 0
            choice = xbmcgui.Dialog().select(L(31288), choices, preselect=selected, useDetails=True)
            if choice < 0:
                return
            if choice:
                setting(PREFIX + 'BackgroundPreset', str(choice - 1))
                setting(PREFIX + 'BackgroundPresetName', palettes[choice - 1]['name'])
            else:
                xbmc.executebuiltin('Skin.Reset(' + PREFIX + 'BackgroundPreset)')
                xbmc.executebuiltin('Skin.Reset(' + PREFIX + 'BackgroundPresetName)')
            xbmc.sleep(100)
            prepare()
            focus = 9063
        elif action in ('background', 'panels'):
            key = PREFIX + ('BackgroundResolution' if action == 'background' else 'PanelResolution')
            options = ['720', '1080', '1440']
            current = get(key) or '1080'
            index = xbmcgui.Dialog().select(L(31299) if action == 'background' else L(31300), [L(31472), L(31473), L(31474)], preselect=options.index(current) if current in options else 1)
            if index < 0:
                return
            setting(key, options[index])
            xbmc.sleep(100)
            prepare()
            focus = 9061 if action == 'background' else 9062
        else:
            return
        from flixium_theme import refresh
        refresh(focus, prepare_glass=False)
    except Exception as error:
        xbmc.log('Flixium glass: {}'.format(error), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(L(31468), L(31469))
if __name__ == '__main__':
    main()
