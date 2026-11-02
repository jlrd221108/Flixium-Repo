"""Window-scoped, once-per-source decoder notice for Flix Pictures."""

from flixium_localization import localize as L
import json
import os
import sys
import uuid

import xbmc
import xbmcgui
import xbmcvfs

sys.path.insert(0, os.path.join(xbmcvfs.translatePath("special://skin/"), "resources", "lib"))
from picture_decoders import OFFICIAL_DECODERS, find_source, notice, scan_source, source_key

RUNNING = "flixium.pictures.decoder_notice.running"
MARKER = "Flixium.Pictures.DecoderNotice."


def get_sources():
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "Files.GetSources",
        "params": {"media": "pictures"}})))
    if "error" in response:
        raise ValueError(L(31735))
    return response.get("result", {}).get("sources", [])


def run():
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    # A lease lets a fresh onload replace a scanner left running by ReloadSkin.
    token = uuid.uuid4().hex
    home.setProperty(RUNNING, token)
    attempted, pending = set(), {}
    previous_folder, sources = None, []

    def active():
        return (not monitor.abortRequested() and home.getProperty(RUNNING) == token
                and xbmc.getSkinDir() == "skin.flixium"
                and xbmc.getCondVisibility("Window.IsActive(pictures)"))

    def current_source():
        return find_source(xbmc.getInfoLabel("Container.FolderPath"), sources)

    # MyPics onload may precede activation of the window by a few frames.
    try:
        if monitor.waitForAbort(.5):
            return
        while active():
            if not xbmc.getCondVisibility("Control.IsVisible(61)"):
                if monitor.waitForAbort(.5):
                    break
                continue
            folder = xbmc.getInfoLabel("Container.FolderPath")
            if folder != previous_folder:
                previous_folder = folder
                try:
                    sources = get_sources()
                except (ValueError, TypeError):
                    sources = []
            source = current_source()
            if source:
                key = source_key(source)
                marker = MARKER + key
                warned = xbmc.getCondVisibility("Skin.HasSetting({})".format(marker))
                if not warned and key not in attempted:
                    def cancelled():
                        selected = current_source()
                        return (not active() or not xbmc.getCondVisibility("Control.IsVisible(61)")
                                or selected is None or source_key(selected) != key)
                    try:
                        found = scan_source(source, xbmcvfs.listdir, cancelled)
                    except Exception as error:
                        # Do not log source URLs: network paths can contain credentials.
                        xbmc.log("Flixium picture decoder scan failed ({})".format(type(error).__name__), xbmc.LOGWARNING)
                        found = set()
                    if found is not None:
                        attempted.add(key)
                        if found:
                            pending[key] = found
                if (not warned and key in pending and active()
                        and xbmc.getCondVisibility("Control.IsVisible(61)")
                        and not xbmc.getCondVisibility("System.HasActiveModalDialog")):
                    selected = current_source()
                    if selected is not None and source_key(selected) == key:
                        # Remember even a dismissal, before opening another window.
                        xbmc.executebuiltin("Skin.SetBool({})".format(marker))
                        found = pending.pop(key)
                        accepted = xbmcgui.Dialog().yesno(L(31528), notice(found),
                                                         nolabel=L(31529), yeslabel=L(31530))
                        if accepted:
                            xbmc.executebuiltin("ActivateWindow(addonbrowser,{},return)".format(OFFICIAL_DECODERS))
            if monitor.waitForAbort(.5):
                break
    finally:
        if home.getProperty(RUNNING) == token:
            home.clearProperty(RUNNING)


if __name__ == "__main__":
    run()
