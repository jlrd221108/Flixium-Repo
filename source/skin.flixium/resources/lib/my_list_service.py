"""Refresh saved-list counts and opt-in watched removal on library changes."""
import os
import sys
import time
import uuid

import xbmc
import xbmcgui
import xbmcvfs

SKIN = xbmcvfs.translatePath("special://skin/")
sys.path.insert(0, os.path.join(SKIN, "extras"))
import my_list_runtime as runtime


class SavedListMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.dirty = False
        self.changed_at = 0

    def onNotification(self, sender, method, data):
        if method.startswith("AudioLibrary.") or method == "Player.OnStop":
            xbmcgui.Window(10000).setProperty("flixium.music.revision", str(time.time_ns()))
        if method.startswith("VideoLibrary.") or method in ("Player.OnStop", "Player.OnAVChange"):
            self.dirty = True
            self.changed_at = time.monotonic()


def run():
    home = xbmcgui.Window(10000)
    if home.getProperty("flixium.mylist.service"):
        return
    token = uuid.uuid4().hex
    home.setProperty("flixium.mylist.service", token)
    monitor = SavedListMonitor()
    previous = None
    profile = None
    try:
        while not monitor.abortRequested() and xbmc.getSkinDir() == "skin.flixium":
            try:
                current_profile = xbmcvfs.translatePath("special://profile/")
                if profile != current_profile:
                    from flixium_my_list import setup
                    setup()
                    profile, previous = current_profile, None
                files = [runtime.membership("movie"), runtime.membership("tvshow"), runtime.path("my_list_settings.json")]
                stamp = tuple(os.stat(path).st_mtime_ns if os.path.exists(path) else 0 for path in files)
                if stamp != previous or (monitor.dirty and time.monotonic() - monitor.changed_at > .75):
                    runtime.changed()
                    previous = tuple(os.stat(path).st_mtime_ns if os.path.exists(path) else 0 for path in files)
                    monitor.dirty = False
            except (OSError, RuntimeError, ValueError, KeyError) as error:
                xbmc.log("Flixium saved list service: {}".format(error), xbmc.LOGERROR)
                if monitor.waitForAbort(2):
                    break
            if monitor.waitForAbort(.5):
                break
    finally:
        if home.getProperty("flixium.mylist.service") == token:
            home.clearProperty("flixium.mylist.service")


if __name__ == "__main__":
    run()
