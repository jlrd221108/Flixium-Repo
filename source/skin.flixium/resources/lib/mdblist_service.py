#!/usr/bin/python
# coding: utf-8

"""Fetch and publish MDBList ratings for focused movies and movie information."""

import json
import os
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON_ID = "skin.flixium"
API_BASE_URL = "https://api.mdblist.com"
API_KEY_SETTING = "Flixium.MDBListApiKey"
# Old entries may already contain a twice-converted Letterboxd score.
CACHE_FILENAME = "mdblist_ratings_cache_v2.json"
CACHE_SCHEMA = 2
SHOW_ID_CACHE = {}
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
POLL_SECONDS = 0.25
FOCUS_DEBOUNCE_SECONDS = 0.65
REQUEST_TIMEOUT_SECONDS = 12
MOVIE_INFORMATION_WINDOW_ID = 12003
FLIX_IMDB_CONTROL = 56004
FLIX_TMDB_CONTROL = 56005
INFO_PREFIX = "flixium.info."
RATING_PREFIX = "flixium.mdblist.rating."
RATING_IMAGE_PATH = "special://skin/resources/rating_images/"
SERVICE_RUNNING_PROPERTY = "flixium.mdblist.service.running"
RATING_SOURCES = (
	"mdblist",
	"imdb",
	"tmdb",
	"metacritic",
	"trakt",
	"tomatoes",
	"audience",
	"letterboxd",
)
SOURCE_ALIASES = {
	"letterbox": "letterboxd",
	"letterboxd": "letterboxd",
	"metacritic": "metacritic",
	"mdblist": "mdblist",
	"imdb": "imdb",
	"tmdb": "tmdb",
	"trakt": "trakt",
	"rotten tomatoes": "tomatoes",
	"rottentomatoes": "tomatoes",
	"rt": "tomatoes",
	"tomatoes": "tomatoes",
	"audience": "audience",
	"popcorn": "audience",
	"rtaudience": "audience",
	"tomatoesaudience": "audience",
}
FIXED_RATING_IMAGES = {
	"mdblist": "mdblist.png",
	"imdb": "imdb.png",
	"tmdb": "tmdb.png",
	"metacritic": "metacritic.png",
	"trakt": "trakt.png",
	"letterboxd": "letterboxd.png",
}
HOME_WINDOW = xbmcgui.Window(10000)
ADDON = xbmcaddon.Addon(ADDON_ID)


def get_api_key():
	# Read only: saving here can trigger onSettingsChanged and re-enter this code.
	key = xbmc.getInfoLabel("Skin.String({})".format(API_KEY_SETTING)).strip()
	if not key and not xbmc.getCondVisibility("Skin.HasSetting(Flixium.MDBListApiKeyManaged)"):
		key = ADDON.getSetting("mdblist_api_key").strip()
	configured = "true" if key else ""
	if HOME_WINDOW.getProperty("flixium.mdblist.key_configured") != configured:
		HOME_WINDOW.setProperty("flixium.mdblist.key_configured", configured)
	return key


def cache_path():
	profile = xbmcvfs.translatePath("special://profile/addon_data/{}/".format(ADDON_ID))
	return os.path.join(profile, CACHE_FILENAME)


def load_cache():
	path = cache_path()
	try:
		with open(path, "r", encoding="utf-8") as cache_file:
			data = json.load(cache_file)
			if not isinstance(data, dict) or data.get("schema") != CACHE_SCHEMA:
				return {}
			entries = data.get("entries", {})
			if not isinstance(entries, dict):
				return {}
			return {key: entry for key, entry in entries.items()
				if isinstance(entry, dict) and isinstance(entry.get("updated"), (int, float))
				and time.time() - entry["updated"] <= CACHE_MAX_AGE_SECONDS}
	except (OSError, ValueError, TypeError):
		return {}


def save_cache(cache):
	path = cache_path()
	temporary = None
	try:
		xbmcvfs.mkdirs(os.path.dirname(path))
		with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path), delete=False) as cache_file:
			temporary = cache_file.name
			json.dump({"schema": CACHE_SCHEMA, "entries": cache}, cache_file, ensure_ascii=False, separators=(",", ":"))
		os.replace(temporary, path)
		return True
	except OSError as error:
		xbmc.log(
			"Flixium could not save the MDBList ratings cache: {}".format(error),
			xbmc.LOGWARNING,
		)
		return False
	finally:
		if temporary and os.path.exists(temporary):
			os.remove(temporary)


