#!/usr/bin/python
# coding: utf-8

"""Publish aggregate metadata for the movie set selected in the Flix view."""

from localization import localize as L

import json
import re
import time

import xbmc
import xbmcgui


SUPPORTED_SKIN = "skin.flixium"
SET_ID_CONTROL = 56001
SET_TYPE_CONTROL = 56002
GENRE_CONTROL = 56003
PROPERTY_COUNT = "flixium.helper.set_count"
PROPERTY_YEARS = "flixium.helper.set_years"
PROPERTY_RUNTIME = "flixium.helper.set_runtime"
PROPERTY_GENRES = "flixium.helper.flix_genres"
PROPERTY_ARTIST_ALBUMS = "flixium.helper.artist_album_count"
PROPERTY_ARTIST_TRACKS = "flixium.helper.artist_track_count"
PROPERTY_ALBUM_TRACKS = "flixium.helper.album_track_count"
PROPERTY_ALBUM_RUNTIME = "flixium.helper.album_runtime"
HOME_WINDOW = xbmcgui.Window(10000)
FLIX_ACTIVE_CONDITION = (
	"[Window.IsActive(videos) + [Control.IsVisible(56) | Control.IsVisible(57)]] | "
	"[Window.IsActive(music) + [Control.IsVisible(56) | Control.IsVisible(57) | Control.IsVisible(59) | Container.Content(albums)]] | "
	"[Window.IsActive(home) + [" + " | ".join(
		"Control.HasFocus({})".format(base + slot * 10)
		for base in (5800, 5900) for slot in range(6)
	) + "]] | "
	"String.IsEqual(Control.GetLabel({}),artist)".format(SET_TYPE_CONTROL)
)
FLIX_DIALOG_OVERLAY_CONDITION = (
	"Window.IsActive(1111) | "
	"[Window.IsVisible(videos) + !Window.IsActive(videos) + "
	"[Control.IsVisible(56) | Control.IsVisible(57)]]"
)
ACTIVE_POLL_SECONDS = 0.10
IDLE_POLL_SECONDS = 0.75
HOME_WIDGET_IDS = tuple(base + slot * 10 for base in (5801, 5901) for slot in range(6)) + (7100, 7200, 7600, 7700, 7800, 7900) + tuple(range(18011, 18062, 10))


def publish_home_widget_sizes():
	# Container() labels are scoped to the active dialog. Retain the home row's
	# size through context/info dialogs rather than treating a missing label as 0.
	if not xbmc.getCondVisibility("Window.IsActive(home) + !System.HasActiveModalDialog"):
		return
	menu_id = xbmc.getInfoLabel("Container(9000).ListItem.Property(id)")
	menu_filter = {"mylist_movies": "movies", "mylist_tvshows": "tvshows"}.get(menu_id, "")
	if HOME_WINDOW.getProperty("flixium.mylist.menu_filter") != menu_filter:
		HOME_WINDOW.setProperty("flixium.mylist.menu_filter", menu_filter)
	for control_id in HOME_WIDGET_IDS:
		label = xbmc.getInfoLabel("Container({}).NumItems".format(control_id))
		if not label.isdigit():
			continue
		value = "true" if 0 < int(label) < 3 else "false"
		name = "flixium.widgets.{}.short".format(control_id)
		if HOME_WINDOW.getProperty(name) != value:
			HOME_WINDOW.setProperty(name, value)
	control_id = HOME_WINDOW.getFocusId()
	if control_id in HOME_WIDGET_IDS[:12] or control_id in range(18011, 18062, 10) or control_id in tuple(base + slot * 10 for base in (5800, 5900) for slot in range(6)):
		item_id = xbmc.getInfoLabel("Container({}).ListItem.DBID".format(control_id))
		kind = xbmc.getInfoLabel("Container({}).ListItem.DBType".format(control_id))
		prefix = "flixium.widgets.{}.".format(control_id)
		for key, value in (("itemid", item_id), ("kind", kind)):
			if HOME_WINDOW.getProperty(prefix + key) != value:
				HOME_WINDOW.setProperty(prefix + key, value)


LIBRARY_UPDATE_DEBOUNCE_SECONDS = 2.0
GENRE_SPLIT_RE = re.compile(r"\s*(?:/|\||\u2022|\u00b7)\s*|,\s*|;\s*")
GENRE_ABBREVIATIONS = {
	"science fiction": "Sci-Fi",
	"science-fiction": "Sci-Fi",
}


