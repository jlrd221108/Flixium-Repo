"""Remote-friendly widget editor and the Next episode library source."""

from flixium_localization import localize as L
import json
import os
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, parse_qs

import xbmc
from flixium_reload import request_reload
import xbmcgui
import xbmcvfs

SKIN = xbmcvfs.translatePath("special://skin/")
sys.path.insert(0, os.path.join(SKIN, "resources", "lib"))
from home_widgets import (CATALOGUE, EPISODE_WIDGETS, ITEM_COUNTS, MAX_WIDGETS, PLAYLIST_TYPES, PREFIX,
                          SECTIONS, SECTION_LABELS, decode, defaults, encode,
                          next_episodes, normalise, option, widget_settings)


def widget_select(heading, items, warning="", **kwargs):
    """Scope the themed native popup to widget configuration menus."""
    home = xbmcgui.Window(10000)
    home.setProperty("flixium.widget_select", "true")
    home.setProperty("flixium.widget_select_warning", warning)
    try:
        return xbmcgui.Dialog().select(heading, items, **kwargs)
    finally:
        home.clearProperty("flixium.widget_select")
        home.clearProperty("flixium.widget_select_warning")


class WidgetEditor(xbmcgui.WindowXMLDialog):
    SECTION_CONTROLS = (100, 101, 102, 104, 105, 106)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = "movies"
        self.draft = {section: decode(section, xbmc.getInfoLabel("Skin.String({}.{}.Config)".format(PREFIX, section))) for section in SECTIONS}
        self.applied = False
        self.move_original = None
        self.move_index = 0
        self.selected = 0
        try:
            saved = json.loads(unquote(xbmc.getInfoLabel(
                "Skin.String({}.GlobalAppearance)".format(PREFIX))))
        except (ValueError, TypeError):
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        self.has_global_appearance = bool(saved)
        self.global_settings = widget_settings("movies", dict(saved, id="continue"))

    def onInit(self):
        self.render()
        self.setFocusId(100)
        self.setProperty("ready", "true")

    def render(self, selected=0):
        rows = self.draft[self.section]
        self.setProperty("section", SECTION_LABELS[SECTIONS.index(self.section)])
        self.setProperty("count", L(31624).format(len(rows), MAX_WIDGETS))
        can_add = len(rows) < MAX_WIDGETS
        if self.section in ("programs", "videos"):
            used = {entry["id"] for entry in rows}
            can_add = can_add and any(entry["id"] not in used and
                (entry["id"] != "android" or xbmc.getCondVisibility("System.Platform.Android"))
                for entry in CATALOGUE[self.section])
        self.setProperty("canadd", "true" if can_add else "false")
        self.setProperty("category", self.section)
        self.setProperty("hasrows", "true" if rows else "false")
        self.selected = max(0, min(selected, len(rows) - 1))
        for index in range(MAX_WIDGETS):
            self.setProperty("row{}.label".format(index),
                             "{}. {}".format(index + 1, rows[index]["title"]) if index < len(rows) else "")
        self.setProperty("description", rows[self.selected]["description"] if rows else "")

    def focus_widget(self):
        self.setFocusId(210 + self.selected if self.draft[self.section] else 201)

    def onFocus(self, control_id):
        if control_id in self.SECTION_CONTROLS:
            if self.move_original is not None:
                self.focus_widget()
                return
            section = SECTIONS[self.SECTION_CONTROLS.index(control_id)]
            if section != self.section:
                self.section = section
                self.render()
        elif 210 <= control_id < 210 + len(self.draft[self.section]):
            self.selected = control_id - 210
            self.setProperty("description", self.draft[self.section][self.selected]["description"])

    def choose(self, replacing=None):
        rows = self.draft[self.section]
        used = {entry["id"] for index, entry in enumerate(rows) if index != replacing}
        choices = [entry for entry in CATALOGUE[self.section] if entry["id"] not in used]
        if self.section in ("programs", "videos"):
            choices = [entry for entry in choices if entry["id"] != "android" or xbmc.getCondVisibility("System.Platform.Android")]
        elif self.section != "mylist":
            choices.append(option("custom", L(31631), "", L(31632)))
        if not choices:
            return None
        items = []
        for entry in choices:
            item = xbmcgui.ListItem(entry["title"], entry["description"])
            items.append(item)
        selected = widget_select(L(31625).format(SECTION_LABELS[SECTIONS.index(self.section)]), items, useDetails=True)
        if selected < 0:
            return None
        entry = dict(choices[selected])
        if entry["id"] == "custom":
            folder = "special://profile/playlists/" + ("music/" if self.section == "music" else "video/")
            path = xbmcgui.Dialog().browse(1, L(31619), "files", ".xsp", False, False, folder)
            if not path:
                return None
            try:
                file = xbmcvfs.File(path)
                try:
                    root = ET.fromstring(file.read())
                finally:
                    file.close()
                if root.tag != "smartplaylist" or root.get("type") not in PLAYLIST_TYPES[self.section]:
                    raise ValueError(L(31738))
                entry = option("custom", root.findtext("name") or os.path.splitext(os.path.basename(path))[0], path, L(31626))
                if not normalise(self.section, [entry]):
                    raise ValueError(L(31739))
                if any(index != replacing and row["path"] == path for index, row in enumerate(rows)):
                    raise ValueError(L(31740))
            except (ET.ParseError, ValueError, OSError, RuntimeError) as error:
                xbmcgui.Dialog().ok(L(31422), str(error))
                return None
        if self.has_global_appearance:
            self.apply_global_entry(self.section, entry)
        return entry

    def apply_global_entry(self, section, entry):
        if entry["id"] == "fullscreen":
            return
        entry["artwork"] = "icons" if section in ("programs", "videos") else "covers" if section == "music" else self.global_settings["artwork"]
        entry["limit"] = self.global_settings["limit"]
        entry.pop("progress", None)
        if entry["id"] == "continue":
            entry["progress"] = self.global_settings["progress"]

    def selection_behaviour(self):
        types = (
            (L(31075), "movieset", ("browse", "continuewatching", "playfrombeginning", "playnext", "queue")),
            (L(31234), "tvshow", ("browse", "continuewatching", "playfrombeginning", "playnext", "queue")),
            (L(31620), "album", ("browse", "play", "playnext", "queue")),
        )
        names = {"browse": L(31597), "continuewatching": L(31598), "playfrombeginning": L(31599),
                 "play": L(31616), "playnext": L(31617), "queue": L(31618)}
        while True:
            kind = widget_select(L(31621), [row[0] for row in types])
            if kind < 0:
                return
            title, prefix, actions = types[kind]
            current = next((i for i, action in enumerate(actions)
                            if xbmc.getCondVisibility("Skin.HasSetting({}_onclick_{})".format(prefix, action))), 0)
            choice = widget_select(title, [names[action] for action in actions], preselect=current)
            if choice < 0:
                continue
            for action in actions:
                xbmc.executebuiltin("Skin.Reset({}_onclick_{})".format(prefix, action))
            xbmc.executebuiltin("Skin.SetBool({}_onclick_{})".format(prefix, actions[choice]))

    def global_appearance(self):
        while True:
            settings = self.global_settings
            labels = [
                L(31627) + (L(31221) if settings["artwork"] == "posters" else L(31633)),
                L(31634).format(settings["limit"]),
                L(31628) + (L(31517) if settings["progress"] else L(31429)),
                L(31622),
            ]
            action = widget_select(L(31623), labels,
                                   warning=L(31629))
            if action < 0:
                return
            if action == 3:
                self.selection_behaviour()
                continue
            if action == 0:
                choice = widget_select(L(31159), [L(31633), L(31221)],
                                       preselect=1 if settings["artwork"] == "posters" else 0)
                if choice < 0:
                    continue
                settings["artwork"] = ("thumbs", "posters")[choice]
            elif action == 1:
                choice = widget_select(L(31635), [str(value) for value in ITEM_COUNTS],
                                       preselect=ITEM_COUNTS.index(settings["limit"]))
                if choice < 0:
                    continue
                settings["limit"] = ITEM_COUNTS[choice]
            else:
                settings["progress"] = not settings["progress"]
            # Reapply the complete global appearance, clearing individual overrides.
            for section in SECTIONS:
                for entry in self.draft[section]:
                    self.apply_global_entry(section, entry)
            self.has_global_appearance = True
            xbmc.executebuiltin('Skin.SetString({}.GlobalAppearance,"{}")'.format(
                PREFIX, encode(settings)))
            self.save()

    def appearance(self, entry):
        while True:
            settings = widget_settings(self.section, entry)
            actions = []
            if self.section == "movies" or (self.section == "tvshows" and entry["id"] not in EPISODE_WIDGETS) or (self.section == "mylist" and entry["id"] != "continue"):
                actions.append((L(31636) + (L(31221) if settings["artwork"] == "posters" else L(31633)), "artwork"))
            actions.append((L(31634).format(settings["limit"]), "limit"))
            if entry["id"] == "continue":
                actions.append((L(31637) + (L(31517) if settings["progress"] else L(31429)), "progress"))
            selected = widget_select(entry["title"] + L(31630), [label for label, _ in actions])
            if selected < 0:
                return
            before = dict(entry)
            action = actions[selected][1]
            if action == "artwork":
                selected = widget_select(L(31159), [L(31633), L(31221)], preselect=1 if settings["artwork"] == "posters" else 0)
                if selected >= 0:
                    entry["artwork"] = ("thumbs", "posters")[selected]
            elif action == "limit":
                selected = widget_select(L(31635), [str(value) for value in ITEM_COUNTS], preselect=ITEM_COUNTS.index(settings["limit"]))
                if selected >= 0:
                    entry["limit"] = ITEM_COUNTS[selected]
            else:
                entry["progress"] = not settings["progress"]
            if entry != before:
                self.save()

    def onClick(self, control_id):
        if 210 <= control_id < 210 + len(self.draft[self.section]):
            self.selected = control_id - 210
            control_id = 200
        if self.move_original is not None:
            if control_id == 200:
                self.finish_move()
            return
        if control_id == 103:
            self.global_appearance()
            self.render()
            self.setFocusId(103)
        elif control_id in self.SECTION_CONTROLS:
            self.onFocus(control_id)
            self.focus_widget()
        elif control_id == 200 and self.draft[self.section]:
            rows = self.draft[self.section]
            index = self.selected
            actions = [(L(31638), "change")]
            if len(rows) > 1:
                actions.append((L(31640), "move"))
            if rows[index]["id"] != "fullscreen":
                actions.append((L(31641), "appearance"))
            actions.append((L(31639), "remove"))
            selected = widget_select(rows[index]["title"], [label for label, _ in actions])
            if selected < 0:
                return
            action = actions[selected][1]
            if action == "change":
                entry = self.choose(index)
                if entry:
                    rows[index] = entry
                    self.save()
            elif action == "appearance":
                self.appearance(rows[index])
            elif action == "move":
                self.move_original = list(rows)
                self.move_index = index
                self.setProperty("moving", "true")
                self.focus_widget()
                return
            else:
                rows.pop(index)
                self.save()
            self.render(index)
            self.focus_widget()
        elif control_id == 201 and len(self.draft[self.section]) < MAX_WIDGETS:
            entry = self.choose()
            if entry:
                self.draft[self.section].append(entry)
                self.save()
                self.render(len(self.draft[self.section]) - 1)
                self.focus_widget()
        elif control_id == 202:
            self.draft[self.section] = defaults(self.section)
            if self.has_global_appearance:
                for entry in self.draft[self.section]:
                    self.apply_global_entry(self.section, entry)
            self.save()
            self.render()

    def onAction(self, action):
        if self.move_original is not None:
            action_id = action.getId()
            if action_id in (9, 10, 92):
                self.finish_move(cancel=True)
            elif action_id in (3, 4):
                rows = self.draft[self.section]
                target = max(0, min(len(rows) - 1, self.move_index + (-1 if action_id == 3 else 1)))
                if target != self.move_index:
                    rows.insert(target, rows.pop(self.move_index))
                    self.move_index = target
                    self.render(target)
                self.focus_widget()
            return
        if action.getId() in (9, 10, 92):
            self.close()

    def finish_move(self, cancel=False):
        if cancel:
            entry = self.draft[self.section][self.move_index]
            self.draft[self.section] = self.move_original
            self.move_index = self.move_original.index(entry)
        elif self.draft[self.section] != self.move_original:
            self.save()
        self.move_original = None
        self.clearProperty("moving")
        self.render(self.move_index)
        self.focus_widget()

    def save(self):
        for section in SECTIONS:
            rows = normalise(section, self.draft[section])
            values = {"Config": encode(rows), "Count": str(len(rows))}
            for slot in range(1, MAX_WIDGETS + 1):
                entry = rows[slot - 1] if slot <= len(rows) else {"id": "", "path": "", "title": ""}
                values["{}.Id".format(slot)] = entry["id"]
                values["{}.Path".format(slot)] = entry["path"]
                values["{}.Title".format(slot)] = entry["title"]
                settings = widget_settings(section, entry)
                values["{}.Artwork".format(slot)] = settings["artwork"] if entry["id"] != "fullscreen" else ""
                values["{}.Limit".format(slot)] = str(settings["limit"]) if settings["limit"] else ""
                values["{}.Progress".format(slot)] = ("on" if settings["progress"] else "off") if entry["id"] == "continue" else ""
            for key, value in values.items():
                name = "{}.{}.{}".format(PREFIX, section, key)
                if value:
                    xbmc.executebuiltin('Skin.SetString({},"{}")'.format(name, value))
                else:
                    xbmc.executebuiltin("Skin.Reset({})".format(name))
        xbmc.executebuiltin("Skin.SetBool({}.Configured)".format(PREFIX))
        xbmc.executebuiltin("Skin.SetBool({}.mylist.Configured)".format(PREFIX))
        self.applied = True


