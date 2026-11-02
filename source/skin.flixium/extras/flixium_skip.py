"""Simple ten-second video seeking, without preview generation."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import xbmc
import xbmcvfs


def main():
    argument = sys.argv[1] if len(sys.argv) > 1 else '10'
    path = Path(xbmcvfs.translatePath('special://profile/keymaps/flixium-seek.xml'))
    if argument == 'uninstall':
        if path.exists():
            path.unlink()
            xbmc.executebuiltin('Action(reloadkeymaps)')
        return
    if argument == 'install':
        root = ET.Element('keymap')
        full = ET.SubElement(root, 'FullscreenVideo')
        for device in ('keyboard', 'remote', 'gamepad'):
            keys = ET.SubElement(full, device)
            for direction, step in (('left', -10), ('right', 10)):
                name = 'dpad' + direction if device == 'gamepad' else direction
                ET.SubElement(keys, name).text = 'RunScript(special://home/addons/skin.flixium/extras/flixium_skip.py,{})'.format(step)
        text = ET.tostring(root, encoding='unicode')
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            xbmc.executebuiltin('Action(reloadkeymaps)')
        return
    step = -10 if argument.startswith('-') else 10
    player = xbmc.Player()
    if xbmc.getSkinDir() != 'skin.flixium' or not xbmc.getCondVisibility('Player.HasVideo + Player.SeekEnabled + !VideoPlayer.Content(livetv) + !VideoPlayer.Content(musicvideos)'):
        xbmc.executebuiltin('Action(StepBack)' if step < 0 else 'Action(StepForward)')
        return
    player.seekTime(min(max(0, player.getTime() + step), max(0, player.getTotalTime() - .25)))

if __name__ == '__main__':
    main()
