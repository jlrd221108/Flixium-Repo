"""Keep the settings mouse wheel tied to focus, rather than scrolling it away."""
from pathlib import Path
import sys

import xbmc
import xbmcvfs


BACK = 'RunScript(special://skin/extras/flixium_settings_navigation.py,back)'
KEYMAP = ('<keymap><SkinSettings><mouse><wheelup>Up</wheelup><wheeldown>Down</wheeldown></mouse>'
          '<keyboard><escape>{0}</escape><backspace>{0}</backspace></keyboard>'
          '<remote><back>{0}</back></remote><gamepad><b>{0}</b></gamepad></SkinSettings></keymap>').format(BACK)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'back':
        page = xbmc.getInfoLabel('Window(home).Property(Flixium.Customisation.Page)')
        if xbmc.getCondVisibility('Container(9000).HasFocus(103)') and page in ('home', 'appearance', 'colours', 'quality'):
            focus = 9170 + ('home', 'appearance', 'colours', 'quality').index(page)
            xbmc.executebuiltin('ClearProperty(Flixium.Customisation.Page,home)', True)
            xbmc.executebuiltin('SetFocus({})'.format(focus))
        else:
            xbmc.executebuiltin('Action(previousmenu)')
        return
    path = Path(xbmcvfs.translatePath('special://profile/keymaps/flixium-settings-navigation.xml'))
    install = len(sys.argv) > 1 and sys.argv[1] == 'install'
    if install:
        if xbmc.getSkinDir() != 'skin.flixium' or not xbmc.getCondVisibility('Window.IsActive(skinsettings)'):
            return
        if path.exists() and path.read_text(encoding='utf-8') == KEYMAP:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(KEYMAP, encoding='utf-8')
    else:
        # A delayed unload from the previous visit must not undo a new visit.
        if xbmc.getSkinDir() == 'skin.flixium' and xbmc.getCondVisibility('Window.IsActive(skinsettings)'):
            return
        if not path.exists():
            return
        path.unlink()
    xbmc.executebuiltin('Action(reloadkeymaps)')


if __name__ == '__main__':
    main()
