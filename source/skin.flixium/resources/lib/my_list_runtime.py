"""Kodi library adapter for the profile-local saved list."""

from localization import localize as L
import json
import os
import random
import time
import xml.etree.ElementTree as ET

import xbmc
import xbmcgui
import xbmcvfs

import my_list
from home_widgets import next_episodes


def path(filename):
    return xbmcvfs.translatePath("special://profile/addon_data/skin.flixium/" + filename)


def membership(kind):
    return path("my_list_tvshows.json" if kind == "tvshow" else "my_list.json")


def preferences():
    return my_list.preferences(path("my_list_settings.json"))


def rpc(method, params):
    result = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1,
                                                      "method": method, "params": params})))
    if "error" in result:
        raise RuntimeError(str(result["error"]))
    return result.get("result", {})


def invalidate():
    cache = path("my_list_library_cache.json")
    if os.path.exists(cache):
        os.remove(cache)


def show_status(folder):
    # Kodi's JSON-RPC TVShow fields do not expose series status. Only remove a
    # completed show when its own metadata explicitly confirms it has ended.
    metadata = folder.rstrip("/\\") + "/tvshow.nfo"
    try:
        if xbmcvfs.exists(metadata):
            stream = xbmcvfs.File(metadata)
            try:
                return (ET.fromstring(stream.read()).findtext("status") or "").strip()
            finally:
                stream.close()
    except (OSError, RuntimeError, ET.ParseError):
        pass
    return ""


