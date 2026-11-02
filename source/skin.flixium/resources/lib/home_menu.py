"""One portable main-menu configuration for both Home renderers. No Kodi imports."""

from localization import localize as L
from copy import deepcopy
import json
import re
from urllib.parse import quote, unquote
PREFIX = 'Flixium.HomeMenu'
MAX_ITEMS = 20
TARGETS = (('movies', L(31233), 'ActivateWindow(Videos,videodb://movies/titles/,return)', '5000'), ('tvshows', L(31234), 'ActivateWindow(Videos,videodb://tvshows/titles/,return)', '6000'), ('music', L(31414), 'ActivateWindow(Music,root,return)', '7000'), ('musicvideos', L(31702), 'ActivateWindow(Videos,musicvideos,return)', '16000'), ('livetv', L(31703), 'ActivateWindow(TVChannels)', '12000'), ('radio', L(31704), 'ActivateWindow(RadioChannels)', '13000'), ('addons', L(31705), 'ActivateWindow(1100)', '8000'), ('pictures', L(31706), 'ActivateWindow(Pictures)', '4000'), ('video', L(31416), 'ActivateWindow(Videos,root,return)', '11000'), ('games', L(31707), 'ActivateWindow(Games)', '17000'), ('favorites', L(31708), 'ActivateWindow(favouritesbrowser)', '14000'), ('weather', L(31709), 'ActivateWindow(Weather)', '15000'), ('settings', L(31710), 'ActivateWindow(Settings)', '0'))
MY_LIST_TARGETS = tuple((key, label, 'RunScript(special://skin/extras/flixium_my_list.py,open,{})'.format(media_filter), '18000')
                       for key, label, media_filter in (('mylist', L(31241), 'default'),
                           ('mylist_movies', L(31711), 'movies'), ('mylist_tvshows', L(31712), 'tvshows')))
TARGETS = TARGETS[:2] + MY_LIST_TARGETS + TARGETS[2:]
TARGET_MAP = {row[0]: row for row in TARGETS}

def valid_action(value):
    return isinstance(value, str) and 0 < len(value) <= 2048 and (not any((char in value for char in '\x00\r\n'))) and (re.match('^[A-Za-z][A-Za-z0-9_.]*(?:\\(|$)', value) is not None)

def normalise(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ITEMS:
        raise ValueError(L(31741))
    result, seen = ([], set())
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(L(31744))
        uid, label = (row.get('uid'), row.get('label'))
        if not isinstance(uid, str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', uid) or uid in seen:
            raise ValueError(L(31745))
        if not isinstance(label, str) or not label.strip() or len(label) > 160 or ('\x00' in label):
            raise ValueError(L(31746))
        seen.add(uid)
        actions = row.get('actions', [])
        if not isinstance(actions, list) or not 1 <= len(actions) <= 12:
            raise ValueError(L(31747))
        clean_actions = []
        for action in actions:
            if not isinstance(action, dict) or not valid_action(action.get('command')):
                raise ValueError(L(31749))
            condition = action.get('condition', '')
            if not isinstance(condition, str) or len(condition) > 2048 or '\x00' in condition:
                raise ValueError(L(31750))
            clean_actions.append({'command': action['command'], 'condition': condition})
        section = row.get('section', 'custom')
        if not isinstance(section, str) or not re.fullmatch('[a-z0-9_]{1,64}', section):
            raise ValueError(L(31748))
        item = {'uid': uid, 'label': label.strip(), 'section': section, 'enabled': row.get('enabled', True) is True, 'actions': clean_actions}
        for key in ('background',):
            value = row.get(key, '')
            if not isinstance(value, str) or len(value) > 4096 or '\x00' in value:
                raise ValueError(L(31751))
            item[key] = value
        item['menu_id'] = '21000' if section == 'disc' else TARGET_MAP.get(section, (None, None, None, '0'))[3]
        if section == 'settings':
            item.update(enabled=True, actions=[{'command': 'ActivateWindow(Settings)', 'condition': ''}])
        result.append(item)
    if not any((row['enabled'] for row in result)):
        raise ValueError(L(31742))
    return result

def encode(rows):
    return quote(json.dumps(normalise(rows), ensure_ascii=False, separators=(',', ':')), safe='')

def decode(value):
    if not isinstance(value, str) or len(value) > 512000:
        raise ValueError(L(31743))
    return normalise(json.loads(unquote(value)))

def new_item(uid, label, target='movies'):
    section, _, action, menu_id = TARGET_MAP[target]
    return {'uid': uid, 'label': label, 'section': section, 'menu_id': menu_id, 'enabled': True, 'actions': [{'command': action, 'condition': ''}], 'background': ''}

def settings(rows):
    rows = normalise(rows)
    output = [{'id': PREFIX + '.Config', 'type': 'string', 'value': encode(rows)}]
    for index in range(MAX_ITEMS):
        row = rows[index] if index < len(rows) else None
        base = '{}.Item{}.'.format(PREFIX, index + 1)
        values = {'Label': row['label'] if row else '', 'Id': row['section'] if row else '', 'Uid': row['uid'] if row else '', 'MenuId': row['menu_id'] if row else '0', 'Background': row['background'] if row else ''}
        if row:
            values['Action'] = row['actions'][0]['command'] if len(row['actions']) == 1 and (not row['actions'][0]['condition']) else 'RunScript(special://skin/extras/flixium_home_menu.py,activate,{})'.format(row['uid'])
        else:
            values['Action'] = ''
        output.extend(({'id': base + key, 'type': 'string', 'value': value} for key, value in values.items()))
        output.append({'id': base + 'Enabled', 'type': 'bool', 'value': bool(row and row['enabled'])})
    output.append({'id': PREFIX + '.Configured', 'type': 'bool', 'value': True})
    return output

def changed(rows, index, **values):
    result = deepcopy(rows)
    result[index].update(values)
    return normalise(result)

def setting_changes(previous, current):
    """Keep publication order, without retriggering Kodi for unchanged values."""
    before = {row['id']: (row['type'], row['value']) for row in previous}
    return [row for row in current if before.get(row['id']) != (row['type'], row['value'])]
