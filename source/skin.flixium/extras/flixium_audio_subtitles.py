"""Remote-friendly track selection for the video currently playing."""

from flixium_localization import localize as L
import json
import xbmc
import xbmcgui
import xbmcvfs


def rpc(method, **params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})))
    if 'error' in response:
        raise RuntimeError(method + ' failed')
    return response.get('result')


def track_label(track, kind):
    language = track.get('language', '')
    if language and language != 'und':
        language = xbmc.convertLanguage(language, xbmc.ENGLISH_NAME) or language
    else:
        language = L(31423)
    name = (track.get('name') or '').strip()
    title = language + (' · ' + name if name and name.casefold() != language.casefold() else '')
    details = []
    if kind == 'audio':
        if track.get('codec'):
            details.append(track['codec'].upper())
        channels = track.get('channels', 0)
        if channels:
            details.append({1: L(31432), 2: L(31433), 6: '5.1', 8: '7.1'}.get(channels, L(31784).format(channels)))
    for key, label in (('isforced', L(31424)), ('isimpaired', L(31426) if kind == 'audio' else L(31427))):
        if track.get(key):
            details.append(label)
    return title, ' · '.join(details) or (L(31785).format(track['index'] + 1))


def selection_command(playerid, kind, index):
    if kind == 'audio':
        return 'Player.SetAudioStream', {'playerid': playerid, 'stream': index}
    return 'Player.SetSubtitle', {'playerid': playerid, 'subtitle': index, 'enable': index != 'off'}


class PlaybackGuard(xbmc.Player):
    def dismiss(self):
        panel = getattr(self, 'panel', None)
        if panel is not None:
            panel.close()

    def onPlayBackStopped(self): self.dismiss()
    def onPlayBackEnded(self): self.dismiss()
    def onPlayBackStarted(self): self.dismiss()


class TrackPanel(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.playerid = kwargs.pop('playerid')
        self.file = kwargs.pop('file')
        self.advanced = None
        self.rows = {}
        self.guard = PlaybackGuard()
        self.guard.panel = self
        super().__init__(*args, **kwargs)

    def same_video(self):
        players = rpc('Player.GetActivePlayers')
        if not any(p['playerid'] == self.playerid and p['type'] == 'video' for p in players):
            return False
        item = rpc('Player.GetItem', playerid=self.playerid, properties=['file'])['item']
        return item.get('file', '') == self.file

    def onInit(self):
        try:
            if not self.same_video():
                self.close()
                return
            self.refresh(initial=True)
        except Exception:
            self.failed()

    def refresh(self, initial=False):
        props = rpc('Player.GetProperties', playerid=self.playerid, properties=['audiostreams', 'currentaudiostream', 'subtitles', 'currentsubtitle', 'subtitleenabled'])
        for cid, kind, streams, selected in (
            (100, 'audio', props.get('audiostreams', []), (props.get('currentaudiostream') or {}).get('index')),
            (200, 'subtitle', props.get('subtitles', []), (props.get('currentsubtitle') or {}).get('index') if props.get('subtitleenabled') else 'off')):
            listing = self.getControl(cid)
            position = listing.getSelectedPosition() if not initial else 0
            rows = []
            items = []
            if kind == 'subtitle':
                rows.append('off')
                item = xbmcgui.ListItem(label=L(31429), label2=L(31430))
                item.setProperty('active', L(31431) if selected == 'off' else '')
                items.append(item)
            for track in streams:
                title, details = track_label(track, kind)
                item = xbmcgui.ListItem(label=title, label2=details)
                item.setProperty('active', L(31431) if track['index'] == selected else '')
                rows.append(track['index'])
                items.append(item)
            if not items:
                items.append(xbmcgui.ListItem(label=L(31434)))
                rows.append(None)
            self.rows[cid] = rows
            listing.reset()
            listing.addItems(items)
            if initial and selected in rows:
                position = rows.index(selected)
            listing.selectItem(max(0, min(position, len(rows) - 1)))
        if initial:
            self.setFocusId(100 if any(r is not None for r in self.rows[100]) else 200)

    def failed(self):
        xbmcgui.Dialog().notification(L(31337), L(31425))
        self.close()

    def onAction(self, action):
        if action.getId() in (9, 10, 92, 216):
            self.close()

    def onClick(self, control):
        if control == 300:
            self.close()
        elif control in (301, 302):
            self.advanced = 'osdaudiosettings' if control == 301 else 'osdsubtitlesettings'
            self.close()
        elif control in (100, 200):
            try:
                if not self.same_video():
                    self.close()
                    return
                index = self.rows[control][self.getControl(control).getSelectedPosition()]
                if index is None:
                    return
                kind = 'audio' if control == 100 else 'subtitle'
                # Recheck the available indices in case the player changed its tracks.
                props = rpc('Player.GetProperties', playerid=self.playerid, properties=['audiostreams' if kind == 'audio' else 'subtitles'])
                streams = props.get('audiostreams' if kind == 'audio' else 'subtitles', [])
                if index != 'off' and index not in [s['index'] for s in streams]:
                    self.refresh()
                    return
                method, params = selection_command(self.playerid, kind, index)
                rpc(method, **params)
                self.refresh()
            except Exception:
                self.failed()


def main():
    home = xbmcgui.Window(10000)
    if home.getProperty('flixium.tracks.open') == 'true':
        return
    panel = None
    home.setProperty('flixium.tracks.open', 'true')
    try:
        players = rpc('Player.GetActivePlayers')
        playerid = next((p['playerid'] for p in players if p['type'] == 'video'), None)
        if playerid is None:
            return
        file = rpc('Player.GetItem', playerid=playerid, properties=['file'])['item'].get('file', '')
        xbmc.executebuiltin('Dialog.Close(VideoOSD)', True)
        panel = TrackPanel('script-FlixiumAudioSubtitles.xml', xbmcvfs.translatePath('special://skin/'), 'Default', '1080i', playerid=playerid, file=file)
        panel.doModal()
        advanced = panel.advanced
        panel.guard.panel = None
        del panel
        panel = None
        if advanced:
            xbmc.executebuiltin('ActivateWindow(' + advanced + ')')
    except Exception:
        xbmcgui.Dialog().notification(L(31337), L(31425))
    finally:
        if panel is not None:
            panel.guard.panel = None
        home.clearProperty('flixium.tracks.open')


if __name__ == '__main__':
    main()
