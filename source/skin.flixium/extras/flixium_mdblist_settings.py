#!/usr/bin/python
# coding: utf-8

"""Configure the MDBList API key from Flixium's own settings panel."""

from flixium_localization import localize as L

import re

import xbmc
import xbmcaddon
import xbmcgui


SETTING_ID = "Flixium.MDBListApiKey"
API_KEY_RE = re.compile(r"^[A-Za-z0-9]+$")


def get_api_key():
	key = xbmc.getInfoLabel("Skin.String({})".format(SETTING_ID)).strip()
	if key or xbmc.getCondVisibility("Skin.HasSetting(Flixium.MDBListApiKeyManaged)"):
		return key
	return xbmcaddon.Addon("skin.flixium").getSetting("mdblist_api_key").strip()


def set_api_key(value):
	# Skin credentials use native skin storage. Addon.setSetting immediately saves
	# and dispatches settings callbacks; do not use it as a migration mechanism.
	if value:
		xbmc.executebuiltin("Skin.SetString({},{})".format(SETTING_ID, value), True)
	else:
		xbmc.executebuiltin("Skin.Reset({})".format(SETTING_ID), True)
	xbmc.executebuiltin("Skin.SetBool(Flixium.MDBListApiKeyManaged)", True)
	xbmcgui.Window(10000).setProperty("flixium.mdblist.key_configured", "true" if value else "")


def configure_api_key():
	keyboard = xbmc.Keyboard(
		get_api_key(),
		L(31490),
		True,
	)
	keyboard.doModal()
	if not keyboard.isConfirmed():
		return

	api_key = keyboard.getText().strip()
	if api_key and not API_KEY_RE.match(api_key):
		xbmcgui.Dialog().notification(
			L(31493),
			L(31494),
			xbmcgui.NOTIFICATION_ERROR,
			3000,
		)
		return

	set_api_key(api_key)
	message = L(31491) if api_key else L(31492)
	xbmcgui.Dialog().notification(
		L(31493),
		message,
		xbmcgui.NOTIFICATION_INFO,
		2500,
	)


if __name__ == "__main__":
	configure_api_key()