def list_next(handle):
    import xbmcplugin
    request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetEpisodes", "params": {
        "properties": ["tvshowid", "season", "episode", "playcount", "lastplayed", "resume"]}}
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        xbmcplugin.setContent(handle, "episodes")
        for episode in next_episodes(response.get("result", {}).get("episodes", []), limit=30):
            # Fetch artwork and long plots only for the episodes actually displayed.
            details_request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetEpisodeDetails", "params": {
                "episodeid": episode["episodeid"], "properties": ["title", "showtitle", "art", "file", "plot", "runtime", "firstaired", "rating", "uniqueid"]}}
            details = json.loads(xbmc.executeJSONRPC(json.dumps(details_request)))
            if "error" in details:
                continue  # A concurrent library clean can remove an episode.
            episode.update(details.get("result", {}).get("episodedetails", {}))
            item = xbmcgui.ListItem(episode["title"], path=episode["file"], offscreen=True)
            tag = item.getVideoInfoTag()
            tag.setDbId(episode["episodeid"])
            tag.setMediaType("episode")
            tag.setTitle(episode["title"])
            tag.setTvShowTitle(episode.get("showtitle", ""))
            tag.setSeason(episode["season"])
            tag.setEpisode(episode["episode"])
            tag.setPlot(episode.get("plot", ""))
            tag.setDuration(episode.get("runtime", 0))
            tag.setFirstAired(episode.get("firstaired", ""))
            tag.setPlaycount(episode.get("playcount", 0))
            tag.setRating(episode.get("rating", 0))
            tag.setUniqueIDs(episode.get("uniqueid", {}))
            tag.setResumePoint(episode.get("resume", {}).get("position", 0), episode.get("resume", {}).get("total", 0))
            art = dict(episode.get("art", {}))
            for kind in ("fanart", "clearlogo", "poster"):
                if not art.get(kind) and art.get("tvshow." + kind):
                    art[kind] = art["tvshow." + kind]
            item.setArt(art)
            item.setProperty("IsPlayable", "true")
            xbmcplugin.addDirectoryItem(handle, episode["file"], item, False)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (ValueError, KeyError, RuntimeError) as error:
        xbmc.log("Flixium next episode: {}".format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)


