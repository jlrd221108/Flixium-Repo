"""Measure installed add-on labels for the wall's normal 256 x 56 text area."""
import json
import os
import re
import xml.etree.ElementTree as ET


def label_fits(text, measure, line_height, width=256, height=56):
    """Wrap on words, splitting oversized words, before checking the height."""
    text = re.sub(r"\[/?(?:B|I|LIGHT|COLOR(?: [^]]+)?)\]", "", text,
                  flags=re.IGNORECASE).replace("[CR]", "\n")
    lines = 0
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = (line + " " + word).strip()
            if measure(candidate) <= width:
                line = candidate
                continue
            if line:
                lines += 1
                line = ""
            for character in word:
                if line and measure(line + character) > width:
                    lines += 1
                    line = ""
                line += character
        lines += 1
    return lines * line_height <= height


def refresh():
    import xbmc
    import xbmcgui
    import xbmcvfs
    from PIL import ImageFont

    def rpc(method, params):
        response = json.loads(xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        })))
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        return response["result"]

    skin = xbmcvfs.translatePath("special://skin/")
    font_name = rpc("Settings.GetSettingValue", {"setting": "lookandfeel.font"})["value"]
    font_sets = ET.parse(os.path.join(skin, "xml", "Font.xml")).getroot().findall("fontset")
    font_set = next((item for item in font_sets if item.get("id") == font_name), font_sets[0])
    definition = font_set.find("font[name='font12']")
    filename = definition.findtext("filename")
    font_path = (xbmcvfs.translatePath(filename) if filename.startswith("special://")
                 else os.path.join(skin, "fonts", filename))
    font = ImageFont.truetype(font_path, int(definition.findtext("size")))
    aspect = float(definition.findtext("aspect", "1"))
    spacing = float(definition.findtext("linespacing", "1"))
    line_height = sum(font.getmetrics()) * spacing

    def measure(text):
        return (font.getlength(text) if hasattr(font, "getlength")
                else font.getsize(text)[0]) * aspect

    normal, small = [], []
    addons = rpc("Addons.GetAddons", {"properties": ["name"]}).get("addons", [])
    for addon in addons:
        label = addon.get("name", "")
        if label:
            (normal if label_fits(label, measure, line_height) else small).append(label)
    window = xbmcgui.Window(10000)
    window.setProperty("flixium.addonlabels.normal", "\n".join(normal))
    window.setProperty("flixium.addonlabels.small", "\n".join(small))


if __name__ == "__main__":
    try:
        refresh()
    except Exception as error:
        import xbmc
        xbmc.log("[Flixium] Cannot measure add-on labels: {}".format(error), xbmc.LOGWARNING)