def compact_number(value, fixed_decimal=False):
	try:
		number = float(value)
	except (TypeError, ValueError):
		return str(value).strip() if value is not None else ""
	if fixed_decimal:
		return "{:.1f}".format(number)
	if number.is_integer():
		return str(int(number))
	return ("{:.1f}".format(number)).rstrip("0").rstrip(".")


def rating_label(source, rating):
	value = rating.get("value")
	if value in (None, ""):
		value = rating.get("score")
	try:
		number = float(value)
	except (TypeError, ValueError):
		number = None
	if number is not None:
		if source in ("trakt", "tmdb") and number > 10:
			value = number / 10.0
		elif source == "letterboxd" and number <= 5:
			value = number * 2.0
	label = compact_number(value, fixed_decimal=source not in ("metacritic", "tomatoes", "audience"))
	if not label:
		return ""
	if source in ("metacritic", "tomatoes", "audience"):
		return "{}%".format(label)
	return label


def normalized_ratings(payload):
	result = {}
	score = payload.get("score_average")
	if score in (None, "", 0):
		score = payload.get("score")
	if score not in (None, ""):
		result["mdblist"] = compact_number(score, fixed_decimal=True)

	keywords = payload.get("keywords") or []
	result["_tomatoes_certified"] = any(
		isinstance(keyword, dict)
		and str(keyword.get("name", "")).casefold() == "certified-fresh"
		for keyword in keywords
	)
	for rating in payload.get("ratings") or []:
		if not isinstance(rating, dict):
			continue
		source_name = str(rating.get("source", "")).strip().casefold()
		source = SOURCE_ALIASES.get(source_name)
		if not source:
			continue
		label = rating_label(source, rating)
		if label:
			result[source] = label
	return result


def normalize_cached_ratings(ratings):
	"""Cached v2 values are display labels, never raw provider scores."""
	result = {}
	for source, value in ratings.items():
		if source.startswith("_"):
			result[source] = value
			continue
		if source not in RATING_SOURCES:
			continue
		text = str(value).strip()
		if not text:
			continue
		if source in ("metacritic", "tomatoes", "audience"):
			text = text.rstrip("%").strip()
		formatted = compact_number(text, fixed_decimal=source not in ("metacritic", "tomatoes", "audience"))
		if source in ("metacritic", "tomatoes", "audience"):
			formatted += "%"
		if formatted:
			result[source] = formatted
	return result


def fetch_ratings(api_key, provider, media_id, media_type):
	path = "{}/{}/{}/{}".format(
		API_BASE_URL,
		provider,
		media_type,
		quote(str(media_id).strip(), safe=""),
	)
	url = "{}?{}".format(
		path,
		urlencode({"apikey": api_key, "append_to_response": "keyword"}),
	)
	request = Request(
		url,
		headers={
			"Accept": "application/json",
			"User-Agent": "Flixium/1.0 MDBList ratings",
		},
	)
	with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
		payload = json.loads(response.read().decode("utf-8"))
	if not isinstance(payload, dict):
		raise ValueError("MDBList returned an unexpected response")
	return normalized_ratings(payload)


def clear_rating_properties(window):
	for source in RATING_SOURCES:
		window.clearProperty(RATING_PREFIX + source)
		window.clearProperty(RATING_PREFIX + source + ".icon")
	window.clearProperty(RATING_PREFIX + "available")


def numeric_label(label):
	try:
		return float(str(label).rstrip("%"))
	except (TypeError, ValueError):
		return 0.0


def rating_image(source, label, ratings):
	if source in FIXED_RATING_IMAGES:
		return RATING_IMAGE_PATH + FIXED_RATING_IMAGES[source]
	value = numeric_label(label)
	if source == "tomatoes":
		if ratings.get("_tomatoes_certified"):
			filename = "rtcertified.png"
		elif value >= 60:
			filename = "rtfresh.png"
		else:
			filename = "rtrotten.png"
		return RATING_IMAGE_PATH + filename
	if source == "audience":
		filename = "popcorn.png" if value >= 60 else "popcorn_spilt.png"
		return RATING_IMAGE_PATH + filename
	return ""


def publish_ratings(window, ratings):
	clear_rating_properties(window)
	for source, label in ratings.items():
		if source in RATING_SOURCES and label:
			window.setProperty(RATING_PREFIX + source, label)
			icon = rating_image(source, label, ratings)
			if icon:
				window.setProperty(RATING_PREFIX + source + ".icon", icon)
	if any(ratings.get(source) for source in RATING_SOURCES):
		window.setProperty(RATING_PREFIX + "available", "true")


