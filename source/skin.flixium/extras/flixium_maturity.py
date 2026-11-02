"""Publish a brief opening maturity bumper; no network requests or metadata guesses."""

from flixium_localization import localize as L
import re
import time
import xbmc
import xbmcgui
HOME = xbmcgui.Window(10000)
PREFIX = 'flixium.maturity.'

def parse_rating(raw):
    raw = re.sub('\\s+', ' ', raw or '').strip()
    if not raw or raw.casefold() in ('n/a', 'not available', 'unknown'):
        return ('', '')
    parts = re.split('\\s+for\\s+', raw, maxsplit=1, flags=re.I)
    certificate = parts[0]
    advisory = parts[1].rstrip('.') if len(parts) > 1 else ''
    certificate = re.sub('^(?:rated\\s+|rating\\s*:\\s*|(?:UK|GB|US|USA|BBFC|MPAA|Australia|Canada)\\s*:\\s*)', '', certificate, flags=re.I)
    certificate = re.sub('^(?:rated\\s+|rating\\s*:\\s*)', '', certificate, flags=re.I).strip()
    return (certificate, advisory)

def rating_icon(rating, raw):
    certificate = rating.upper().strip()
    uk = {'U': 'u', 'PG': 'pg', '12': '12', '12A': '12a', '15': '15', '18': '18'}
    us = {'G', 'PG', 'PG-13', 'R', 'NC-17', 'NR'}
    american = bool(re.search('(?:^|[^A-Z])(?:US|USA|MPAA)(?:[^A-Z]|$)', raw.upper()))
    if certificate in uk and (not american):
        return 'special://skin/extras/AgeRatingIcons/bbfc_{}_certificate_uk.png'.format(uk[certificate])
    if certificate in us:
        return 'special://skin/extras/certificates/MPAA_{}_Certificate_US.png'.format(certificate)
    if certificate in ('TV-G', 'TV-PG', 'TV-14', 'TV-MA'):
        return 'special://skin/extras/certificates/{}_Certificate_US.png'.format(certificate)
    return ''

def main():
    if xbmc.getSkinDir() != 'skin.flixium' or not xbmc.getCondVisibility('Player.HasVideo + !VideoPlayer.Content(livetv) + !VideoPlayer.Content(musicvideos) + !Player.HasGame'):
        return
    player = xbmc.Player()
    source = player.getPlayingFile()
    if HOME.getProperty(PREFIX + 'source') == source:
        return
    token = str(time.monotonic())
    HOME.setProperty(PREFIX + 'token', token)
    monitor = xbmc.Monitor()
    raw = ''
    for attempt in range(15):
        if not player.isPlayingVideo() or player.getPlayingFile() != source:
            return
        raw = xbmc.getInfoLabel('VideoPlayer.MPAA')
        if raw:
            break
        if monitor.waitForAbort(0.1):
            return
    rating, advisory = parse_rating(raw)
    if not rating:
        return
    HOME.setProperty(PREFIX + 'source', source)
    HOME.setProperty(PREFIX + 'rating', L(31489) + rating)
    HOME.setProperty(PREFIX + 'certificate', rating)
    HOME.setProperty(PREFIX + 'icon', rating_icon(rating, raw))
    HOME.setProperty(PREFIX + 'advisory', advisory)
    HOME.clearProperty(PREFIX + 'bar')
    HOME.clearProperty(PREFIX + 'content')
    HOME.setProperty(PREFIX + 'visible', 'true')
    if monitor.waitForAbort(0.15):
        HOME.clearProperty(PREFIX + 'visible')
        return
    HOME.setProperty(PREFIX + 'bar', 'true')
    if monitor.waitForAbort(0.45):
        HOME.clearProperty(PREFIX + 'visible')
        return
    HOME.setProperty(PREFIX + 'content', 'true')
    deadline = time.monotonic() + 6.5
    try:
        while time.monotonic() < deadline and (not monitor.abortRequested()):
            if HOME.getProperty(PREFIX + 'token') != token or not player.isPlayingVideo() or player.getPlayingFile() != source:
                break
            monitor.waitForAbort(0.1)
    finally:
        if HOME.getProperty(PREFIX + 'token') == token:
            HOME.clearProperty(PREFIX + 'visible')
if __name__ == '__main__':
    main()
