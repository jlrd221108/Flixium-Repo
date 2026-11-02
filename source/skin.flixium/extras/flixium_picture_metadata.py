"""Debounced, window-scoped metadata enrichment for selected photos/videos."""
from collections import OrderedDict
import os
import sys
import time
import uuid

import xbmc
import xbmcgui
import xbmcvfs

sys.path.insert(0, os.path.join(xbmcvfs.translatePath('special://skin/'), 'resources', 'lib'))
from picture_metadata import VIDEO_EXTENSIONS, format_rows, location_details, read_mp4, video_details

PREFIX = 'flixium.pictures.media.'
FIELDS = ('path', 'location', 'video_details')
RUNNING = PREFIX + 'running'


class VFSReader:
    def __init__(self, handle):
        self.handle = handle

    def read(self, length):
        return bytes(self.handle.readBytes(length))

    def seek(self, position):
        return self.handle.seek(position)


def enrich(path, video, native, cancelled):
    metadata = {}
    # QuickTime location metadata covers typical phone/camera MOV/MP4 recordings.
    extension = path.rsplit('.', 1)[-1].lower()
    if video and extension in ('mp4', 'mov', 'm4v', '3gp', '3g2'):
        handle = xbmcvfs.File(path)
        try:
            metadata = read_mp4(VFSReader(handle), handle.size(), cancelled)
        finally:
            handle.close()
    if cancelled():
        return None
    # Picture labels can retain unrelated/default EXIF values for video entries.
    location = location_details(metadata, {} if video else native)
    return {'location': format_rows(location), 'video_details': format_rows(video_details(metadata)) if video else ''}


def run():
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    token = uuid.uuid4().hex
    home.setProperty(RUNNING, token)
    cache = OrderedDict()
    current, updated, signature = None, 0, None

    def clear():
        for field in FIELDS:
            home.clearProperty(PREFIX + field)

    def active():
        return (not monitor.abortRequested() and home.getProperty(RUNNING) == token
                and xbmc.getSkinDir() == 'skin.flixium'
                and xbmc.getCondVisibility('Window.IsActive(pictures)'))

    try:
        clear()
        if monitor.waitForAbort(.4):
            return
        while active():
            visible = xbmc.getCondVisibility('Control.IsVisible(61)')
            folder = xbmc.getCondVisibility('ListItem.IsFolder')
            path = xbmc.getInfoLabel('ListItem.FileNameAndPath') if visible and not folder else ''
            native = {name: xbmc.getInfoLabel(label) for name, label in (
                ('lat', 'ListItem.PictureGPSLat'), ('lon', 'ListItem.PictureGPSLon'),
                ('altitude', 'ListItem.PictureGPSAlt'), ('city', 'ListItem.PictureCity'),
                ('country', 'ListItem.PictureCountry'))} if path else {}
            video = path.rsplit('.', 1)[-1].lower() in VIDEO_EXTENSIONS or xbmc.getCondVisibility('ListItem.IsVideo')
            selected = (path, video, tuple(sorted(native.items())) if not video else ())
            if selected != current:
                current, updated, signature = selected, time.monotonic(), None
                clear()
            elif path and signature != selected and time.monotonic() - updated >= .25:
                def cancelled():
                    return (not active() or not xbmc.getCondVisibility('Control.IsVisible(61)')
                            or xbmc.getInfoLabel('ListItem.FileNameAndPath') != path)
                try:
                    values = cache.get(selected)
                    if values is None:
                        values = enrich(path, video, native, cancelled)
                    if values is not None and not cancelled():
                        cache[selected] = values
                        cache.move_to_end(selected)
                        while len(cache) > 128:
                            cache.popitem(last=False)
                        for field, value in values.items():
                            home.setProperty(PREFIX + field, value)
                        # Publish identity last; XML guards against stale selection data.
                        home.setProperty(PREFIX + 'path', path)
                        signature = selected
                except Exception as error:
                    xbmc.log('Flixium selected-media metadata failed ({})'.format(type(error).__name__), xbmc.LOGWARNING)
                    signature = selected
            if monitor.waitForAbort(.15):
                break
    finally:
        if home.getProperty(RUNNING) == token:
            clear()
            home.clearProperty(RUNNING)


if __name__ == '__main__':
    run()
