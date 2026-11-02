"""Publish local/embedded lyrics and timed context for the music playback screen."""
import bisect
from collections import OrderedDict
import os
import time

import xbmc
import xbmcgui
import xbmcvfs

from lyrics_local import embedded_lyrics, parse_lyrics
from lyrics_timed import LyricLine, Word, parse_sidecar
from lyrics_layout import CachedGlyphLayout
from lyrics_options import PRESETS, read_options
from lyrics_timeline import with_interludes
from lyrics_native import NativeLyrics

PREFIX = "flixium.lyrics."
CONTEXT = (("before2", -2), ("before1", -1), ("current", 0), ("after1", 1), ("after2", 2))
LINE_KEYS = tuple(key for key, _ in CONTEXT)
PROPERTIES = ("mode", "text", "source")
LEGACY_PROPERTIES = ("bank", "before2", "before1", "current", "after1", "after2") + tuple(
    bank + "." + key for bank in ("a", "b") for key in
    ("glow", "frame", "wordtimed", "transition", "ripple") + tuple(
        row + suffix for row in LINE_KEYS for suffix in
        ("", ".align", ".backing", ".backframe", ".active", ".frame", ".wordtimed", ".dots", ".dotshow", ".dot1", ".dot2", ".dot3", ".breathe", ".effects")))
MAX_TEXT = 2 * 1024 * 1024


def word_frame_delay(started, fps=60):
    """Budget rendering inside a display tick; never queue catch-up frames."""
    # Kodi treats waitForAbort(0) as an infinite wait, not an immediate return.
    # Always yield briefly even when rendering exceeds the frame budget.
    return max(0.001, 1 / fps - (time.monotonic() - started))


def resolve_playing_path(path):
    """Library playback may expose a musicdb URI rather than the media file."""
    if path.startswith("musicdb://"):
        label = "Player.Filenameandpath"
        resolved = getattr(xbmc, "getInfoLabel", lambda _: "")(label)
        if resolved and resolved != label and not resolved.startswith("musicdb://"):
            return resolved
    return path


def line_active(lines, index, position):
    if not 0 <= index < len(lines) or position < lines[index][0]:
        return False
    end = getattr(lines[index], "end", None)
    if end is None:
        end = lines[index + 1][0] if index + 1 < len(lines) else float("inf")
    return position < end


def lyric_anchor(lines, latest, position):
    """Keep adjacent overlapping singers together, without pinning old tails."""
    if latest > 0 and line_active(lines, latest, position) and line_active(lines, latest - 1, position):
        return latest - 1
    return latest


def backing_text(line, position):
    return "\n".join(bg[1] for bg in getattr(line, "background", ()))


def backing_line(line, position):
    # Visibility follows the parent row; the original cues control singing.
    # Keeping the scene stable also avoids atlas rebuilds at backing cue edges.
    active = getattr(line, "background", ())
    if not active:
        return None
    text, cues = "", []
    for bg in active:
        if text:
            text += "\n"
        offset = len(text)
        cues.extend(Word(c.start, c.end, c.first + offset, c.last + offset) for c in bg.words)
        text += bg[1]
    end = max(bg.end for bg in active) if all(bg.end is not None for bg in active) else None
    return LyricLine(min(bg[0] for bg in active), text, cues, end=end,
                     align=getattr(line, "align", "center"))


def load_lyrics(path, source="auto"):
    """Try the preferred source, then the other source only if nothing is found."""
    order = ("embedded", "local") if source == "embedded" else ("local", "embedded")
    for candidate_source in order:
        try:
            lines, plain, name = load_lyrics_source(path, candidate_source)
        except (OSError, RuntimeError, ValueError, SyntaxError) as error:
            xbmc.log("Flixium {} lyrics: {}".format(candidate_source, error), xbmc.LOGWARNING)
            continue
        if any(line[1].strip() for line in lines) or plain.strip():
            return lines, plain, name
    return [], "", ""