def list_my_movies(handle):
    import xbmcplugin
    import my_list
    path = xbmcvfs.translatePath("special://profile/addon_data/skin.flixium/my_list.json")
    try:
        rows = my_list.load(path)
        xbmcplugin.setContent(handle, "movies")
        if rows:
            # Resolve paths against today's library, including re-scraped movies.
            request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetMovies",
                       "params": {"properties": ["file"]}}
            response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            selected = my_list.select_movies(rows, response.get("result", {}).get("movies", []))
            requests = [{"jsonrpc": "2.0", "id": movie["movieid"], "method": "VideoLibrary.GetMovieDetails",
                         "params": {"movieid": movie["movieid"], "properties": [
                             "title", "originaltitle", "file", "art", "plot", "tagline", "year", "genre",
                             "runtime", "rating", "playcount", "resume", "mpaa", "uniqueid"]}} for movie in selected]
            responses = json.loads(xbmc.executeJSONRPC(json.dumps(requests))) if requests else []
            for response in responses:
                movie = response.get("result", {}).get("moviedetails")
                if not movie:
                    continue
                item = xbmcgui.ListItem(movie["title"], path=movie["file"], offscreen=True)
                tag = item.getVideoInfoTag()
                tag.setDbId(movie["movieid"])
                tag.setMediaType("movie")
                tag.setTitle(movie["title"])
                tag.setOriginalTitle(movie.get("originaltitle", ""))
                tag.setPlot(movie.get("plot", ""))
                tag.setTagLine(movie.get("tagline", ""))
                tag.setYear(movie.get("year", 0))
                tag.setGenres(movie.get("genre", []))
                tag.setDuration(movie.get("runtime", 0))
                tag.setRating(movie.get("rating", 0))
                tag.setPlaycount(movie.get("playcount", 0))
                tag.setMpaa(movie.get("mpaa", ""))
                tag.setUniqueIDs(movie.get("uniqueid", {}))
                resume = movie.get("resume", {})
                tag.setResumePoint(resume.get("position", 0), resume.get("total", 0))
                item.setArt(movie.get("art", {}))
                item.setProperty("IsPlayable", "true")
                xbmcplugin.addDirectoryItem(handle, movie["file"], item, False)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        xbmc.log("Flixium My list: {}".format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)