def clear_set_properties():
	HOME_WINDOW.clearProperty(PROPERTY_COUNT)
	HOME_WINDOW.clearProperty(PROPERTY_YEARS)
	HOME_WINDOW.clearProperty(PROPERTY_RUNTIME)


def clear_properties():
	clear_set_properties()
	HOME_WINDOW.clearProperty(PROPERTY_GENRES)
	HOME_WINDOW.clearProperty(PROPERTY_ARTIST_ALBUMS)
	HOME_WINDOW.clearProperty(PROPERTY_ARTIST_TRACKS)
	HOME_WINDOW.clearProperty(PROPERTY_ALBUM_TRACKS)
	HOME_WINDOW.clearProperty(PROPERTY_ALBUM_RUNTIME)


def limited_genres(label, limit=2):
	"""Return the first distinct genres from Kodi's display label."""
	if limit <= 0 or not label:
		return ""
	genres = []
	seen = set()
	for genre in GENRE_SPLIT_RE.split(label):
		genre = " ".join(genre.split())
		genre = GENRE_ABBREVIATIONS.get(genre.casefold(), genre)
		key = genre.casefold()
		if genre and key not in seen:
			genres.append(genre)
			seen.add(key)
			if len(genres) == limit:
				break
	return " / ".join(genres[:limit])


def focused_genre_label():
	"""Read genres from the active Flix list or focused Home widget."""
	if xbmc.getCondVisibility("Window.IsActive(home)"):
		return xbmc.getInfoLabel("Control.GetLabel({})".format(GENRE_CONTROL))
	return xbmc.getInfoLabel("Control.GetLabel({})".format(GENRE_CONTROL))


def formatted_stats(movies):
	count = len(movies)
	count_label = (L(31488) if count == 1 else L(31535)).format(count)

	years = sorted(
		int(movie.get("year", 0))
		for movie in movies
		if int(movie.get("year", 0) or 0) > 0
	)
	if not years:
		years_label = ""
	elif years[0] == years[-1]:
		years_label = str(years[0])
	else:
		years_label = "{}\u2013{}".format(years[0], years[-1])

	total_seconds = sum(int(movie.get("runtime", 0) or 0) for movie in movies)
	total_minutes = total_seconds // 60
	hours = total_minutes // 60
	minutes = total_minutes % 60
	if not hours:
		runtime_label = L(31798).format(minutes)
	elif hours == 1:
		runtime_label = L(31799).format(minutes)
	else:
		runtime_label = L(31800).format(hours, minutes)
	return count_label, years_label, runtime_label


def movie_set_movies(set_id):
	movies, start = [], 0
	while True:
		request = {"jsonrpc": "2.0", "id": 1,
			"method": "VideoLibrary.GetMovieSetDetails",
			"params": {"setid": set_id, "properties": [],
				"movies": {"properties": ["year", "runtime"],
					"limits": {"start": start, "end": start + 500}}}}
		response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
		if "error" in response:
			raise ValueError("Movie-set query failed")
		page = response.get("result", {}).get("setdetails", {}).get("movies", [])
		movies.extend(page)
		if len(page) < 500:
			return movies
		start += len(page)


COUNT_CACHE = {}
ALBUM_RUNTIME_CACHE = {}


def audio_count(method, field, item_id):
	key = (method, field, item_id)
	if key not in COUNT_CACHE:
		request = {"jsonrpc": "2.0", "id": 1, "method": method,
			"params": {"properties": [], "limits": {"start": 0, "end": 1},
				"filter": {field: item_id}}}
		response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
		if "error" in response:
			raise ValueError("Audio-library count request failed")
		result = response.get("result", {})
		if "total" not in result.get("limits", {}):
			raise ValueError("Audio library did not return a total")
		if len(COUNT_CACHE) >= 512:
			COUNT_CACHE.clear()
		COUNT_CACHE[key] = int(result["limits"]["total"])
	return COUNT_CACHE[key]


def artist_album_count(artist_id):
	return audio_count("AudioLibrary.GetAlbums", "artistid", artist_id)


def artist_track_count(artist_id):
	return audio_count("AudioLibrary.GetSongs", "artistid", artist_id)


def album_track_count(album_id):
	return audio_count("AudioLibrary.GetSongs", "albumid", album_id)