def load_lyrics_source(path, source):
    # Internet streams should not be reopened just to probe their metadata.
    if path.lower().startswith(("http://", "https://", "plugin://")):
        if source == "local":
            return [], "", ""
        lines, plain = parse_lyrics(xbmc.getInfoLabel("MusicPlayer.Lyrics"))
        return lines, plain, "Embedded lyrics" if lines or plain else ""
    stem = os.path.splitext(path)[0]
    candidates = [base + ext for ext in (".ttml", ".krc", ".lrc", ".txt") for base in (stem, path)]
    for candidate in candidates if source != "embedded" else ():
        if not xbmcvfs.exists(candidate):
            continue
        handle = xbmcvfs.File(candidate)
        try:
            data = bytes(handle.readBytes(MAX_TEXT + 1))
        finally:
            handle.close()
        try:
            if len(data) > MAX_TEXT:
                raise ValueError("Lyric sidecar exceeds size limit")
            lines, plain = parse_sidecar(data, os.path.splitext(candidate)[1])
        except (ValueError, SyntaxError) as error:
            xbmc.log("Flixium lyric sidecar {}: {}".format(candidate, error), xbmc.LOGWARNING)
            continue
        if lines or plain:
            return lines, plain, "Local lyrics ({})".format(os.path.splitext(candidate)[1][1:].upper())
    if source == "local":
        return [], "", ""
    if path and xbmcvfs.exists(path):
        handle = xbmcvfs.File(path)
        try:
            lines, plain = embedded_lyrics(handle)
        finally:
            handle.close()
        if lines or plain:
            return lines, plain, "Embedded lyrics"
    lines, plain = parse_lyrics(xbmc.getInfoLabel("MusicPlayer.Lyrics"))
    return lines, plain, "Embedded lyrics" if lines or plain else ""