def list_my_tvshows(handle):
    import xbmcplugin
    import my_list
    path = xbmcvfs.translatePath("special://profile/addon_data/skin.flixium/my_list_tvshows.json")
    try:
        rows = my_list.load(path)
        xbmcplugin.setContent(handle, "tvshows")
        if rows:
            request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetTVShows",
                       "params": {"properties": ["file"]}}
            response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            selected = my_list.select_items(rows, response.get("result", {}).get("tvshows", []))
            requests = [{"jsonrpc": "2.0", "id": show["tvshowid"], "method": "VideoLibrary.GetTVShowDetails",
                         "params": {"tvshowid": show["tvshowid"], "properties": [
                             "title", "file", "art", "plot", "year", "genre", "rating", "playcount",
                             "mpaa", "uniqueid", "episode", "watchedepisodes"]}} for show in selected]
            responses = json.loads(xbmc.executeJSONRPC(json.dumps(requests))) if requests else []
            for response in responses:
                if "error" in response:
                    raise RuntimeError(str(response["error"]))
                show = response.get("result", {}).get("tvshowdetails")
                if not show:
                    continue
                # A saved show opens its seasons, just like the library's show tile.
                url = "videodb://tvshows/titles/{}/".format(show["tvshowid"])
                item = xbmcgui.ListItem(show["title"], path=url, offscreen=True)
                tag = item.getVideoInfoTag()
                tag.setDbId(show["tvshowid"])
                tag.setMediaType("tvshow")
                tag.setTitle(show["title"])
                tag.setTvShowTitle(show["title"])
                tag.setPlot(show.get("plot", ""))
                tag.setYear(show.get("year", 0))
                tag.setGenres(show.get("genre", []))
                tag.setRating(show.get("rating", 0))
                tag.setPlaycount(show.get("playcount", 0))
                tag.setMpaa(show.get("mpaa", ""))
                tag.setUniqueIDs(show.get("uniqueid", {}))
                item.setArt(show.get("art", {}))
                total, watched = show.get("episode", 0), show.get("watchedepisodes", 0)
                item.setProperty("TotalEpisodes", str(total))
                item.setProperty("WatchedEpisodes", str(watched))
                item.setProperty("UnWatchedEpisodes", str(max(0, total - watched)))
                xbmcplugin.addDirectoryItem(handle, url, item, True)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        xbmc.log("Flixium TV My list: {}".format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)


