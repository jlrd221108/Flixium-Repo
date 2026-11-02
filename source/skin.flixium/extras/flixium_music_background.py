"""Choose cached cover-background motion without changing the lyric effects."""

from flixium_localization import localize as L
import xbmc
import xbmcgui


def main():
    value = xbmc.getInfoLabel("Skin.String(Flixium.MusicBackgroundMotion)")
    choices = ("Preset", "Static", "Gentle", "Full")
    selected = xbmcgui.Dialog().select(L(31495), [
        L(31496), L(31497),
        L(31498), L(31499)],
        preselect=choices.index(value) if value in choices else 0)
    if selected >= 0:
        xbmc.executebuiltin("Skin.SetString(Flixium.MusicBackgroundMotion,{})".format(choices[selected]))


if __name__ == "__main__":
    main()
