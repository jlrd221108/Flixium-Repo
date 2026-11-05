"""Genre tiles with empty entries for the remaining icon assignments."""

import json
from urllib.parse import quote

import xbmc
import xbmcgui
import xbmcplugin


EMPTY_GENRES = {
    "movies": ("Sport", "War", "History"),
    "tvshows": ("Documentary", "History", "Mini-Series", "Reality TV", "Suspense"),
}


def directory(handle, media):
    if media not in EMPTY_GENRES:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    request = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetGenres",
               "params": {"type": {"movies": "movie", "tvshows": "tvshow"}[media]}}
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        genres = response["result"].get("genres", [])
        names = {row["label"].casefold(): row["label"] for row in genres}
        for name in EMPTY_GENRES[media]:
            names.setdefault(name.casefold(), name)
        xbmcplugin.setContent(handle, "genres")
        for name in sorted(names.values(), key=str.casefold):
            # A name filter also opens a valid empty directory before media is added.
            playlist = {"type": media, "rules": {"and": [
                {"field": "genre", "operator": "is", "value": [name]}]}}
            url = "videodb://{}/titles/?xsp={}".format(
                media, quote(json.dumps(playlist, separators=(",", ":")), safe=""))
            item = xbmcgui.ListItem(name, path=url, offscreen=True)
            item.getVideoInfoTag().setTitle(name)
            item.setArt({"icon": "DefaultGenre.png"})
            xbmcplugin.addDirectoryItem(handle, url, item, True)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (ValueError, KeyError, TypeError, RuntimeError) as error:
        xbmc.log("Flixium genres: {}".format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
