"""Source identity and filename-only picture decoder discovery (no Kodi imports)."""

from localization import localize as L
from collections import deque
import hashlib
import posixpath
import re
from urllib.parse import unquote, urlsplit, urlunsplit


HEIF_EXTENSIONS = frozenset(("heic", "heif", "hif", "heics", "heifs"))
RAW_EXTENSIONS = frozenset("3fr ari arw bay bmq cap cine cr2 cr3 crw cs1 dc2 dcr dng drf dsc erf fff ia iiq k25 kc2 kdc mdc mef mos mrw nef nrw obm orf pef ptx pxn qtk raf raw rdc rwl rw2 rwz sr2 srf srw sti x3f".split())
OFFICIAL_DECODERS = "addons://repository.xbmc.org/kodi.imagedecoder/"
DECODERS = {"heif": L(31713), "raw": L(31714)}


def source_roots(path):
    if path.lower().startswith("multipath://"):
        return [unquote(part) for part in path[len("multipath://"):].split("/") if part]
    return [path]


def canonical(path):
    path = path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", path) or path.startswith("//"):
        return posixpath.normpath(path).casefold().rstrip("/") + "/"
    if "://" in path:
        parts = urlsplit(path)
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                           posixpath.normpath(unquote(parts.path)).rstrip("/") + "/", "", ""))
    return posixpath.normpath(path).rstrip("/") + "/"


def source_key(source):
    roots = sorted(canonical(root) for root in source_roots(source["file"]))
    return hashlib.sha256("\n".join(roots).encode("utf-8")).hexdigest()


def find_source(folder, sources):
    """Use the longest source root, with path boundaries and platform case rules."""
    if not folder or folder.lower().startswith(("sources://", "plugin://", "addons://")):
        return None
    candidates = []
    for source in sources:
        for root in source_roots(source["file"]):
            for current in source_roots(folder):
                if canonical(current).startswith(canonical(root)):
                    candidates.append((len(canonical(root)), source))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def scan_source(source, listdir, cancelled=lambda: False):
    """Walk VFS directory names only, independently of installed decoder filters.

    None means cancelled: never consume a source's notice after an interrupted
    scan. Stop early only once BOTH families have been found.
    """
    pending = deque(source_roots(source["file"]))
    seen, found = set(), set()
    while pending:
        if cancelled():
            return None
        folder = pending.popleft()
        identity = canonical(folder)
        if identity in seen:
            continue
        seen.add(identity)
        # Errors propagate so an offline source can be retried on a later visit.
        directories, files = listdir(folder)
        for name in files:
            extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
            if extension in HEIF_EXTENSIONS:
                found.add("heif")
            elif extension in RAW_EXTENSIONS:
                found.add("raw")
        if found == {"heif", "raw"}:
            return found
        for name in directories:
            if name in (".", ".."):
                continue
            pending.append(folder.rstrip("/\\") + "/" + name + "/")
    return found


def notice(found):
    kinds = L(31715) if len(found) == 2 else (
        L(31716) if "raw" in found else L(31717))
    addons = L(31786).format(DECODERS["heif"], DECODERS["raw"]) if len(found) == 2 else DECODERS[next(iter(found))]
    return L(31787).format(kinds, addons, addons)