def parent_show_ids(db_id):
	try:
		show_id = int(str(db_id).strip())
	except (TypeError, ValueError):
		return {}
	if show_id in SHOW_ID_CACHE:
		return SHOW_ID_CACHE[show_id]
	request = json.dumps({
		"jsonrpc": "2.0",
		"method": "VideoLibrary.GetTVShowDetails",
		"params": {"tvshowid": show_id, "properties": ["uniqueid"]},
		"id": "flixium-ratings",
	})
	try:
		result = json.loads(xbmc.executeJSONRPC(request))
		if "error" in result:
			return {}
		ids = result.get("result", {}).get("tvshowdetails", {}).get("uniqueid") or {}
		if len(SHOW_ID_CACHE) >= 512:
			SHOW_ID_CACHE.clear()
		SHOW_ID_CACHE[show_id] = ids
		return ids
	except (TypeError, ValueError, AttributeError):
		return {}

def dialog_media_identity():
	window = xbmcgui.Window(MOVIE_INFORMATION_WINDOW_ID)
	dbtype = window.getProperty(INFO_PREFIX + "dbtype").casefold()
	if dbtype not in ("movie", "tvshow"):
		return None
	media_type = "movie" if dbtype == "movie" else "show"
	imdb_id = window.getProperty(INFO_PREFIX + "imdb").strip()
	cache_id = imdb_id or window.getProperty(INFO_PREFIX + "tmdb").strip()
	if media_type == "show":
		ids = parent_show_ids(window.getProperty(INFO_PREFIX + "tvshowdbid") or window.getProperty(INFO_PREFIX + "dbid"))
		imdb_id = str(ids.get("imdb", "")).strip() or imdb_id
		tmdb_id = str(ids.get("tmdb", "")).strip()
		if imdb_id:
			return "imdb", imdb_id, media_type, cache_id or imdb_id
		if tmdb_id:
			return "tmdb", tmdb_id, media_type, cache_id or tmdb_id
	if imdb_id:
		return "imdb", imdb_id, media_type, cache_id or imdb_id
	tmdb_id = window.getProperty(INFO_PREFIX + "tmdb").strip()
	if tmdb_id:
		return "tmdb", tmdb_id, media_type, cache_id or tmdb_id
	return None


def flix_media_identity():
	dbtype = xbmc.getInfoLabel("Control.GetLabel(56002)").casefold()
	if dbtype not in ("movie", "tvshow"):
		return None
	media_type = "movie" if dbtype == "movie" else "show"
	imdb_id = xbmc.getInfoLabel("ListItem.Property(imdb)").strip() or xbmc.getInfoLabel("ListItem.IMDBNumber").strip() or xbmc.getInfoLabel(
		"Control.GetLabel({})".format(FLIX_IMDB_CONTROL)
	).strip()
	tmdb_direct = xbmc.getInfoLabel("ListItem.Property(TMDb_ID)").strip() or xbmc.getInfoLabel("ListItem.Property(tmdb)").strip() or xbmc.getInfoLabel(
		"Control.GetLabel({})".format(FLIX_TMDB_CONTROL)
	).strip()
	cache_id = imdb_id or tmdb_direct
	if media_type == "show":
		ids = parent_show_ids(xbmc.getInfoLabel("ListItem.TVShowDBID") or xbmc.getInfoLabel("ListItem.DBID"))
		imdb_id = str(ids.get("imdb", "")).strip() or imdb_id
		tmdb_id = str(ids.get("tmdb", "")).strip()
		if imdb_id:
			return "imdb", imdb_id, media_type, cache_id or imdb_id
		if tmdb_id:
			return "tmdb", tmdb_id, media_type, cache_id or tmdb_id
	if imdb_id:
		return "imdb", imdb_id, media_type, cache_id or imdb_id
	if tmdb_direct:
		return "tmdb", tmdb_direct, media_type, cache_id or tmdb_direct
	return None


def active_movie_identity():
	if xbmc.getCondVisibility("Window.IsActive(movieinformation)"):
		return dialog_media_identity()
	if xbmc.getCondVisibility(
		"Window.IsActive(videos) + [Control.IsVisible(56) | Control.IsVisible(57)]"
	):
		return flix_media_identity()
	return None


