"""Leave Kodi's Interface rows visible, disabling the skin-managed choices."""

import uuid
import xbmc
import xbmcgui

PAGE = 'Window.IsActive(interfacesettings) + Container(3).Position(0)'
TARGETS = (-177, -176, -175)  # Themes, Colours, Fonts in Kodi's Skin category.
SESSION = 'flixium.interface.disable_session'


def disable_options():
    if not xbmc.getCondVisibility(PAGE + ' + !System.HasActiveModalDialog'):
        return
    if xbmc.getInfoLabel('Control.GetLabel(20)') == xbmc.getLocalizedString(10036):
        return  # Basic level does not create these three rows.
    # A fresh Window proxy for each pass: never cache generated controls across
    # category changes, settings-level changes or ReloadSkin.
    window = xbmcgui.Window(10032)
    for control_id in TARGETS:
        try:
            control = window.getControl(control_id)
            control.setEnableCondition('false')
            control.setEnabled(False)
        except RuntimeError:
            pass  # Kodi may still be constructing this category.


def main():
    home = xbmcgui.Window(10000)
    if home.getProperty(SESSION):
        return
    token = uuid.uuid4().hex
    home.setProperty(SESSION, token)
    monitor = xbmc.Monitor()
    try:
        while xbmc.getCondVisibility('Window.IsActive(interfacesettings)') and not monitor.abortRequested():
            disable_options()
            if monitor.waitForAbort(.25):
                break
    finally:
        if home.getProperty(SESSION) == token:
            home.clearProperty(SESSION)


if __name__ == '__main__':
    main()
