"""Style native context actions and manage separate movie and TV lists."""

from flixium_localization import localize as L
import json
import os
import sys
import time

import xbmc
import xbmcgui
import xbmcvfs

sys.path.insert(0, os.path.join(xbmcvfs.translatePath("special://skin/"), "resources", "lib"))
import my_list

HOME_VIDEO_WIDGET_IDS = frozenset(base + slot * 10 + variant
                                 for base in (5800, 5900)
                                 for slot in range(6) for variant in (0, 1)).union(range(18011, 18062, 10))


def selected_identity():
    """Read Home's retained widget identity, rather than dialog ListItem."""
    if xbmcgui.getCurrentWindowId() == 10000:
        home = xbmcgui.Window(10000)
        control_id = home.getFocusId()
        if control_id in HOME_VIDEO_WIDGET_IDS:
            try:
                # Both ListItem labels and Python's native ControlList wrappers
                # lose the underlying selection in a modal dialog. Home's
                # metadata service retains it before the dialog takes focus.
                prefix = "flixium.widgets.{}.".format(control_id)
                item_id = home.getProperty(prefix + "itemid")
                kind = home.getProperty(prefix + "kind")
                if item_id.isdigit() and kind:
                    return item_id, kind
            except (RuntimeError, TypeError):
                pass
    return xbmc.getInfoLabel("ListItem.DBID"), xbmc.getInfoLabel("ListItem.DBType")


def saved_identity(item_id, kind):
    # Episode widgets belong to a show: use its poster and save the series,
    # while leaving Kodi's native episode playback/information actions intact.
    if kind == "episode" and item_id.isdigit():
        request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetEpisodeDetails",
                   "params": {"episodeid": int(item_id), "properties": ["tvshowid"]}}
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
        show_id = response.get("result", {}).get("episodedetails", {}).get("tvshowid", -1)
        if show_id > 0:
            return str(show_id), "tvshow"
    return item_id, kind

def list_path(kind):
    filename = "my_list_tvshows.json" if kind == "tvshow" else "my_list.json"
    return xbmcvfs.translatePath("special://profile/addon_data/skin.flixium/" + filename)


def item_details(item_id, kind):
    method, key = {"movie": ("Movie", "movie"), "tvshow": ("TVShow", "tvshow")}[kind]
    request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.Get" + method + "Details",
               "params": {key + "id": int(item_id), "properties": ["file", "title", "art"]}}
    response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    return response.get("result", {}).get(key + "details", {})


def continue_widget():
    """Only offer dismissal on an actual Continue watching Home row."""
    if xbmcgui.getCurrentWindowId() != 10000:
        return False
    control_id = xbmcgui.Window(10000).getFocusId()
    for section, base, configured in (("movies", 5801, "Flixium.Widgets.Configured"),
                                       ("tvshows", 5901, "Flixium.Widgets.Configured"),
                                       ("mylist", 18011, "Flixium.Widgets.mylist.Configured")):
        if control_id not in range(base, base + 60, 10):
            continue
        slot = (control_id - base) // 10 + 1
        if not xbmc.getCondVisibility("Skin.HasSetting({})".format(configured)):
            return slot == 1
        key = "Flixium.Widgets.{}.{}.".format(section, slot)
        widget_id = xbmc.getInfoLabel("Skin.String({}Id)".format(key))
        path = xbmc.getInfoLabel("Skin.String({}Path)".format(key))
        return widget_id == "continue" or path in (
            "special://skin/playlists/widgets/{}_continue.xsp".format(section),
            "plugin://skin.flixium/?action=continue&media=" + section,
            "plugin://skin.flixium/?action=saved&view=continue")
    return False


