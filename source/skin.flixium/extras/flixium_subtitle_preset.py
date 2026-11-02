"""Prepare first-use Netflix subtitle defaults, or explicitly restore them."""

from flixium_localization import localize as L
import os
import sys

import xbmc
import xbmcgui
import xbmcvfs

sys.path.insert(0, os.path.join(xbmcvfs.translatePath("special://skin/"), "resources", "lib"))
from subtitle_appearance import NativeSettings


def main():
    automatic = "initialise" in sys.argv[1:]
    marker = "Flixium.SubtitleDefaultsApplied"
    if automatic and xbmc.getCondVisibility("Skin.HasSetting({})".format(marker)):
        return
    home = xbmcgui.Window(10000)
    if home.getProperty("flixium.subtitle_defaults_running") == "true":
        return
    home.setProperty("flixium.subtitle_defaults_running", "true")
    try:
        target = "special://home/media/Fonts/NetflixSans-Regular.otf"
        if not xbmcvfs.exists(target):
            xbmcvfs.mkdirs("special://home/media/Fonts/")
            if not xbmcvfs.copy("special://skin/fonts/NetflixSans-Regular.otf", target):
                raise ValueError(L(31736))
        settings = NativeSettings(xbmc.executeJSONRPC)
        settings.refresh()
        # Kodi's font dropdown is cached at app startup. Its dynamic string setting
        # accepts the installed family directly; don't wait for the dropdown cache.
        # Installing before playback lets Android's subtitle renderer load the font.
        settings.apply_preset(installed_font='Netflix Sans')
        xbmc.executebuiltin("Skin.SetBool({})".format(marker))
        if not automatic:
            xbmcgui.Dialog().notification(L(31385), L(31559), time=2500)
    except (ValueError, KeyError, TypeError) as error:
        if automatic:
            xbmc.log("Flixium subtitle defaults: {}".format(error), xbmc.LOGERROR)
        else:
            xbmcgui.Dialog().ok(L(31560), str(error))
    finally:
        home.clearProperty("flixium.subtitle_defaults_running")


if __name__ == "__main__":
    main()
