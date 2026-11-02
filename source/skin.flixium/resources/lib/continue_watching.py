"""Dismiss Continue watching entries without changing library or resume data."""
import my_list


def hide(path, item, kind):
    rows = my_list.load(path)
    rows = [row for row in rows if (row.get("kind"), row["file"]) != (kind, item["file"])]
    rows.append({"kind": kind, "file": item["file"], "lastplayed": item.get("lastplayed", "")})
    my_list.write(path, rows)


def is_hidden(rows, item, kind):
    return any(row.get("kind") == kind and row["file"] == item.get("file")
               and item.get("lastplayed", "") <= row.get("lastplayed", "") for row in rows)
