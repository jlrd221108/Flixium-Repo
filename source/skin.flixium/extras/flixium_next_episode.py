"""A cancellable Netflix-style next-episode prompt for Kodi's local TV library."""

from flixium_localization import localize as L
import json
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

SKIN = xbmcvfs.translatePath('special://home/addons/skin.flixium/')
sys.path.insert(0, os.path.join(SKIN, 'resources', 'lib'))
from next_episode import Countdown, credits_start, next_episode, prompt_due

HOME = xbmcgui.Window(10000)
RUNNING = 'flixium.next_episode.running'
LEASE = 'Flixium.NextEpisode.UpNextLease'


def rpc(method, **params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0', 'id':1, 'method':method, 'params':params})))
    if 'error' in response:
        raise RuntimeError(L(31734) + method)
    return response.get('result', {})


def enabled():
    return xbmc.getSkinDir() == 'skin.flixium' and not xbmc.getCondVisibility('Skin.HasSetting(Flixium.NextEpisode.Disabled)')


def fallback_time():
    value = xbmc.getInfoLabel('Skin.String(Flixium.NextEpisode.Fallback)')
    return int(value) if value in ('0', '15', '30', '60', '90', '120') else 60


def recover_upnext(force=False):
    if not force and HOME.getProperty(RUNNING) == 'true':
        return
    if xbmc.getInfoLabel('Skin.String({})'.format(LEASE)) != 'restore':
        return
    try:
        addon = xbmcaddon.Addon('service.upnext')
        if addon.getSettingBool('disableNextUp'):
            addon.setSettingBool('disableNextUp', False)
    except RuntimeError:
        pass
    xbmc.executebuiltin('Skin.Reset({})'.format(LEASE), True)


def own_local_prompt():
    """Temporarily suppress Up Next; journal it so a Kodi restart recovers it."""
    try:
        addon = xbmcaddon.Addon('service.upnext')
        if not addon.getSettingBool('disableNextUp'):
            xbmc.executebuiltin('Skin.SetString({},restore)'.format(LEASE), True)
            addon.setSettingBool('disableNextUp', True)
    except RuntimeError:
        pass


def playing_item():
    players = rpc('Player.GetActivePlayers')
    video = next((p['playerid'] for p in players if p['type'] == 'video'), None)
    if video is None:
        return None
    item = rpc('Player.GetItem', playerid=video, properties=['file','season','episode','tvshowid','title','showtitle']).get('item', {})
    if (item.get('type') != 'episode' or not item.get('id') or not item.get('tvshowid')
            or item.get('file', '').lower().startswith(('plugin://', 'http://', 'https://'))):
        return None
    return item


def marker_for(path, total):
    # An optional sidecar uses seconds from the start of this exact video file.
    sidecar = os.path.splitext(path)[0] + '.flixium.json'
    if not xbmcvfs.exists(sidecar):
        return None
    try:
        with xbmcvfs.File(sidecar) as stream:
            if stream.size() > 65536:
                return None
            return credits_start(json.loads(stream.read()), total)
    except (ValueError, RuntimeError, OSError):
        return None


class NextEpisodePrompt(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, current=None, following=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current, self.following = current, following
        self.dismissed = False
        self.countdown = None

    def onInit(self):
        e = self.following
        self.setProperty('episode', L(31526).format(e['season'], e['episode'], e.get('title') or e.get('label', '')))
        self.setProperty('show', self.current.get('showtitle', ''))
        self.setProperty('thumb', e.get('art', {}).get('thumb', ''))
        self.setFocusId(10)
        self.countdown = Countdown(time.monotonic(), xbmc.Player().getTime())
        self.getControl(30).setPercent(0)

    def tick(self, position, paused=False):
        if self.dismissed or self.countdown is None:
            return
        progress = self.countdown.update(time.monotonic(), position, paused)
        if self.countdown.cancelled:
            self.dismissed = True
            self.close()
            return
        self.getControl(30).setPercent(progress)
        if self.countdown.complete:
            self.onClick(10)

    def onAction(self, action):
        key = action.getId()
        if key in (9, 10, 92):
            self.dismissed = True
            self.close()
        elif key in (12, 68, 79, 229):
            xbmc.executebuiltin('Action(PlayPause)')
        elif key == 13:
            self.dismissed = True
            self.close()
            xbmc.Player().stop()
        elif key in (20, 21, 22, 23, 16, 17):
            self.dismissed = True
            self.close()
            command = {20:'StepForward', 21:'StepBack', 22:'BigStepForward',
                       23:'BigStepBack', 16:'FastForward', 17:L(31038)}[key]
            xbmc.executebuiltin('Action({})'.format(command))

    def onClick(self, control_id):
        if self.dismissed:
            return
        self.dismissed = True
        self.close()
        if control_id != 10:
            return
        try:
            current = playing_item()
            if not current or current.get('id') != self.current['id'] or current.get('file') != self.current['file']:
                return  # The episode changed while this button was on screen.
            if not xbmcvfs.exists(self.following['file']):
                xbmcgui.Dialog().notification(L(31251), L(31527))
                return
            rpc('Player.Open', item={'episodeid':self.following['episodeid']}, options={'resume':False})
        except RuntimeError as error:
            xbmc.log('Flixium next episode: {}'.format(error), xbmc.LOGWARNING)


def run():
    if HOME.getProperty(RUNNING) == 'true' or not enabled():
        return
    recover_upnext(force=True)
    HOME.setProperty(RUNNING, 'true')
    player, monitor = xbmc.Player(), xbmc.Monitor()
    prompt = None
    identity = None
    shown = False
    following = None
    current = None
    marker = None
    ticks = 0
    try:
        # Fullscreen can load before the player's episode metadata is ready.
        for _ in range(40):
            if not enabled() or monitor.waitForAbort(0.25):
                return
            if player.isPlayingVideo():
                try:
                    if playing_item() and player.getTotalTime() > 0:
                        break
                    if xbmc.getCondVisibility('VideoPlayer.Content(movies) | VideoPlayer.Content(musicvideos) | VideoPlayer.Content(livetv)'):
                        return
                except RuntimeError:
                    pass
        else:
            return
        while not monitor.waitForAbort(0.05) and enabled() and player.isPlayingVideo():
            try:
                # Query metadata once per second; no library queries in the timing loop.
                ticks += 1
                if ticks % 20 == 1 or current is None:
                    item = playing_item()
                    key = (item.get('id'), item.get('file')) if item else None
                    if key != identity:
                        if prompt:
                            prompt.close()
                            prompt = None
                        recover_upnext(force=True)
                        identity, current, following, shown, marker = key, item, None, False, None
                        if item:
                            own_local_prompt()
                            episodes = rpc('VideoLibrary.GetEpisodes', tvshowid=item['tvshowid'], properties=['season','episode','file','title','art']).get('episodes', [])
                            following = next_episode(item, episodes)
                            if following:
                                marker = marker_for(item['file'], player.getTotalTime())
                    elif item:
                        current = item
                if not current or not following:
                    continue
                due = prompt_due(player.getTime(), player.getTotalTime(), marker,
                                 xbmc.getInfoLabel('Player.ChapterName'), fallback_time())
                if prompt and (not due or not xbmc.getCondVisibility('Window.IsVisible(fullscreenvideo)')):
                    prompt.close()
                    prompt = None
                if prompt:
                    prompt.tick(player.getTime(), xbmc.getCondVisibility('Player.Paused | Player.Caching'))
                if due and not shown and xbmc.getCondVisibility('Window.IsActive(fullscreenvideo) + !Player.Paused + !System.HasActiveModalDialog'):
                    prompt = NextEpisodePrompt('script-FlixiumNextEpisode.xml', SKIN, 'Default', '1080i', current=current, following=following)
                    prompt.show()
                    shown = True
            except (RuntimeError, ValueError, TypeError) as error:
                xbmc.log('Flixium next episode: {}'.format(error), xbmc.LOGWARNING)
                # Metadata may still be arriving immediately after playback starts.
                if current is None:
                    continue
    finally:
        if prompt:
            prompt.close()
        recover_upnext(force=True)
        HOME.clearProperty(RUNNING)


def settings():
    choices = (L(31429), L(31521), L(31522), L(31523), L(31524), L(31525))
    values = (0, 15, 30, 60, 90, 120)
    selected = xbmcgui.Dialog().select(L(31280), list(choices), preselect=values.index(fallback_time()))
    if selected >= 0:
        xbmc.executebuiltin('Skin.SetString(Flixium.NextEpisode.Fallback,{})'.format(values[selected]))


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if action == 'settings':
        settings()
    elif action == 'recover':
        recover_upnext()
    else:
        run()