if __name__ == "__main__":
    if sys.argv[0].startswith("plugin://"):
        action = parse_qs(sys.argv[2].lstrip("?")).get("action", [""])[0]
        if action == "genres":
            from genre_widgets import directory
            directory(int(sys.argv[1]), parse_qs(sys.argv[2].lstrip("?")).get("media", ["movies"])[0])
        elif action == "musicalbums":
            from music_widgets import directory
            directory(int(sys.argv[1]), parse_qs(sys.argv[2].lstrip("?")).get("slot", ["1"])[0])
        elif action == "continue":
            from continue_runtime import directory
            directory(int(sys.argv[1]), parse_qs(sys.argv[2].lstrip("?")).get("media", ["movies"])[0])
        elif action == "saved":
            from flixium_my_list import directory
            directory(int(sys.argv[1]), parse_qs(sys.argv[2].lstrip("?")))
        elif action == "mylist":
            list_my_movies(int(sys.argv[1]))
        elif action == "mylisttvshows":
            list_my_tvshows(int(sys.argv[1]))
        else:
            list_next(int(sys.argv[1]))
    else:
        editor = WidgetEditor("script-FlixiumWidgets.xml", SKIN, "Default", "1080i")
        editor.doModal()
        applied = editor.applied
        del editor
        if applied:
            request_reload()
