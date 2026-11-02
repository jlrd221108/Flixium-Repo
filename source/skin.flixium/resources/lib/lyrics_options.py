"""Individual lyric effect toggles; preserve old preset values as migration defaults."""
from collections import namedtuple


LyricOptions = namedtuple("LyricOptions", "quality fps words glow motion smooth letters interludes ripple simple", defaults=(False,))
PRESETS = {
    "Low": LyricOptions("Low", 15, False, False, False, False, False, False, False),
    "Balanced": LyricOptions("Balanced", 30, True, False, False, True, False, True, False),
    "High": LyricOptions("High", 60, True, True, True, True, True, True, False),
}
OVERRIDES = (("WordHighlight", "words"), ("Glow", "glow"),
             ("WordMotion", "motion"), ("SmoothScroll", "smooth"),
             ("LetterEmphasis", "letters"), ("InterludeDots", "interludes"), ("LineRipple", "ripple"))


def read_options(get_label):
    def setting(key):
        return get_label("Skin.String(Flixium.Lyrics{})".format(key))
    # Historical quality values only seed unset toggles for existing users.
    # The settings UI no longer exposes or writes presets.
    options = PRESETS.get(setting("Quality"), PRESETS["Balanced"])
    changes = {}
    for key, field in OVERRIDES:
        value = setting(key)
        if value in ("On", "Off"):
            changes[field] = value == "On"
    changes["simple"] = setting("Simple") == "On"
    frames = setting("SmoothFrames")
    if frames in ("On", "Off"):
        changes["fps"] = 60 if frames == "On" else 30
    return options._replace(**changes)
