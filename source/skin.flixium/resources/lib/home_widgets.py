"""Widget catalogue and configuration rules. No Kodi imports: easy to validate."""

from localization import localize as L
from copy import deepcopy
import json
from urllib.parse import quote, unquote

MAX_WIDGETS = 6
ITEM_COUNTS = (10, 15, 20, 30)
SECTIONS = ("movies", "tvshows", "music", "programs", "videos", "mylist")
SECTION_LABELS = (L(31233), L(31234), L(31414), L(31415), L(31416), L(31241))
PREFIX = "Flixium.Widgets"
EPISODE_WIDGETS = ("continue", "next", "recentepisodes", "watched")


def option(key, title, path, description):
    return {"id": key, "title": title, "path": path, "description": description}


def playlist(section, key):
    return "special://skin/playlists/widgets/{}_{}.xsp".format(section, key)


CATALOGUE = {
    "mylist": [
        option("continue", L(31232), "plugin://skin.flixium/?action=saved&view=continue", L(31642)),
        option("movies", L(31233), "plugin://skin.flixium/?action=saved&view=movies", L(31643)),
        option("tvshows", L(31234), "plugin://skin.flixium/?action=saved&view=tvshows", L(31644)),
        option("recent", L(31235), "plugin://skin.flixium/?action=saved&view=recent", L(31645)),
        option("random", L(31236), "plugin://skin.flixium/?action=saved&view=random", L(31646)),
        option("unwatched", L(31007), "plugin://skin.flixium/?action=saved&view=unwatched", L(31647)),
    ],
    "movies": [
        option("all", L(31249), "videodb://movies/titles/", L(31648)),
        option("fullscreen", L(31649), "videodb://movies/titles/", L(31650)),
        option("continue", L(31247), "plugin://skin.flixium/?action=continue&media=movies", L(31651)),
        option("recent", L(31248), playlist("movies", "recent"), L(31652)),
        option("unwatched", L(31007), playlist("movies", "unwatched"), L(31653)),
        option("watched", L(31654), playlist("movies", "watched"), L(31655)),
        option("rated", L(31656), playlist("movies", "rated"), L(31657)),
        option("random", L(31006), playlist("movies", "random"), L(31658)),
        option("sets", L(31659), "videodb://movies/sets/", L(31660)),
        option("genres", L(31661), "videodb://movies/genres/", L(31662)),
    ],
    "tvshows": [
        option("all", L(31257), "videodb://tvshows/titles/", L(31663)),
        option("fullscreen", L(31664), "videodb://tvshows/titles/", L(31665)),
        option("continue", L(31250), "plugin://skin.flixium/?action=continue&media=tvshows", L(31666)),
        option("next", L(31251), "plugin://skin.flixium/?action=next", L(31667)),
        option("recentepisodes", L(31252), playlist("tvshows", "recentepisodes"), L(31668)),
        option("recentshows", L(31669), playlist("tvshows", "recentshows"), L(31670)),
        option("unwatched", L(31671), "special://skin/playlists/unwatched_tvshows.xsp", L(31672)),
        option("watched", L(31673), playlist("tvshows", "watched"), L(31674)),
        option("random", L(31675), playlist("tvshows", "random"), L(31676)),
    ],
    "music": [
        option("played", L(31253), playlist("music", "played"), L(31677)),
        option("recent", L(31254), playlist("music", "recent"), L(31678)),
        option("most", L(31011), "special://skin/playlists/mostplayed_albums.xsp", L(31679)),
        option("random", L(31012), "special://skin/playlists/random_albums.xsp", L(31680)),
        option("unplayed", L(31014), "special://skin/playlists/unplayed_albums.xsp", L(31681)),
        option("rated", L(31682), playlist("music", "rated"), L(31683)),
        option("artists", L(31684), "musicdb://artists/", L(31685)),
        option("genres", L(31661), "musicdb://genres/", L(31686)),
    ],
    "videos": [
        dict(option("categories", L(31148), "library://video/", L(31687)), target="videos"),
        dict(option("sources", L(31244), "sources://video/", L(31688)), target="videos"),
        dict(option("playlists", L(31245), "special://videoplaylists/", L(31689)), target="videos"),
        dict(option("addons", L(31238), "addons://sources/video/", L(31690)), target="videos"),
    ],
    "programs": [
        dict(option("categories", L(31148), "addons://", L(31691)), target="addonbrowser"),
        dict(option("video", L(31238), "addons://sources/video/", L(31690)), target="videos"),
        dict(option("audio", L(31239), "addons://sources/audio/", L(31692)), target="music"),
        dict(option("programs", L(31693), "addons://sources/executable/", L(31694)), target="programs"),
        dict(option("games", L(31695), "addons://sources/game/", L(31696)), target="games"),
        dict(option("pictures", L(31697), "addons://sources/image/", L(31698)), target="pictures"),
        dict(option("android", L(31699), "androidapp://sources/apps/", L(31700)), target="programs"),
    ],
}
DEFAULT_IDS = {"movies": ("genres", "continue", "recent"),
               "mylist": ("continue", "movies", "tvshows", "recent", "random"),
               "tvshows": ("continue", "next", "recentepisodes"),
               "music": ("played", "recent", "most"),
               "programs": ("categories", "video", "audio"),
               "videos": ("categories", "sources", "playlists")}
