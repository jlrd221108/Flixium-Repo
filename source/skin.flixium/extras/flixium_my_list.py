"""My list settings, saved-list directory and profile migration."""

from flixium_localization import localize as L
import json
import os
import sys
import threading
import time
from urllib.parse import unquote, urlencode

import xbmc
import xbmcgui
import xbmcvfs

SKIN = xbmcvfs.translatePath("special://skin/")
sys.path.insert(0, os.path.join(SKIN, "resources", "lib"))
import my_list
import my_list_runtime as runtime


def choose(heading, labels, preselect=0):
    # Reuse Flixium's existing themed selection dialog.
    from flixium_widgets import widget_select
    return widget_select(heading, labels, preselect=preselect)


def directory(handle, query):
    import xbmcplugin
    view = query.get("view", ["all"])[0]
    media_filter = query.get("filter", ["default"])[0]
    browsing = query.get("browse", [""])[0] == "1"
    try:
        if view == "help":
            xbmcgui.Dialog().ok(L(31241), L(31501))
            xbmcplugin.endOfDirectory(handle)
            return
        runtime.refresh_state()
        items = runtime.view_items(view, media_filter, limit=0 if browsing else 30)
        xbmcplugin.setContent(handle, "tvshows" if view == "tvshows" or runtime.active_filter(media_filter) == "tvshows" else "movies")
        for item in items:
            xbmcplugin.addDirectoryItem(handle, *runtime.listitem(item))
        if browsing and not items:
            hint = xbmcgui.ListItem(L(31502), offscreen=True)
            xbmcplugin.addDirectoryItem(handle, "plugin://skin.flixium/?action=saved&view=help", hint, False)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        xbmc.log("Flixium My list: {}".format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)


def restore_removed():
    try:
        with open(runtime.path("my_list_undo.json"), encoding="utf-8") as stream:
            undo = json.load(stream)
        if time.time() > undo["expires"]:
            return False
        rows = my_list.load(runtime.membership(undo["kind"]))
        if not my_list.contains(rows, undo["entry"]):
            rows.insert(min(undo["index"], len(rows)), undo["entry"])
            my_list.write(runtime.membership(undo["kind"]), rows)
        os.remove(runtime.path("my_list_undo.json"))
        runtime.changed()
        return True
    except (OSError, ValueError, KeyError):
        return False


class UndoDialog(xbmcgui.WindowXMLDialog):
    def onInit(self):
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.expire, daemon=True)
        self.worker.start()

    def expire(self):
        if not self.stop.wait(4):
            self.close()

    def onClick(self, control_id):
        if control_id == 201:
            restore_removed()
        self.close()

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            self.close()


def toggle_entry(item, kind):
    prefs = runtime.preferences()
    rows = my_list.load(runtime.membership(kind))
    previous = next(((i, row) for i, row in enumerate(rows) if row["file"] == item["file"]), None)
    added = my_list.toggle(runtime.membership(kind), item, id_key=kind + "id")
    if not added and previous:
        my_list.write(runtime.path("my_list_undo.json"), {"kind": kind, "entry": previous[1],
                       "index": previous[0], "expires": time.time() + 30})
    runtime.changed()
    if prefs["notifications"]:
        if added:
            xbmcgui.Dialog().notification(L(31241), L(31503), item.get("art", {}).get("poster", ""), 2000, False)
        else:
            xbmc.Monitor().waitForAbort(.15)
            dialog = UndoDialog("script-FlixiumListUndo.xml", SKIN, "Default", "1080i")
            dialog.doModal()
            dialog.stop.set()
            dialog.worker.join(.2)
            del dialog