def album_runtime(album_id):
	"""Sum song durations in seconds; albums may expose a placeholder zero."""
	if album_id not in ALBUM_RUNTIME_CACHE:
		total_seconds, start = 0, 0
		while True:
			request = {"jsonrpc": "2.0", "id": 1, "method": "AudioLibrary.GetSongs",
				"params": {"properties": ["duration"], "filter": {"albumid": album_id},
					"limits": {"start": start, "end": start + 500}}}
			response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
			if "error" in response:
				raise ValueError("Album runtime query failed")
			result = response.get("result", {})
			songs = result.get("songs", [])
			total_seconds += sum(max(0, int(song.get("duration", 0) or 0)) for song in songs)
			start += len(songs)
			if not songs or start >= result.get("limits", {}).get("total", start + 1) or len(songs) < 500:
				break
		minutes = max(1, total_seconds // 60) if total_seconds > 0 else 0
		if len(ALBUM_RUNTIME_CACHE) >= 512:
			ALBUM_RUNTIME_CACHE.clear()
		ALBUM_RUNTIME_CACHE[album_id] = (L(31798) if minutes == 1 else L(31801)).format(minutes) if minutes else ""
	return ALBUM_RUNTIME_CACHE[album_id]


class SetStatsService(xbmc.Monitor):
	def __init__(self):
		super().__init__()
		self.playback = xbmc.Player()
		self.maturity_source = ""
		self.previous_set_id = None
		self.previous_genre_label = None
		self.previous_artist_id = None
		self.previous_album_id = None
		self.cache = {}
		self.cache_dirty = False
		self.cache_dirty_since = 0.0

	def onNotification(self, _sender, method, _data):
		if method in ("AudioLibrary.OnUpdate", "AudioLibrary.OnRemove", "AudioLibrary.OnScanFinished", "AudioLibrary.OnCleanFinished"):
			COUNT_CACHE.clear()
			ALBUM_RUNTIME_CACHE.clear()
			self.previous_artist_id = None
			self.previous_album_id = None
		if method in (
			"VideoLibrary.OnUpdate",
			"VideoLibrary.OnRemove",
			"VideoLibrary.OnScanFinished",
			"VideoLibrary.OnCleanFinished",
		):
			self.cache_dirty = True
			self.cache_dirty_since = time.monotonic()


	def refresh_dirty_cache(self):
		if not self.cache_dirty:
			return
		if (
			time.monotonic() - self.cache_dirty_since
			< LIBRARY_UPDATE_DEBOUNCE_SECONDS
		):
			return
		self.cache = {}
		self.cache_dirty = False
		self.previous_set_id = None

	def publish(self, set_id):
		if set_id not in self.cache:
			self.cache[set_id] = formatted_stats(movie_set_movies(set_id))
		count_label, years_label, runtime_label = self.cache[set_id]
		HOME_WINDOW.setProperty(PROPERTY_COUNT, count_label)
		HOME_WINDOW.setProperty(PROPERTY_YEARS, years_label)
		HOME_WINDOW.setProperty(PROPERTY_RUNTIME, runtime_label)

	def run(self):
		while not self.abortRequested():
			if xbmc.getSkinDir() == SUPPORTED_SKIN:
				publish_home_widget_sizes()
			if self.playback.isPlayingVideo() and xbmc.getSkinDir() == SUPPORTED_SKIN:
				source = self.playback.getPlayingFile()
				if source != self.maturity_source and xbmc.getCondVisibility("Window.IsVisible(1113)"):
					self.maturity_source = source
					xbmc.executebuiltin("RunScript(special://skin/extras/flixium_maturity.py)")
			else:
				self.maturity_source = ""
			if xbmc.getSkinDir() != SUPPORTED_SKIN:
				clear_properties()
				self.previous_set_id = None
				self.previous_genre_label = None
				self.waitForAbort(2)
				continue

			if not xbmc.getCondVisibility(FLIX_ACTIVE_CONDITION):
				# Keep the last capped genre while a customise/settings dialog is
				# displayed over Flix. Reading Control.GetLabel() from the dialog
				# would return empty and expose Kodi's uncapped ListItem.Genre.
				if xbmc.getCondVisibility(FLIX_DIALOG_OVERLAY_CONDITION):
					self.waitForAbort(ACTIVE_POLL_SECONDS)
					continue
				if (
					self.previous_set_id is not None
					or self.previous_genre_label is not None
				):
					# Set-only statistics are view-specific, but the capped genre must
					# survive focus/window transitions such as opening Customise.
					clear_set_properties()
				self.previous_set_id = None
				self.previous_genre_label = None
				self.previous_artist_id = None
				self.previous_album_id = None
				self.waitForAbort(ACTIVE_POLL_SECONDS if xbmc.getCondVisibility("Window.IsActive(home)") else IDLE_POLL_SECONDS)
				continue

			# Native scrolling can cross many items before focus settles. Keep
			# cached display values and avoid queries for those intermediate items.
			if xbmc.getCondVisibility("Container.Scrolling"):
				self.waitForAbort(ACTIVE_POLL_SECONDS)
				continue

			self.refresh_dirty_cache()

			db_type = xbmc.getInfoLabel(
				"Control.GetLabel({})".format(SET_TYPE_CONTROL)
			).lower() or xbmc.getInfoLabel("ListItem.DBType").lower()
			if xbmc.getCondVisibility("Window.IsActive(music) + Container.Content(albums)"):
				db_type = "album"
			genre_label = focused_genre_label()
			if genre_label != self.previous_genre_label:
				self.previous_genre_label = genre_label
				trimmed_genres = limited_genres(genre_label)
				if trimmed_genres:
					HOME_WINDOW.setProperty(PROPERTY_GENRES, trimmed_genres)
				else:
					HOME_WINDOW.clearProperty(PROPERTY_GENRES)
			set_id_label = xbmc.getInfoLabel(
				"Control.GetLabel({})".format(SET_ID_CONTROL)
			)
			if db_type in ("artist", "album") and not set_id_label:
				set_id_label = xbmc.getInfoLabel("ListItem.DBID")
			try:
				artist_id = int(set_id_label) if db_type == "artist" else None
			except (TypeError, ValueError):
				artist_id = None
			if artist_id != self.previous_artist_id:
				self.previous_artist_id = artist_id
				HOME_WINDOW.clearProperty(PROPERTY_ARTIST_ALBUMS)
				HOME_WINDOW.clearProperty(PROPERTY_ARTIST_TRACKS)
				if artist_id is not None:
					try:
						album_count = artist_album_count(artist_id)
						if album_count:
							label = (L(31802) if album_count == 1 else L(31803)).format(album_count)
							HOME_WINDOW.setProperty(PROPERTY_ARTIST_ALBUMS, label)
						track_count = artist_track_count(artist_id)
						if track_count:
							label = (L(31804) if track_count == 1 else L(31805)).format(track_count)
							HOME_WINDOW.setProperty(PROPERTY_ARTIST_TRACKS, label)
					except Exception as error:
						xbmc.log(
							"Flixium artist library counts failed: {}".format(error),
							xbmc.LOGWARNING,
						)
			try:
				album_id = int(set_id_label) if db_type == "album" else None
			except (TypeError, ValueError):
				album_id = None
			if db_type == "album":
				# During a view refresh Kodi can briefly expose an empty ID. Keep the
				# last valid count through that transition instead of flashing it away.
				if album_id is not None and album_id != self.previous_album_id:
					self.previous_album_id = album_id
					HOME_WINDOW.clearProperty(PROPERTY_ALBUM_TRACKS)
					HOME_WINDOW.clearProperty(PROPERTY_ALBUM_RUNTIME)
					try:
						track_count = album_track_count(album_id)
						if track_count:
							label = (L(31804) if track_count == 1 else L(31805)).format(track_count)
							HOME_WINDOW.setProperty(PROPERTY_ALBUM_TRACKS, label)
						runtime = album_runtime(album_id)
						if runtime:
							HOME_WINDOW.setProperty(PROPERTY_ALBUM_RUNTIME, runtime)
					except Exception as error:
						xbmc.log(
							"Flixium album statistics failed: {}".format(error),
							xbmc.LOGWARNING,
						)
			elif db_type and self.previous_album_id is not None:
				# A confirmed non-album item means the old album count is no longer
				# relevant. Empty metadata is intentionally ignored above.
				self.previous_album_id = None
				HOME_WINDOW.clearProperty(PROPERTY_ALBUM_TRACKS)
				HOME_WINDOW.clearProperty(PROPERTY_ALBUM_RUNTIME)
			try:
				set_id = int(set_id_label) if db_type == "set" else None
			except (TypeError, ValueError):
				set_id = None

			if set_id != self.previous_set_id:
				self.previous_set_id = set_id
				if set_id is None:
					clear_set_properties()
				else:
					try:
						self.publish(set_id)
					except Exception as error:
						clear_set_properties()
						xbmc.log(
							"Flixium set statistics failed: {}".format(error),
							xbmc.LOGERROR,
						)

			self.waitForAbort(ACTIVE_POLL_SECONDS)


if __name__ == "__main__":
	SetStatsService().run()
