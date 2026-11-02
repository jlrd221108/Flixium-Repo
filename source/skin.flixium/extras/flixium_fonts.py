"""On-demand font choices for the home menu and shared settings text."""

from flixium_localization import localize as L
import xbmc
import xbmcgui
from flixium_reload import request_reload

def main():
    dialog = xbmcgui.Dialog()
    roles = [("Menu", L(31461)), ("Global", L(31462))]
    changed = False
    while True:
        row = dialog.select(L(31290), [label for key, label in roles])
        if row < 0:
            break
        key, label = roles[row]
        names = [L(31463), L(31464), L(31465), L(31466)]
        values = ["", "inter", "opensans", "roboto"]
        if key == "Menu":
            names.append(L(31467))
            values.append("aeon")
        setting = "Flixium.Font." + key
        current = xbmc.getInfoLabel("Skin.String(" + setting + ")")
        if key == "Menu" and not current and xbmc.getCondVisibility("Skin.HasSetting(Flixium.HomeMenu.AeonFont)"):
            current = "aeon"
        selection = dialog.select(label, names, preselect=values.index(current) if current in values else 0)
        if selection < 0:
            continue
        value = values[selection]
        xbmc.executebuiltin("Skin.SetString({},{})".format(setting, value) if value else "Skin.Reset({})".format(setting), True)
        if key == "Menu":
            xbmc.executebuiltin("Skin.Reset(Flixium.HomeMenu.AeonFont)", True)
        changed = True
    if changed:
        request_reload(9044)

if __name__ == "__main__":
    main()
