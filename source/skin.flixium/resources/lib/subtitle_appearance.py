"""Native subtitle appearance settings; no subtitle rendering in the skin."""
import json

class NativeSettings:
    def __init__(self, execute):
        self.execute = execute
        self.definitions = {}

    def rpc(self, method, params):
        response = json.loads(self.execute(json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})))
        if "error" in response:
            raise ValueError(response["error"].get("message", "Kodi rejected the setting"))
        return response.get("result")

    def refresh(self):
        result = self.rpc("Settings.GetSettings", {
            "level": "expert", "filter": {"section": "player", "category": "subtitles"}})
        self.definitions = {s["id"]: s for s in result.get("settings", [])}
        # Some Kodi versions omit colour-picker controls from GetSettings.
        # Their native values are still available individually.
        for key in ("subtitles.colorpick", "subtitles.bordercolorpick",
                    "subtitles.shadowcolor", "subtitles.bgcolorpick"):
            if key not in self.definitions:
                try:
                    value = self.rpc("Settings.GetSettingValue", {"setting": key})
                    self.definitions[key] = {"id": key, "value": value["value"]}
                except ValueError:
                    continue

    def get(self, setting):
        return self.definitions[setting]["value"]

    def set(self, setting, value):
        if setting not in self.definitions:
            raise ValueError("This Kodi version does not support that setting")
        if self.get(setting) == value:
            return
        if self.rpc("Settings.SetSettingValue", {"setting": setting, "value": value}) is not True:
            raise ValueError("Kodi could not apply that setting")
        self.definitions[setting]["value"] = value

    def font_options(self):
        return tuple((str(o["label"]), o["value"])
                     for o in self.definitions.get("subtitles.fontname", {}).get("options", []))

    def apply_preset(self, installed_font=None):
        fonts = self.font_options()
        font = next((value for label, value in fonts
                     if "netflix sans" in (label + " " + str(value)).lower()), None)
        if font is None:
            font = installed_font
        if font is None:
            raise ValueError("Restart Kodi to make the installed Netflix Sans font available")
        values = {"subtitles.fontname": font, "subtitles.fontsize": 42,
                  "subtitles.style": 0, "subtitles.colorpick": "FFFFFFFF",
                  "subtitles.opacity": 100, "subtitles.backgroundtype": 1,
                  "subtitles.bordersize": 0, "subtitles.shadowcolor": "FF000000",
                  "subtitles.shadowopacity": 100, "subtitles.shadowsize": 15}
        previous = {key: self.get(key) for key in values if key in self.definitions}
        changed = []
        try:
            for key, value in values.items():
                if key in previous:
                    self.set(key, value)
                    changed.append(key)
        except ValueError:
            for key in reversed(changed):
                self.set(key, previous[key])
            raise