def prepare():
    window = xbmcgui.Window(10106)
    window.clearProperty("flixium.context.ready")
    # Resolve the selected library item before moving focus into the dialog.
    item_id, kind = saved_identity(*selected_identity())
    has_poster = kind in ("movie", "tvshow") and item_id.isdigit()
    movie = item_details(item_id, kind) if has_poster else {}
    has_poster = bool(movie.get("file"))
    removable = has_poster and continue_widget()
    window.setProperty("flixium.context.continue", "true" if removable else "false")
    window.setProperty("flixium.context.posteritem", "true" if has_poster else "false")
    window.setProperty("flixium.context.itemid", item_id if has_poster else "")
    window.setProperty("flixium.context.mediatype", kind if has_poster else "")
    window.setProperty("flixium.context.poster", movie.get("art", {}).get("poster", "DefaultVideo.png"))
    if has_poster:
        saved = my_list.contains(my_list.load(list_path(kind)), movie)
        window.setProperty("flixium.context.listlabel", L(31458) if saved else L(31459))
    buttons = []
    for control_id in range(1001, 1257):
        try:
            button = window.getControl(control_id)
        except (RuntimeError, TypeError):
            break
        button.setVisibleCondition("true")
        buttons.append(control_id)
    if has_poster:
        # Native actions keep their original IDs and handlers. Place the skin's
        # action after Information, and make remote navigation follow that order.
        information = xbmc.getLocalizedString(19033)
        insert_at = next((i + 1 for i, cid in enumerate(buttons)
                          if window.getControl(cid).getLabel() == information), len(buttons))
        custom = [990] + ([991] if removable else [])
        order = buttons[:insert_at] + custom + buttons[insert_at:]
        original = custom + buttons
        for index, cid in enumerate(order):
            control = window.getControl(cid)
            offset = (index - original.index(cid)) * 68
            control.setAnimations([("Conditional", "effect=slide start=0,{} end=0,{} time=0 condition=true".format(offset, offset))])
            control.controlUp(window.getControl(order[index - 1]))
            control.controlDown(window.getControl(order[(index + 1) % len(order)]))
    height = min(900, (len(buttons) + int(has_poster) + int(removable)) * 68 - 4)
    # Reference poster dimensions: 480 x 720, inset in its Flixium panel.
    panel_height = max(744, height + 24) if has_poster else height + 24
    poster_width = 504 if has_poster else 0
    panel_width = 474 + poster_width
    left = int((1920 - panel_width) / 2)
    top = int((1080 - panel_height) / 2)
    panel = window.getControl(951)
    panel.setPosition(left, top)
    panel.setWidth(panel_width)
    panel.setHeight(panel_height)
    # Let Kodi apply the native control changes before revealing the popup.
    monitor = xbmc.Monitor()
    if monitor.waitForAbort(0.05) or not xbmc.getCondVisibility("Window.IsActive(contextmenu)"):
        return
    # Focus must settle while the whole popup (including its dimmer) is still
    # transparent, so it cannot change the highlight during the opening fade.
    if buttons:
        window.setFocus(window.getControl(buttons[0]))
    elif has_poster:
        window.setFocus(window.getControl(990))
    if monitor.waitForAbort(0.05) or not xbmc.getCondVisibility("Window.IsActive(contextmenu)"):
        return
    window.setProperty("flixium.context.ready", "true")


def toggle(item_id, kind="movie"):
    movie = item_details(item_id, kind)
    if not movie.get("file"):
        raise ValueError(L(31729))
    from flixium_my_list import toggle_entry
    toggle_entry(movie, kind)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 3 and sys.argv[1] == "dismiss":
            from continue_runtime import remove
            remove(sys.argv[2], sys.argv[3])
        elif len(sys.argv) > 2 and sys.argv[1] == "toggle":
            toggle(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "movie")
        else:
            prepare()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as error:
        xbmc.log("Flixium context menu: {}".format(error), xbmc.LOGERROR)
        if len(sys.argv) > 1:
            xbmcgui.Dialog().notification(L(31241), L(31460), xbmcgui.NOTIFICATION_ERROR)
        else:
            # Keep native actions usable if artwork or profile data cannot be read.
            xbmcgui.Window(10106).setProperty("flixium.context.ready", "true")