def settings_dialog(setting=None):
    choices = {
        "filter": [("all", L(31504)), ("movies", L(31233)), ("tvshows", L(31505))],
        "sort": [("added", L(31506)), ("alphabetical", L(31507)), ("unwatched", L(31508))],
        "watched": [("show", L(31509)), ("hide", L(31510)), ("remove", L(31511))],
    }
    while True:
        prefs = runtime.preferences()
        title = lambda key: next(label for value, label in choices[key] if value == prefs[key])
        # Preserve IDs used by skin actions; retired settings are ignored.
        labels = {0: L(31788).format(title("filter")),
                  1: L(31789).format(title("sort")),
                  2: L(31790).format(title("watched")),
                  5: L(31791).format(L(31517) if prefs["notifications"] else L(31429)),
                  7: L(31500), 8: L(31307)}
        actions = tuple(labels)
        if setting is not None:
            selected = setting
        else:
            row = choose(L(31516), list(labels.values()))
            selected = actions[row] if row >= 0 else -1
        if selected not in labels:
            return
        if selected in (0, 1, 2):
            key = ("filter", "sort", "watched")[selected]
            values = choices[key]
            choice = choose({0: L(31302), 1: L(31792), 2: L(31304)}[selected], [label for _, label in values],
                            next(i for i, (value, _) in enumerate(values) if value == prefs[key]))
            if choice < 0:
                if setting is not None:
                    return
                continue
            prefs[key] = values[choice][0]
        elif selected == 5:
            prefs["notifications"] = not prefs["notifications"]
        elif selected == 7:
            if not restore_removed():
                xbmcgui.Dialog().notification(L(31519), L(31520), time=2000, sound=False)
            if setting is not None:
                return
            continue
        else:
            prefs = dict(my_list.DEFAULTS)
        my_list.write(runtime.path("my_list_settings.json"), prefs)
        runtime.changed()
        if setting is not None:
            return


def publish_section(section, rows):
    from home_widgets import PREFIX, MAX_WIDGETS, encode, widget_settings
    values = {"Config": encode(rows), "Count": str(len(rows))}
    for slot in range(1, MAX_WIDGETS + 1):
        entry = rows[slot - 1] if slot <= len(rows) else {"id": "", "path": "", "title": ""}
        appearance = widget_settings(section, entry)
        for key, value in (("Id", entry["id"]), ("Path", entry["path"]), ("Title", entry["title"]),
                           ("Artwork", appearance["artwork"]), ("Limit", str(appearance["limit"] or "")),
                           ("Progress", "on" if appearance["progress"] else "off")):
            values["{}.{}".format(slot, key)] = value
    for key, value in values.items():
        name = "{}.{}.{}".format(PREFIX, section, key)
        if value:
            xbmc.executebuiltin('Skin.SetString({},"{}")'.format(name, value))
        else:
            xbmc.executebuiltin("Skin.Reset({})".format(name))


def setup():
    if xbmc.getCondVisibility("Skin.HasSetting(Flixium.MyList.MenuMigrated)"):
        runtime.refresh_state()
        return
    from home_widgets import normalise, decode, PREFIX
    # Keep all saved membership files; only move the old widgets out of Movies/TV.
    for section in ("movies", "tvshows"):
        saved = xbmc.getInfoLabel("Skin.String({}.{}.Config)".format(PREFIX, section))
        if saved:
            raw = json.loads(unquote(saved))
            if any(row.get("id") == "mylist" for row in raw):
                rows = normalise(section, [row for row in raw if row.get("id") != "mylist"])
                publish_section(section, rows)
    saved = xbmc.getInfoLabel("Skin.String({}.mylist.Config)".format(PREFIX))
    publish_section("mylist", decode("mylist", saved))
    xbmc.executebuiltin("Skin.SetBool(Flixium.Widgets.mylist.Configured)")
    if xbmc.getCondVisibility("Skin.HasSetting(Flixium.HomeMenu.Configured)"):
        from home_menu import decode as menu_decode, settings, new_item, MAX_ITEMS
        from skin_backup import commands
        rows = menu_decode(xbmc.getInfoLabel("Skin.String(Flixium.HomeMenu.Config)"))
        if not any(row["section"].startswith("mylist") for row in rows) and len(rows) < MAX_ITEMS:
            index = next((i + 1 for i, row in enumerate(rows) if row["section"] == "tvshows"), len(rows))
            rows.insert(index, new_item("flixium_mylist", L(31241), "mylist"))
            for command in commands(settings(rows)):
                xbmc.executebuiltin(command)
    xbmc.executebuiltin("Skin.SetBool(Flixium.MyList.MenuMigrated)")
    runtime.changed()


if __name__ == "__main__":
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "settings"
        if action == "setup":
            setup()
        elif action == "refresh":
            runtime.refresh_state()
        elif action == "setting":
            selected = int(sys.argv[2])
            if not 0 <= selected <= 8:
                raise ValueError(L(31733))
            settings_dialog(selected)
        elif action == "open":
            media_filter = runtime.active_filter(sys.argv[2] if len(sys.argv) > 2 else "default")
            url = "plugin://skin.flixium/?" + urlencode({"action": "saved", "view": "all", "filter": media_filter, "browse": "1"})
            xbmc.executebuiltin('ActivateWindow(Videos,"{}",return)'.format(url))
        else:
            settings_dialog()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        xbmc.log("Flixium My list settings: {}".format(error), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(L(31241), L(31518) + str(error))
