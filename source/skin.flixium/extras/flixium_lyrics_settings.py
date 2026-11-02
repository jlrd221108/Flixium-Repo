"""Edit lyric effects as individual checkboxes, without animation presets."""

from flixium_localization import localize as L
import os
import sys

import xbmc
import xbmcgui

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "resources", "lib"))
from lyrics_options import read_options


EFFECTS = (("Simple", L(31081), "simple"),
           ("WordHighlight", L(31085), "words"),
           ("Glow", L(31086), "glow"),
           ("WordMotion", L(31087), "motion"),
           ("SmoothScroll", L(31088), "smooth"),
           ("LetterEmphasis", L(31090), "letters"),
           ("InterludeDots", L(31091), "interludes"),
           ("LineRipple", L(31094), "ripple"),
           ("SmoothFrames", L(31108), "fps"))


def main(toggle=None):
    options = read_options(xbmc.getInfoLabel)
    keys = {key for key, _, _ in EFFECTS}
    if toggle is not None:
        if toggle not in keys:
            return
        current = xbmc.getInfoLabel("Skin.String(Flixium.Lyrics{})".format(toggle))
        xbmc.executebuiltin("Skin.SetString(Flixium.Lyrics{},{})".format(toggle, "Off" if current == "On" else "On"))
        return
    for key, _, field in EFFECTS:
        if xbmc.getInfoLabel("Skin.String(Flixium.Lyrics{})".format(key)) not in ("On", "Off"):
            enabled = options.fps == 60 if field == "fps" else getattr(options, field)
            xbmc.executebuiltin("Skin.SetString(Flixium.Lyrics{},{})".format(key, "On" if enabled else "Off"))
    xbmc.executebuiltin("ActivateWindow(1106)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
