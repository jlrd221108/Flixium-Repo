
from flixium_localization import localize as L
import sys

import xbmc
import xbmcgui


DEFAULT_RADIUS = "30"
DEFAULT_SATURATION = "1.5"


def skin_value(name, default):
    return xbmc.getInfoLabel("Skin.String({})".format(name)) or default


def set_skin_value(name, value):
    xbmc.executebuiltin("Skin.SetString({},{})".format(name, value))


def set_radius():
    current = skin_value("Flixium.BlurRadius", DEFAULT_RADIUS)
    value = xbmcgui.Dialog().numeric(0, L(31452), current)
    if value == "":
        value = DEFAULT_RADIUS
    set_skin_value("Flixium.BlurRadius", value)


def set_saturation():
    current = skin_value("Flixium.BlurSaturation", DEFAULT_SATURATION)
    keyboard = xbmc.Keyboard(current, L(31453))
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return

    value = keyboard.getText().strip() or DEFAULT_SATURATION
    try:
        if float(value) < 0:
            raise ValueError
    except ValueError:
        xbmcgui.Dialog().notification(
            L(31454),
            L(31455),
            xbmcgui.NOTIFICATION_ERROR,
        )
        return

    set_skin_value("Flixium.BlurSaturation", value)


if __name__ == "__main__" and len(sys.argv) > 1:
    if sys.argv[1] == "radius":
        set_radius()
    elif sys.argv[1] == "saturation":
        set_saturation()
