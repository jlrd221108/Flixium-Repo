"""Shared fullscreen main-menu editor; both Home styles consume its preferences."""

from flixium_localization import localize as L
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
import xbmc
from flixium_reload import request_reload
import xbmcaddon
import xbmcgui
import xbmcvfs
SKIN = xbmcvfs.translatePath('special://skin/')
sys.path.insert(0, os.path.join(SKIN, 'resources', 'lib'))
from home_menu import PREFIX, MAX_ITEMS, TARGETS, decode, settings, setting_changes, new_item, changed, normalise
from skin_backup import commands

def local_label(value):
    return re.sub('\\$LOCALIZE\\[(\\d+)\\]', lambda m: xbmc.getLocalizedString(int(m[1])), value or '')

def initial_items():
    saved = xbmc.getInfoLabel('Skin.String({}.Config)'.format(PREFIX))
    if saved:
        return decode(saved)
    tree = ET.parse(os.path.join(SKIN, 'xml', 'Includes_FlixiumHome.xml'))
    content = tree.find(".//control[@id='9000']/content")
    legacy = content.find('include')
    if legacy is not None:
        tree = ET.parse(os.path.join(SKIN, 'xml', 'Includes_SharedHomeMenu.xml'))
        content = tree.find("include[@name='FlixiumLegacyMenuItems']")
    rows = []
    for index, item in enumerate(content.findall('item')):
        section = item.findtext("property[@name='id']", 'custom')
        actions = [{'command': node.text, 'condition': node.get('condition', '')} for node in item.findall('onclick')]
        if not actions:
            continue
        visible = item.findtext('visible', 'true')
        rows.append({'uid': 'legacy_' + section, 'label': local_label(item.findtext('label')), 'section': section, 'enabled': xbmc.getCondVisibility(visible), 'actions': actions})
    return normalise(rows)

