"""Select the native cover visualizer once; preserve later user selections."""

from flixium_localization import localize as L
import json
import sys

import xbmc

ADDON = "visualization.flixium"
CONFIGURED = "Flixium.NativeVisualizerConfigured"


def rpc(method, params):
    reply = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1,
                                                     "method": method, "params": params})))
    if "error" in reply:
        raise RuntimeError(str(reply["error"]))
    return reply.get("result")


def main(settings=False):
    if not settings and xbmc.getCondVisibility("Skin.HasSetting({})".format(CONFIGURED)):
        return
    try:
        rpc("Addons.SetAddonEnabled", {"addonid": ADDON, "enabled": True})
        selected = rpc("Settings.SetSettingValue", {"setting": "musicplayer.visualisation", "value": ADDON})
        if selected is not True:
            raise RuntimeError(L(31737))
        xbmc.executebuiltin("Skin.SetBool(FlixiumMusicVisualiserBackground)")
        xbmc.executebuiltin("Skin.SetBool({})".format(CONFIGURED))
        if settings:
            xbmc.executebuiltin("Addon.OpenSettings({})".format(ADDON))
    except Exception as error:
        xbmc.log("Flixium Visualizer setup: {}".format(error), xbmc.LOGWARNING)


if __name__ == "__main__":
    main(len(sys.argv) > 1 and sys.argv[1] == "settings")
