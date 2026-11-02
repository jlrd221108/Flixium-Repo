"""Populate album rails from library metadata without native directory enrichment."""
import xbmc
import xbmcgui

from home_widgets import CATALOGUE, DEFAULT_IDS
from my_list_runtime import rpc

ALBUM_IDS = ('played', 'recent', 'most', 'random', 'unplayed', 'rated')


def directory(handle, slot):
    import xbmcplugin
    try:
        slot = int(slot)
        if not 1 <= slot <= 6:
            raise ValueError('Invalid music widget slot')
        key = xbmc.getInfoLabel('Skin.String(Flixium.Widgets.music.{}.Id)'.format(slot))
        if not xbmc.getCondVisibility('Skin.HasSetting(Flixium.Widgets.Configured)'):
            key = DEFAULT_IDS['music'][slot - 1] if slot <= 3 else ''
        if key not in ALBUM_IDS:
            raise ValueError('Not an album widget')
        source = next(row['path'] for row in CATALOGUE['music'] if row['id'] == key)
        rows = rpc('Files.GetDirectory', {
            'directory': source, 'media': 'music',
            'properties': ['title', 'artist', 'album', 'year', 'genre', 'art'],
            'limits': {'end': 30}}).get('files', [])
        xbmcplugin.setContent(handle, 'albums')
        entries = []
        for row in rows:
            url = 'musicdb://albums/{}/'.format(row['id'])
            title = row.get('title') or row['label']
            item = xbmcgui.ListItem(title, path=url, offscreen=True)
            tag = item.getMusicInfoTag()
            tag.setDbId(row['id'], 'album')
            tag.setTitle(title)
            tag.setAlbum(row.get('album') or title)
            tag.setArtist(' / '.join(row.get('artist', [])))
            tag.setYear(row.get('year', 0))
            tag.setGenres(row.get('genre', []))
            item.setArt(row.get('art', {}))
            entries.append((url, item, True))
        xbmcplugin.addDirectoryItems(handle, entries, len(entries))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        xbmc.log('Flixium music widgets: {}'.format(error), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