class HomeMenuEditor(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = initial_items()
        self.index = 0
        self.applied = False
        self._published = None

    def onInit(self):
        self.render()
        self.setProperty('ready', 'true')
        self.setFocusId(100 if self.visible_indices else 101)

    def render(self):
        listing = self.getControl(100)
        listing.reset()
        self.visible_indices = [index for index, row in enumerate(self.rows) if row['section'] != 'settings']
        for index in self.visible_indices:
            row = self.rows[index]
            item = xbmcgui.ListItem(row['label'])
            item.setProperty('visibility', '' if row['enabled'] else L(31477))
            listing.addItem(item)
        self.index = min(self.index, len(self.rows) - 1)
        if self.visible_indices:
            if self.index not in self.visible_indices:
                self.index = self.visible_indices[0]
            listing.selectItem(self.visible_indices.index(self.index))
        self.details()

    def details(self):
        self.setProperty('hasitem', 'true' if self.visible_indices else 'false')
        self.setProperty('canmoveup', 'false')
        self.setProperty('canmovedown', 'false')
        if not self.visible_indices:
            self.setProperty('item', L(31475))
            self.setProperty('canadd', 'true' if len(self.rows) < MAX_ITEMS else 'false')
            return
        position = max(0, min(self.getControl(100).getSelectedPosition(), len(self.visible_indices) - 1))
        self.index = self.visible_indices[position]
        self.setProperty('canmoveup', 'true' if position > 0 else 'false')
        self.setProperty('canmovedown', 'true' if position + 1 < len(self.visible_indices) else 'false')
        row = self.rows[self.index]
        self.setProperty('locked', 'true' if row['section'] == 'settings' else 'false')
        self.setProperty('item', row['label'])
        self.setProperty('action', row['actions'][0]['command'])
        action_label = next((target[1] for target in TARGETS if target[2] == row['actions'][0]['command']), '')
        if not action_label and len(row['actions']) > 1:
            # Legacy library entries contain several conditional open actions.
            action_label = next((target[1] for target in TARGETS if target[0] == row['section']), '')
        self.setProperty('actionlabel', action_label or L(31476))
        self.setProperty('enabled', 'true' if row['enabled'] else 'false')
        self.setProperty('background', os.path.basename(row['background'].replace('\\', '/')) or L(31311))
        self.setProperty('canadd', 'true' if len(self.rows) < MAX_ITEMS else 'false')

    def commit(self, rows):
        rows = normalise(rows)
        if rows == self.rows:
            return
        published = settings(rows)
        if self._published is None:
            self._published = [dict(row, value=xbmc.getCondVisibility('Skin.HasSetting({})'.format(row['id'])) if row['type'] == 'bool' else xbmc.getInfoLabel('Skin.String({})'.format(row['id']))) for row in published]
        for command in commands(setting_changes(self._published, published)):
            xbmc.executebuiltin(command, True)
        self._published = published
        same_order = [row['uid'] for row in rows] == [row['uid'] for row in self.rows]
        same_order = same_order and [row['uid'] for row in rows if row['section'] != 'settings'] == [row['uid'] for row in self.rows if row['section'] != 'settings']
        previous = self.rows
        self.rows = rows
        self.applied = True
        if same_order:
            listing = self.getControl(100)
            for index, row in enumerate(rows):
                if row['label'] != previous[index]['label']:
                    if index in self.visible_indices:
                        listing.getListItem(self.visible_indices.index(index)).setLabel(row['label'])
                if row['enabled'] != previous[index]['enabled'] and index in self.visible_indices:
                    listing.getListItem(self.visible_indices.index(index)).setProperty('visibility', '' if row['enabled'] else L(31477))
            self.details()
        else:
            self.render()

    def onFocus(self, control_id):
        self.details()

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            self.close()
        elif self.getFocusId() == 100:
            self.details()

    def onClick(self, control_id):
        if control_id != 101 and (not self.visible_indices):
            return
        if control_id == 100:
            self.details()
            self.setFocusId(201)
            return
        row = self.rows[self.index]
        if row['section'] == 'settings' and control_id in (202, 203, 206):
            return
        dialog = xbmcgui.Dialog()
        try:
            if control_id == 101:
                name = dialog.input(L(31478))
                if name.strip():
                    item = new_item('custom_' + uuid.uuid4().hex, name)
                    self.commit(self.rows + [item])
                    self.index = len(self.rows) - 1
                    self.render()
                    self.setFocusId(100)
            elif control_id == 201:
                name = dialog.input(L(31480), defaultt=row['label'])
                if name.strip():
                    self.commit(changed(self.rows, self.index, label=name))
            elif control_id == 202:
                targets = [target for target in TARGETS if target[0] != 'settings']
                choice = dialog.select(L(31481), [target[1] for target in targets] + [L(31482), L(31483)])
                if 0 <= choice < len(targets):
                    target = targets[choice]
                    self.commit(changed(self.rows, self.index, section=target[0], actions=[{'command': target[2]}]))
                elif choice == len(targets):
                    import json
                    response = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'Favourites.GetFavourites', 'params': {'properties': ['window', 'windowparameter', 'path']}})))
                    favourites = response.get('result', {}).get('favourites', [])
                    selected = dialog.select(L(31482), [item['title'] for item in favourites])
                    if 0 <= selected < len(favourites):
                        item = favourites[selected]

                        def quoted(value):
                            return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'
                        action = 'ActivateWindow({},{},return)'.format(item['window'], quoted(item.get('windowparameter', ''))) if item.get('type') == 'window' else 'PlayMedia({})'.format(quoted(item.get('path', '')))
                        self.commit(changed(self.rows, self.index, actions=[{'command': action}]))
                elif choice == len(targets) + 1:
                    action = dialog.input(L(31484), defaultt=row['actions'][0]['command'])
                    if action.strip():
                        self.commit(changed(self.rows, self.index, actions=[{'command': action.strip()}]))
            elif control_id == 203:
                self.commit(changed(self.rows, self.index, enabled=not row['enabled']))
            elif control_id in (204, 205):
                position = self.visible_indices.index(self.index) + (-1 if control_id == 204 else 1)
                if 0 <= position < len(self.visible_indices):
                    target = self.visible_indices[position]
                    rows = list(self.rows)
                    rows[target], rows[self.index] = (rows[self.index], rows[target])
                    self.index = target
                    self.commit(rows)
            elif control_id == 206:
                if dialog.yesno(L(31485), L(31487).format(row['label'])):
                    self.commit(self.rows[:self.index] + self.rows[self.index + 1:])
                    self.setFocusId(100)
            elif control_id == 207:
                path = dialog.browseSingle(2, L(31486), 'files', '.jpg|.jpeg|.png|.webp', False, False, row['background'])
                if path:
                    self.commit(changed(self.rows, self.index, background=path))
            elif control_id == 209:
                self.commit(changed(self.rows, self.index, background=''))
        except (ValueError, TypeError) as error:
            dialog.ok(L(31479), str(error))

def activate(uid):
    rows = decode(xbmc.getInfoLabel('Skin.String({}.Config)'.format(PREFIX)))
    row = next((row for row in rows if row['uid'] == uid and row['enabled']), None)
    if row:
        for action in row['actions']:
            if not action['condition'] or xbmc.getCondVisibility(action['condition']):
                xbmc.executebuiltin(action['command'])
                break

def finish_edit(applied):
    if applied:
        request_reload(9042)
if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'activate':
        activate(sys.argv[2])
    else:
        editor = HomeMenuEditor('script-FlixiumHomeMenu.xml', SKIN, 'Default', '1080i')
        editor.doModal()
        applied = editor.applied
        del editor
        finish_edit(applied)
