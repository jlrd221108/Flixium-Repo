"""The first-use preset; never reapply it to an existing or resumed setup."""
import json

import xbmc

MARKER = 'Flixium.FirstInstallPresetApplied'
COMMANDS = (
    'Skin.SetBool(Flixium.Glass.Enabled)',
    'Skin.Reset(Flixium.Unrounded)',
    'Skin.Reset(Flixium.ExtraRounded)',
    'Skin.SetString(Flixium.Glass.BackgroundResolution,1080)',
    'Skin.SetString(Flixium.Glass.PanelResolution,1080)',
    'Skin.Reset(Flixium.Glass.BackgroundPreset)',
    'Skin.Reset(Flixium.Glass.BackgroundPresetName)',
    'Skin.Reset(FlixiumRatingsEnabled)',
    'Skin.Reset(HomeMenuNoMovieButton)',
    'Skin.Reset(HomeMenuNoTVShowButton)',
    'Skin.Reset(HomeMenuNoMusicButton)',
) + tuple('Skin.SetBool({})'.format(key) for key in (
    'HomeMenuNoMusicVideoButton', 'HomeMenuNoTVButton', 'HomeMenuNoRadioButton',
    'HomeMenuNoProgramsButton', 'HomeMenuNoPicturesButton', 'HomeMenuNoVideosButton',
    'HomeMenuNoGamesButton', 'HomeMenuNoFavButton', 'HomeMenuNoWeatherButton',
)) + tuple('Skin.Reset(Flixium.Theme.{})'.format(key) for key in (
    'Window', 'Panel', 'Card', 'Focus', 'Highlight', 'Dialog', 'DialogHeader', 'Scheme', 'Name',
))


def apply():
    has = lambda key: xbmc.getCondVisibility('Skin.HasSetting({})'.format(key))
    if has(MARKER) or any(has('Flixium.Setup.' + k) for k in ('Started', 'Seen', 'Completed')):
        return False
    if xbmc.getInfoLabel('Skin.String(Flixium.DefaultsVersion)') and not has('Flixium.Setup.Pending'):
        return False
    for command in COMMANDS:
        xbmc.executebuiltin(command, True)
    # Kodi defines 0 as AE_SOUND_OFF. Keep the selected sound pack available.
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'Settings.SetSettingValue',
            'params': {'setting': 'audiooutput.guisoundmode', 'value': 0},
        })))
        if response.get('result') is not True:
            xbmc.log('Flixium first-use defaults: UI sounds could not be disabled', xbmc.LOGWARNING)
    except (ValueError, RuntimeError):
        xbmc.log('Flixium first-use defaults: UI sounds could not be disabled', xbmc.LOGWARNING)
    xbmc.executebuiltin('Skin.SetBool({})'.format(MARKER), True)
    return True