PLAYLIST_TYPES = {"movies": {"movies"}, "tvshows": {"tvshows", "episodes"},
                  "music": {"albums", "artists", "songs"}}


def defaults(section):
    choices = {entry["id"]: entry for entry in CATALOGUE[section]}
    return [deepcopy(choices[key]) for key in DEFAULT_IDS[section]]


def widget_settings(section, entry):
    """Validated appearance values; fullscreen library rails are fixed."""
    if entry.get("id") == "fullscreen":
        return {"artwork": "thumbs", "limit": None, "progress": False}
    count = entry.get("limit", 15)
    if type(count) is not int or count not in ITEM_COUNTS:
        count = 15
    artwork = "posters" if section != "music" and entry.get("artwork") == "posters" else ("covers" if section == "music" else "thumbs")
    if section in ("programs", "videos"):
        artwork = "icons"
    if section == "tvshows" and entry.get("id") in EPISODE_WIDGETS:
        artwork = "thumbs"
    if section == "mylist":
        artwork = "thumbs" if entry.get("id") == "continue" else entry.get("artwork", "posters")
        if artwork not in ("thumbs", "posters"):
            artwork = "posters"
    progress = entry.get("progress", True)
    return {"artwork": artwork, "limit": count,
            "progress": (progress if isinstance(progress, bool) else True) if entry.get("id") == "continue" else False}


def normalise(section, entries):
    """Reject broken/stale entries, duplicates and oversized saved lists."""
    if not isinstance(entries, list):
        return defaults(section)
    choices = {entry["id"]: entry for entry in CATALOGUE[section]}
    result, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get("id")
        saved = entry
        if not isinstance(key, str):
            continue
        if key == "custom":
            if section in ("programs", "videos", "mylist"):
                continue
            path, title = entry.get("path", ""), entry.get("title", "")
            if not isinstance(path, str) or not path.lower().endswith(".xsp") or not isinstance(title, str):
                continue
            if any(c in path + title for c in '\"\r\n'):
                continue
            entry = option("custom", title[:100] or L(31701), path, L(31626))
            identity = path
        elif key in choices:
            entry, identity = choices[key], key
        else:
            continue
        if identity not in seen:
            entry = deepcopy(entry)
            settings = widget_settings(section, saved)
            if key != "fullscreen":
                for name in ("artwork", "limit", "progress"):
                    if name in saved and (name != "progress" or key == "continue"):
                        entry[name] = settings[name]
            result.append(entry)
            seen.add(identity)
        if len(result) == MAX_WIDGETS:
            break
    return result


def encode(entries):
    return quote(json.dumps(entries, ensure_ascii=False, separators=(",", ":")), safe="")


def decode(section, value):
    if not value:
        return defaults(section)
    try:
        return normalise(section, json.loads(unquote(value)))
    except (ValueError, TypeError):
        return defaults(section)


def next_episodes(episodes, limit=15):
    """One first unwatched regular episode per started show, most recently played first."""
    shows = {}
    for episode in episodes:
        if episode.get("season", 0) <= 0 or episode.get("episode", 0) <= 0:
            continue
        shows.setdefault(episode["tvshowid"], []).append(episode)
    result = []
    for rows in shows.values():
        started = [row for row in rows if row.get("playcount", 0) > 0 or row.get("resume", {}).get("position", 0) > 0]
        if not started:
            continue
        unwatched = [row for row in rows if not row.get("playcount", 0)]
        if unwatched:
            row = min(unwatched, key=lambda item: (item["season"], item["episode"]))
            result.append((max((item.get("lastplayed", "") for item in started), default=""), row))
    return [row for _, row in sorted(result, key=lambda item: item[0], reverse=True)][:limit]
