"""Filtered native-library Continue watching widget provider."""
import time

import xbmc
import xbmcgui

import continue_watching
import my_list
import my_list_runtime as runtime


def hidden():
    return my_list.load(runtime.path("continue_watching_hidden.json"))


def remove(item_id, kind):
    method = "Movie" if kind == "movie" else "TVShow"
    item = runtime.rpc("VideoLibrary.Get" + method + "Details", {
        kind + "id": int(item_id), "properties": ["file", "lastplayed"]}).get(kind + "details", {})
    if not item.get("file"):
        raise ValueError("This item is no longer in the library")
    continue_watching.hide(runtime.path("continue_watching_hidden.json"), item, kind)
    home = xbmcgui.Window(10000)
    stamp = str(time.time_ns())
    home.setProperty("flixium.continue.revision", stamp)
    home.setProperty("flixium.mylist.revision", stamp)
    xbmc.executebuiltin("NotifyAll(flixium,continuechanged)")


def items(media):
    kind = "movie" if media == "movies" else "episode"
    plural = "movies" if kind == "movie" else "episodes"
    properties = ["file", "resume", "lastplayed"] + (["tvshowid"] if kind == "episode" else [])
    rows = runtime.rpc("VideoLibrary.Get" + plural.title(), {
        "properties": properties, "filter": {"field": "inprogress", "operator": "true", "value": ""}}).get(plural, [])
    dismissed = hidden()
    shows = {}
    if kind == "episode" and any(row.get("kind") == "tvshow" for row in dismissed):
        shows = {show["tvshowid"]: show for show in runtime.rpc("VideoLibrary.GetTVShows", {
            "properties": ["file", "lastplayed"]}).get("tvshows", [])}
    rows = [row for row in rows if row.get("resume", {}).get("position", 0) > 0 and
            not continue_watching.is_hidden(dismissed, row if kind == "movie" else shows.get(row.get("tvshowid"), {}),
                                            "movie" if kind == "movie" else "tvshow")]
    rows.sort(key=lambda row: row.get("lastplayed", ""), reverse=True)
    result = []
    properties = ["title", "file", "art", "plot", "runtime", "rating", "playcount", "resume", "lastplayed", "uniqueid"]
    properties += ["year", "genre", "mpaa"] if kind == "movie" else ["tvshowid", "showtitle", "season", "episode", "firstaired"]
    for row in rows[:30]:
        item = runtime.rpc("VideoLibrary.Get" + kind.title() + "Details", {
            kind + "id": row[kind + "id"], "properties": properties}).get(kind + "details")
        if item:
            item["_kind"] = kind
            result.append(item)
    return result


def directory(handle, media):
    import xbmcplugin
    try:
        xbmcplugin.setContent(handle, "movies" if media == "movies" else "episodes")
        for item in items(media):
            xbmcplugin.addDirectoryItem(handle, *runtime.listitem(item))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        xbmc.log("Flixium Continue watching: {}".format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
