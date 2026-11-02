"""Theme-aware RGB picker. Changes are returned only when Apply is selected."""

from flixium_localization import localize as L
import re
import xbmcgui
import xbmcvfs


def parse_hex(value):
    value = value.strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', value):
        raise ValueError(L(31728))
    return value.upper()


class ColourPicker(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.title = kwargs.pop('title')
        self.value = parse_hex(kwargs.pop('value')[-6:])
        self.result = None
        self.ready = False
        super().__init__(*args, **kwargs)
        # Seed the tint before doModal can render the white preview texture.
        self.setProperty('title', self.title)
        self.preview()

    def onInit(self):
        self.setProperty('title', self.title)
        self.load_sliders()
        self.ready = True

    def load_sliders(self):
        for index in range(3):
            self.getControl(201 + index).setPercent(int(self.value[index * 2:index * 2 + 2], 16) * 100 / 255)
        self.preview()

    def preview(self):
        self.setProperty('colour', 'FF' + self.value)
        self.setProperty('hex', '#' + self.value)
        for index, name in enumerate(('red', 'green', 'blue')):
            self.setProperty(name, str(int(self.value[index * 2:index * 2 + 2], 16)))

    def set_channel(self, index, value):
        channels = [int(self.value[i:i + 2], 16) for i in (0, 2, 4)]
        channels[index] = max(0, min(255, int(value)))
        self.value = ''.join('{:02X}'.format(v) for v in channels)
        self.load_sliders()

    def onAction(self, action):
        if action.getId() in (9, 10, 92, 216):
            self.close()
        elif self.ready and action.getId() in (1, 2) and self.getFocusId() in (101, 102, 103):
            index = self.getFocusId() - 101
            value = int(self.value[index * 2:index * 2 + 2], 16)
            self.set_channel(index, value + (1 if action.getId() == 2 else -1))

    def onClick(self, control):
        if control in (101, 102, 103):
            index = control - 101
            value = xbmcgui.Dialog().input((L(31388), L(31389), L(31390))[index] + ' (0–255)', defaultt=str(int(self.value[index * 2:index * 2 + 2], 16)), type=xbmcgui.INPUT_NUMERIC)
            if value.isdigit() and 0 <= int(value) <= 255:
                self.set_channel(index, int(value))
        elif control == 110:
            value = xbmcgui.Dialog().input(L(31456), defaultt=self.value)
            if not value:
                return
            try:
                self.value = parse_hex(value)
            except ValueError:
                xbmcgui.Dialog().ok(L(31391), L(31457))
                return
            self.load_sliders()
        elif control == 113:
            from flixium_theme import COLOURS
            index = xbmcgui.Dialog().select(L(31392), [name for name, _ in COLOURS])
            if index >= 0:
                self.value = COLOURS[index][1]
                self.load_sliders()
        elif control == 111:
            self.result = self.value
            self.close()
        elif control == 112:
            self.close()


def choose(title, value):
    picker = ColourPicker('script-FlixiumColourPicker.xml', xbmcvfs.translatePath('special://skin/'), 'Default', '1080i', title=title, value=value)
    picker.doModal()
    result = picker.result
    del picker
    return result