def library_items():
    """Resolve saved paths against current IDs; share a short cache across rows."""
    cache = path("my_list_library_cache.json")
    fingerprint = [os.path.getmtime(membership(kind)) if os.path.exists(membership(kind)) else 0
                   for kind in ("movie", "tvshow")]
    try:
        with open(cache, encoding="utf-8") as stream:
            saved = json.load(stream)
        if time.time() - saved["time"] < 5 and saved["fingerprint"] == fingerprint:
            return saved["items"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    items = []
    for kind, plural, method in (("movie", "movies", "Movie"), ("tvshow", "tvshows", "TVShow")):
        rows = my_list.load(membership(kind))
        if not rows:
            continue
        # Older saved entries predate timestamps. Preserve their existing order.
        if any("added_at" not in row for row in rows):
            baseline = os.path.getmtime(membership(kind))
            for index, row in enumerate(rows):
                row.setdefault("added_at", baseline - (len(rows) - index) * .001)
            my_list.write(membership(kind), rows)
        current = rpc("VideoLibrary.Get" + ("Movies" if kind == "movie" else "TVShows"),
                      {"properties": ["file"]}).get(plural, [])
        indexed = {item["file"]: item for item in current}
        properties = ["title", "file", "art", "plot", "year", "genre", "rating", "playcount", "mpaa", "uniqueid"]
        properties += ["runtime", "resume", "lastplayed", "tagline", "originaltitle"] if kind == "movie" else ["episode", "watchedepisodes", "lastplayed"]
        requests, matching = [], []
        for row in rows:
            if row["file"] not in indexed:
                continue  # Unavailable items stay saved and reappear if restored.
            current_id = indexed[row["file"]][kind + "id"]
            requests.append({"jsonrpc": "2.0", "id": len(matching), "method": "VideoLibrary.Get" + method + "Details",
                             "params": {kind + "id": current_id, "properties": properties}})
            matching.append(row)
        responses = json.loads(xbmc.executeJSONRPC(json.dumps(requests))) if requests else []
        for response in responses:
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            item = response.get("result", {}).get(kind + "details")
            if item:
                item.update(_kind=kind, _added=matching[response["id"]]["added_at"])
                if kind == "tvshow" and preferences()["watched"] == "remove":
                    item["status"] = show_status(item["file"])
                items.append(item)
    # Home rows run in separate plugin interpreters. On Windows a concurrent
    # reader can briefly prevent replacement; this optional cache must never
    # discard the library items we have already resolved.
    try:
        my_list.write(cache, {"time": time.time(), "fingerprint": fingerprint, "items": items})
    except OSError:
        pass
    return items


def active_filter(explicit="default"):
    return explicit if explicit in ("all", "movies", "tvshows") else preferences()["filter"]


def continued(items, limit=30):
    result = [item for item in items if item["_kind"] == "movie" and
              item.get("resume", {}).get("position", 0) > 0 and not my_list.watched(item)]
    shows = [item for item in items if item["_kind"] == "tvshow"]
    requests = [{"jsonrpc": "2.0", "id": show["tvshowid"], "method": "VideoLibrary.GetEpisodes",
                 "params": {"tvshowid": show["tvshowid"], "properties": [
                     "tvshowid", "season", "episode", "playcount", "lastplayed", "resume"]}}
                for show in shows]
    responses = json.loads(xbmc.executeJSONRPC(json.dumps(requests))) if requests else []
    episodes = []
    for response in responses:
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        show_episodes = response.get("result", {}).get("episodes", [])
        lastplayed = max((row.get("lastplayed", "") for row in show_episodes), default="")
        episodes.extend(dict(row, _continue_lastplayed=lastplayed) for row in show_episodes)
    for candidate in next_episodes(episodes, limit):
        episode = rpc("VideoLibrary.GetEpisodeDetails", {"episodeid": candidate["episodeid"], "properties": [
            "title", "tvshowid", "showtitle", "season", "episode", "file", "art", "plot", "runtime",
            "rating", "playcount", "resume", "lastplayed", "firstaired", "uniqueid"]}).get("episodedetails")
        if episode:
            episode["_kind"] = "episode"
            episode["_continue_lastplayed"] = candidate["_continue_lastplayed"]
            result.append(episode)
    return sorted(result, key=lambda item: item.get("_continue_lastplayed", item.get("lastplayed", "")), reverse=True)[:limit]


def view_items(view="all", media_filter="default", limit=30):
    prefs = preferences()
    selected_filter = active_filter(media_filter)
    items = my_list.ordered(library_items(), prefs, selected_filter)
    if view == "movies":
        items = [item for item in items if item["_kind"] == "movie"]
    elif view == "tvshows":
        items = [item for item in items if item["_kind"] == "tvshow"]
    elif view == "continue":
        from continue_runtime import hidden
        from continue_watching import is_hidden
        dismissed = hidden()
        items = [item for item in items if not is_hidden(dismissed, item, item["_kind"])]
        items = continued(items, limit)
    elif view == "recent":
        items.sort(key=lambda item: item["_added"], reverse=True)
    elif view == "unwatched":
        items = [item for item in items if item["_kind"] == "movie" and not my_list.watched(item)
                 and not item.get("resume", {}).get("position", 0)]
    elif view == "random":
        items = random.sample(items, min(len(items), 5))
    return items[:limit] if limit else items


def listitem(item):
    kind = item["_kind"]
    url = "videodb://tvshows/titles/{}/".format(item["tvshowid"]) if kind == "tvshow" else item["file"]
    entry = xbmcgui.ListItem(item["title"], path=url, offscreen=True)
    tag = entry.getVideoInfoTag()
    tag.setDbId(item[kind + "id"])
    tag.setMediaType(kind)
    tag.setTitle(item["title"])
    tag.setPlot(item.get("plot", ""))
    tag.setRating(item.get("rating", 0))
    tag.setPlaycount(item.get("playcount", 0))
    tag.setUniqueIDs(item.get("uniqueid", {}))
    if kind != "episode":
        tag.setYear(item.get("year", 0))
        tag.setGenres(item.get("genre", []))
        tag.setMpaa(item.get("mpaa", ""))
    if kind == "episode":
        tag.setTvShowTitle(item.get("showtitle", ""))
        tag.setSeason(item["season"])
        tag.setEpisode(item["episode"])
        tag.setFirstAired(item.get("firstaired", ""))
    if kind != "tvshow":
        tag.setDuration(item.get("runtime", 0))
        resume = item.get("resume", {})
        tag.setResumePoint(resume.get("position", 0), resume.get("total", 0))
        entry.setProperty("IsPlayable", "true")
    else:
        tag.setTvShowTitle(item["title"])
        total, watched = item.get("episode", 0), item.get("watchedepisodes", 0)
        for key, value in (("TotalEpisodes", total), ("WatchedEpisodes", watched), ("UnWatchedEpisodes", max(0, total - watched))):
            entry.setProperty(key, str(value))
    art = dict(item.get("art", {}))
    if kind == "episode":
        for key in ("poster", "fanart", "clearlogo"):
            art.setdefault(key, art.get("tvshow." + key, ""))
    entry.setArt(art)
    return url, entry, kind == "tvshow"


def refresh_state(remove_watched=True):
    prefs = preferences()
    items = library_items()
    if remove_watched and prefs["watched"] == "remove":
        for kind in ("movie", "tvshow"):
            remove = {item["file"] for item in items if item["_kind"] == kind and my_list.watched(item, removing=True)}
            if remove:
                my_list.write(membership(kind), [row for row in my_list.load(membership(kind)) if row["file"] not in remove])
        items = [item for item in items if not my_list.watched(item, removing=True)]
    visible = my_list.ordered(items, prefs)
    home = xbmcgui.Window(10000)
    labels = {
        "filter": {"all": L(31504), "movies": L(31233), "tvshows": L(31505)},
        "sort": {"added": L(31506), "alphabetical": L(31507), "unwatched": L(31508)},
        "watched": {"show": L(31509), "hide": L(31510), "remove": L(31511)},
        "show_count": {True: L(31517), False: L(31429)},
        "notifications": {True: L(31517), False: L(31429)},
    }
    for key, values in labels.items():
        home.setProperty("flixium.mylist.setting." + key, values[prefs[key]])
    for key, value in (("filter", prefs["filter"]), ("showcount", "true" if prefs["show_count"] else "false"),
                       ("count", str(len(visible))),
                       ("movies", str(sum(item["_kind"] == "movie" for item in visible))),
                       ("tvshows", str(sum(item["_kind"] == "tvshow" for item in visible)))):
        home.setProperty("flixium.mylist." + key, value)
    return prefs


def changed():
    invalidate()
    refresh_state()
    stamp = str(time.time_ns())
    home = xbmcgui.Window(10000)
    home.setProperty("flixium.mylist.revision", stamp)
    home.setProperty("flixium.mylist.tvshows.revision", stamp)
    home.setProperty("flixium.continue.revision", stamp)
    xbmc.executebuiltin("NotifyAll(flixium,mylistchanged)")