def nearby_media_identities(current):
	"""Prefetch the next two and previous movie/show, after focus has settled."""
	if not xbmc.getCondVisibility("Window.IsActive(videos) + Control.IsVisible(56)") or current[2] not in ("movie", "show"):
		return []
	result, seen = [], {current}
	for offset in (1, 2, -1):
		prefix = "Container(56).ListItem({}).".format(offset)
		expected_type = "movie" if current[2] == "movie" else "tvshow"
		if xbmc.getInfoLabel(prefix + "DBType").casefold() != expected_type:
			continue
		imdb = xbmc.getInfoLabel(prefix + "IMDBNumber").strip()
		tmdb = xbmc.getInfoLabel(prefix + "Property(TMDb_ID)").strip() or xbmc.getInfoLabel(prefix + "Property(tmdb)").strip()
		cache_id = imdb or tmdb
		if current[2] == "show":
			# Match focused-show resolution; IMDb/TMDb IDs must identify the show.
			ids = parent_show_ids(xbmc.getInfoLabel(prefix + "DBID"))
			imdb = str(ids.get("imdb", "")).strip() or imdb
			tmdb = str(ids.get("tmdb", "")).strip() or tmdb
		if current[2] == "movie":
			identity = ("imdb", imdb, "movie", imdb) if imdb.startswith("tt") else (("tmdb", tmdb, "movie", tmdb) if tmdb.isdigit() else None)
		else:
			identity = ("imdb", imdb, "show", cache_id or imdb) if imdb.startswith("tt") else (("tmdb", tmdb, "show", cache_id or tmdb) if tmdb.isdigit() else None)
		if identity and identity not in seen:
			seen.add(identity)
			result.append(identity)
	return result


