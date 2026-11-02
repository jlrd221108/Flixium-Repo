"""Profile-local saved lists. File paths survive library ID changes."""

from localization import localize as L
import json
import os
import time
import uuid

DEFAULTS = {"filter": "all", "sort": "added", "watched": "show",
            "show_count": True, "notifications": True}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + "." + uuid.uuid4().hex + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def preferences(path):
    result = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as stream:
            saved = json.load(stream)
        if not isinstance(saved, dict):
            raise ValueError(L(31783))
        for key, choices in {"filter": ("all", "movies", "tvshows"),
                             "sort": ("added", "alphabetical", "unwatched"),
                             "watched": ("show", "hide", "remove")}.items():
            if saved.get(key) in choices:
                result[key] = saved[key]
        for key in ("show_count", "notifications"):
            if isinstance(saved.get(key), bool):
                result[key] = saved[key]
    return result


def identity(item):
    return item["_kind"] + "|" + item["file"]


def watched(item, removing=False):
    complete = item.get("playcount", 0) > 0
    if item.get("_kind") == "tvshow":
        complete = item.get("episode", 0) > 0 and item.get("watchedepisodes", 0) >= item["episode"]
        if removing:
            complete = complete and item.get("status", "").casefold() == "ended"
    return complete


def ordered(items, prefs, media_filter="all"):
    rows = [item for item in items if media_filter == "all" or
            item["_kind"] == ("movie" if media_filter == "movies" else "tvshow")]
    if prefs["watched"] in ("hide", "remove"):
        rows = [item for item in rows if not watched(item, removing=prefs["watched"] == "remove")]
    rows.sort(key=lambda item: item.get("_added", 0), reverse=True)
    if prefs["sort"] == "alphabetical":
        rows.sort(key=lambda item: item.get("title", "").casefold())
    elif prefs["sort"] == "unwatched":
        rows.sort(key=watched)
    return rows


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as stream:
        rows = json.load(stream)
    if not isinstance(rows, list):
        raise ValueError(L(31782))
    return [row for row in rows if isinstance(row, dict)
            and isinstance(row.get("file"), str) and row["file"]]


def contains(rows, movie):
    return any(row["file"] == movie["file"] for row in rows)


def toggle(path, movie, id_key="movieid"):
    rows = load(path)
    added = not contains(rows, movie)
    rows = [row for row in rows if row["file"] != movie["file"]]
    if added:
        rows.append(dict({key: movie[key] for key in (id_key, "file", "title")}, added_at=time.time()))
    write(path, rows)
    return added


def select_items(rows, items):
    """Resolve by file, never reuse a stale ID for an unrelated library item."""
    indexed = {item["file"]: item for item in items}
    return [indexed[row["file"]] for row in rows if row["file"] in indexed]


select_movies = select_items
