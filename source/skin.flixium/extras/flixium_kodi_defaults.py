"""Apply the small Kodi-wide defaults requested for a fresh Flixium profile.

Startup.xml invokes this only before Flixium.DefaultsVersion is initialised.
There is no settings monitor or callback and no repeated enforcement.
"""

from flixium_localization import localize as L
import json
import xbmc

MARKER = "Flixium.KodiDefaultsApplied"


def apply_defaults(execute):
    def rpc(method, params):
        response = json.loads(execute(json.dumps({"jsonrpc": "2.0", "id": 1,
                                                 "method": method, "params": params})))
        if "error" in response:
            raise ValueError(response["error"].get("message", L(31731)))
        return response.get("result")
    setting = "musicfiles.selectaction"
    current = rpc("Settings.GetSettingValue", {"setting": setting})
    if not isinstance(current, dict) or type(current.get("value")) is not bool:
        raise ValueError(L(31730))
    if not current["value"]:
        if rpc("Settings.SetSettingValue", {"setting": setting, "value": True}) is not True:
            raise ValueError(L(31732))


def main():
    from flixium_first_install import apply
    apply()
    if xbmc.getCondVisibility("Skin.HasSetting({})".format(MARKER)):
        return
    try:
        apply_defaults(xbmc.executeJSONRPC)
        xbmc.executebuiltin("Skin.SetBool({})".format(MARKER))
    except (ValueError, TypeError) as error:
        xbmc.log("Flixium first-use Kodi defaults: {}".format(error), xbmc.LOGWARNING)


if __name__ == "__main__":
    main()