def run():
    monitor, player, window = xbmc.Monitor(), xbmc.Player(), xbmcgui.Window(10000)
    if window.getProperty(PREFIX + "running"):
        return
    window.setProperty(PREFIX + "running", "true")
    xbmc.log("Flixium music playback service started", xbmc.LOGINFO)
    # One-time cleanup of properties left by the removed renderer/blur worker.
    for key in LEGACY_PROPERTIES:
        window.clearProperty(PREFIX + key)
    window.clearProperty("flixium.playback.blurred")
    window.clearProperty("flixium.playback.cover_color")
    words = CachedGlyphLayout()
    native = NativeLyrics(window, words,
        enabled=lambda: (getattr(xbmc, "getInfoLabel", lambda _: "")("Visualisation.Name") == "Flixium Visualizer"
                         and xbmc.getCondVisibility("Window.IsVisible(visualisation)")),
        log=lambda error: xbmc.log("Flixium native lyrics bridge: " + error, xbmc.LOGWARNING))
    native_render = False
    cache, published = OrderedDict(), {}
    current_path, lines, times, plain, source = "", [], [], "", ""
    last_input_path, resolved_path = "", ""
    source_lines = []
    last_lyric_id = None
    current_source = ""
    index = -1
    options = PRESETS["Balanced"]
    next_options_check = 0
    last_position, last_tick, last_track, last_index = None, None, None, -1

    def publish(values, lyric_id=None, word_line=None, position=0, row_lines=None, transition="snap", paused=False):
        nonlocal last_lyric_id, native_render
        values = dict(values)
        if values.get("mode") == "synced":
            row_lines = row_lines or {"current": (word_line, True)}
            backgrounds = {row: backing_line(row_lines.get(row, (None, False))[0], position) for row, _ in CONTEXT}
            native_render = native.update(lyric_id, row_lines, backgrounds, position, options, transition, paused,
                                          seeking=xbmc.getCondVisibility("Player.Seeking"))
        else:
            native.clear()
            native_render = False
        last_lyric_id = lyric_id
        for key in PROPERTIES:
            value = values.get(key, "")
            if published.get(key) != value:
                # Lyrics are data, not Kodi label markup.
                window.setProperty(PREFIX + key, value.replace("[", "\uff3b").replace("]", "\uff3d"))
                published[key] = value

    try:
        while not monitor.abortRequested():
            tick_started = time.monotonic()
            position = 0
            if xbmc.getSkinDir() != "skin.flixium" or not player.isPlayingAudio():
                publish({})
                current_path = ""
                monitor.waitForAbort(0.5)
                continue
            try:
                visible = xbmc.getCondVisibility("Window.IsVisible(visualisation) | Window.IsVisible(musicosd)")
                if not visible:
                    native.clear()
                    last_position = None
                    last_lyric_id = None
                    monitor.waitForAbort(0.5)
                    continue
                native.set_background(xbmc.getCondVisibility("Skin.HasSetting(FlixiumMusicVisualiserBackground)"))
                if tick_started >= next_options_check:
                    previous_options = options
                    options = read_options(getattr(xbmc, "getInfoLabel", lambda _: ""))
                    if options.interludes != previous_options.interludes:
                        lines = with_interludes(source_lines, options.interludes)
                        times = [entry[0] for entry in lines]
                        last_position = None
                    next_options_check = tick_started + .5
                if not xbmc.getCondVisibility("!Skin.HasSetting(FlixiumMusicLyricsDisabled)"):
                    publish({"mode": "missing"})
                    current_path = ""
                    monitor.waitForAbort(0.5)
                    continue
                input_path = player.getPlayingFile()
                if input_path != last_input_path or resolved_path.startswith("musicdb://"):
                    resolved_path = resolve_playing_path(input_path)
                    last_input_path = input_path
                path = resolved_path
                source_mode = "embedded" if xbmc.getCondVisibility("Skin.HasSetting(FlixiumMusicEmbeddedLyrics)") else "local"
                cache_key = (path, source_mode)
                if path != current_path or source_mode != current_source:
                    publish({"mode": "loading"})
                    current_path = path
                    current_source = source_mode
                    lines, times, plain, source = [], [], "", ""
                    index = -1
                    last_position = None
                    if cache_key in cache:
                        source_lines, plain, source = cache.pop(cache_key)
                    else:
                        source_lines, plain, source = load_lyrics(path, source_mode)
                    cache[cache_key] = (source_lines, plain, source)
                    while len(cache) > 8:
                        cache.popitem(last=False)
                    lines = with_interludes(source_lines, options.interludes)
                    times = [entry[0] for entry in lines]
                if lines:
                    position = player.getTime()
                    latest = bisect.bisect_right(times, position) - 1
                    index = lyric_anchor(lines, latest, position)
                    values = {"mode": "synced", "source": source}
                    row_lines = {}
                    for key, offset in CONTEXT:
                        target = index + offset
                        values[key] = lines[target][1] if 0 <= target < len(lines) else ""
                        row_lines[key] = (lines[target] if 0 <= target < len(lines) else None,
                                          line_active(lines, target, position))
                    word_line = lines[index] if index >= 0 else None
                    continuous = (last_position is not None and last_track == cache_key
                                  and last_lyric_id is not None and last_lyric_id[-1] == options
                                  and index == last_index + 1
                                  and 0 <= position - last_position <= max(1, (tick_started - last_tick) * 2)
                                  and not xbmc.getCondVisibility("Player.Seeking"))
                    transition = "forward" if continuous and options.smooth else "snap"
                    publish(values, (path, source_mode, index, options), word_line, position, row_lines, transition,
                            paused=xbmc.getCondVisibility("Player.Paused"))
                    last_position, last_tick, last_track, last_index = position, tick_started, cache_key, index
                elif plain:
                    publish({"mode": "plain", "text": plain, "source": source})
                else:
                    publish({"mode": "missing"})
            except Exception as error:
                xbmc.log("Flixium local lyrics: {}".format(error), xbmc.LOGWARNING)
                publish({"mode": "missing"})
            # Only the small native scene/clock bridge runs here; never raster frames.
            delay = (max(.001, 1 / min(30, options.fps) - (time.monotonic() - tick_started))
                     if lines else .5)
            monitor.waitForAbort(delay)
    finally:
        native.close()
        window.clearProperty(PREFIX + "running")
        window.clearProperty("flixium.playback.progress")  # Remove a legacy unused value.
        for key in PROPERTIES:
            window.clearProperty(PREFIX + key)


if __name__ == "__main__":
    run()