class MDBListRatingsService(xbmc.Monitor):
	def __init__(self):
		super().__init__()
		self.cache = load_cache()
		self.previous_request = None
		self.published_request = None
		self.focus_changed_at = 0.0
		self.retry_at = 0.0
		self.retry_delay = 2.0
		self.cache_dirty = False
		self.flushed_at = time.monotonic()
		self.executor = None
		self.pending_fetch = None
		self.pending_identity = None
		self.network_retry_at = 0.0
		self.network_retry_delay = 2.0
		get_api_key()

	def onSettingsChanged(self):
		# Never save or migrate settings from a save notification.
		self.previous_request = None

	def onNotification(self, _sender, method, _data):
		if method.startswith("VideoLibrary."):
			SHOW_ID_CACHE.clear()
			self.previous_request = None

	def flush_cache(self, force=False):
		if self.cache_dirty and (force or time.monotonic() - self.flushed_at >= 5):
			cutoff = time.time() - CACHE_MAX_AGE_SECONDS
			self.cache = {key: value for key, value in self.cache.items() if value.get("updated", 0) >= cutoff}
			if save_cache(self.cache):
				self.cache_dirty = False
			self.flushed_at = time.monotonic()

	def cached_ratings(self, cache_key):
		entry = self.cache.get(cache_key)
		if not isinstance(entry, dict):
			return None
		try:
			age = time.time() - float(entry.get("updated", 0))
		except (TypeError, ValueError):
			return None
		if age > CACHE_MAX_AGE_SECONDS:
			return None
		ratings = entry.get("ratings")
		if not isinstance(ratings, dict):
			return None
		normalized = normalize_cached_ratings(ratings)
		if normalized != ratings:
			entry["ratings"] = normalized
			self.cache[cache_key] = entry
			self.cache_dirty = True
		return normalized

	def store_ratings(self, cache_key, ratings):
		self.cache[cache_key] = {
			"updated": int(time.time()),
			"ratings": ratings,
		}
		self.cache_dirty = True

	def cached_for_identity(self, identity):
		"""Return a fresh cache entry using both display and lookup identifiers.

		The Kodi item can expose a parent/provider id that is different from the
		identifier used when the entry was originally cached.  Checking both keeps
		revisits on the zero-delay cache path instead of falling through to the
		focus debounce timer.
		"""
		provider, media_id, media_type, cache_id = identity
		candidates = []
		for value in (cache_id, media_id):
			value = str(value or "").strip()
			if value and value not in candidates:
				candidates.append(value)
		for value in candidates:
			cache_key = "{}:{}:{}".format(provider, media_type, value)
			ratings = self.cached_ratings(cache_key)
			if ratings is not None:
				return ratings, cache_key
		# Preserve the pre-TV cache format for existing movie entries.
		if media_type == "movie":
			legacy_key = "{}:{}".format(provider, media_id)
			ratings = self.cached_ratings(legacy_key)
			if ratings is not None:
				return ratings, legacy_key
		return None, None

	def update_ratings(self, window, api_key, identity):
		provider, media_id, media_type, cache_id = identity
		cache_key = "{}:{}:{}".format(provider, media_type, cache_id)
		ratings, matched_key = self.cached_for_identity(identity)
		if ratings is None:
			ratings = fetch_ratings(api_key, provider, media_id, media_type)
			self.store_ratings(cache_key, ratings)
		elif matched_key != cache_key:
			# Migrate an alias hit so subsequent revisits use the canonical key.
			self.store_ratings(cache_key, ratings)
		if (xbmc.getSkinDir() == ADDON_ID
			and xbmc.getCondVisibility("Skin.HasSetting(FlixiumRatingsEnabled)")
			and get_api_key() == api_key
			and active_movie_identity() == identity):
			publish_ratings(window, ratings)
			return True
		return False

	def start_fetch(self, api_key, identity):
		# No queue: a newly selected movie gets priority over further prefetches.
		if self.pending_fetch is not None or time.monotonic() < self.network_retry_at:
			return False
		if self.executor is None:
			self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="FlixiumRatings")
		self.pending_identity = identity
		self.pending_fetch = self.executor.submit(fetch_ratings, api_key, *identity[:3])
		return True

	def collect_fetch(self):
		if self.pending_fetch is None or not self.pending_fetch.done():
			return
		future, identity = self.pending_fetch, self.pending_identity
		self.pending_fetch = self.pending_identity = None
		try:
			ratings = future.result()
		except (HTTPError, URLError, OSError, ValueError) as error:
			self.network_retry_at = time.monotonic() + self.network_retry_delay
			self.network_retry_delay = min(300.0, self.network_retry_delay * 2)
			# Never log a request URL or credentials.
			detail = "HTTP {}".format(error.code) if isinstance(error, HTTPError) else type(error).__name__
			xbmc.log("Flixium ratings request failed: " + detail, xbmc.LOGWARNING)
			return
		self.network_retry_at = 0.0
		self.network_retry_delay = 2.0
		self.store_ratings("{}:{}:{}".format(identity[0], identity[2], identity[3]), ratings)

	def show_cached(self, request_key, identity):
		cached, matched_key = self.cached_for_identity(identity)
		if cached is None:
			return False
		publish_ratings(HOME_WINDOW, cached)
		canonical = "{}:{}:{}".format(identity[0], identity[2], identity[3])
		if matched_key != canonical:
			self.store_ratings(canonical, cached)
		self.published_request = request_key
		return True

	def run(self):
		try:
			while not self.abortRequested():
				self.collect_fetch()
				self.flush_cache()
				if xbmc.getSkinDir() != ADDON_ID or not xbmc.getCondVisibility("Skin.HasSetting(FlixiumRatingsEnabled)"):
					if self.previous_request is not None:
						clear_rating_properties(HOME_WINDOW)
					self.previous_request = self.published_request = None
					self.waitForAbort(POLL_SECONDS)
					continue
				if xbmc.getCondVisibility("Window.IsActive(DialogContextMenu.xml)"):
					self.waitForAbort(POLL_SECONDS)
					continue
				identity = active_movie_identity()
				if identity is None:
					if self.previous_request is not None:
						clear_rating_properties(HOME_WINDOW)
					self.previous_request = self.published_request = None
					self.waitForAbort(POLL_SECONDS)
					continue
				api_key = get_api_key()
				request_key = (api_key, identity[0], identity[2], identity[3])
				if request_key != self.previous_request:
					self.previous_request = request_key
					self.published_request = None
					self.focus_changed_at = time.monotonic()
					clear_rating_properties(HOME_WINDOW)
				# Cache hits are independent of debounce, scrolling and in-flight I/O.
				if api_key and self.published_request != request_key:
					self.show_cached(request_key, identity)
				settled = time.monotonic() - self.focus_changed_at
				if api_key and settled >= FOCUS_DEBOUNCE_SECONDS and not xbmc.getCondVisibility("Container.Scrolling"):
					if self.published_request != request_key:
						self.start_fetch(api_key, identity)
					elif self.pending_fetch is None and settled >= 1.0:
						for neighbor in nearby_media_identities(identity):
							if self.cached_for_identity(neighbor)[0] is None:
								self.start_fetch(api_key, neighbor)
								break
				self.waitForAbort(POLL_SECONDS)
		finally:
			if self.executor is not None:
				self.executor.shutdown(wait=False, cancel_futures=True)
			self.flush_cache(force=True)


if __name__ == "__main__":
	if HOME_WINDOW.getProperty(SERVICE_RUNNING_PROPERTY) != "true":
		HOME_WINDOW.setProperty(SERVICE_RUNNING_PROPERTY, "true")
		xbmc.log("Flixium MDBList ratings service started", xbmc.LOGINFO)
		try:
			MDBListRatingsService().run()
		finally:
			clear_rating_properties(HOME_WINDOW)
			HOME_WINDOW.clearProperty(SERVICE_RUNNING_PROPERTY)
