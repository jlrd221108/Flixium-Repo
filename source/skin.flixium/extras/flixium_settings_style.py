"""Choose the main settings layout without reloading the skin."""

from flixium_localization import localize as L
import xbmc
import xbmcgui


def main():
    dual_v2 = xbmc.getCondVisibility("Skin.HasSetting(Flixium.SettingsDualListV2)")
    grid = xbmc.getCondVisibility("Skin.HasSetting(Flixium.SettingsGrid)")
    single = xbmc.getCondVisibility("Skin.HasSetting(Flixium.SettingsSingleList)")
    selected = 0 if dual_v2 else (2 if grid else (1 if single else 0))
    choice = xbmcgui.Dialog().select(
        L(31261), [L(31323), L(31325), L(31324)], preselect=selected
    )
    if choice < 0:
        return
    for setting, enabled in (
        ("Flixium.SettingsSingleList", choice == 1),
        ("Flixium.SettingsGrid", choice == 2),
        ("Flixium.SettingsDualListV2", choice == 0),
    ):
        xbmc.executebuiltin("Skin.{}({})".format("SetBool" if enabled else "Reset", setting))


if __name__ == "__main__":
    main()
