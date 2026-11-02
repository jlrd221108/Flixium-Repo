"""A short, per-profile setup flow. Editors keep their existing save semantics."""

from flixium_localization import localize as L
import sys
import time

import xbmc
import xbmcgui
import xbmcvfs

PREFIX = 'Flixium.Setup.'
HOME = xbmcgui.Window(10000)
SKIN = xbmcvfs.translatePath('special://skin/')
PAGES = (L(31531), L(31285), L(31532), L(31533), L(31534))


def flag(name):
    return xbmc.getCondVisibility('Skin.HasSetting({}{})'.format(PREFIX, name))


def setting(name, value):
    xbmc.executebuiltin('Skin.SetString({}{},{})'.format(PREFIX, name, value), True)


def boolean(name, value):
    xbmc.executebuiltin('Skin.{}({}{})'.format('SetBool' if value else 'Reset', PREFIX, name), True)


def auto_eligible():
    if flag('Completed'):
        return False
    if flag('Seen'):
        return flag('AutoResume')
    return flag('Pending') or not xbmc.getInfoLabel('Skin.String(Flixium.DefaultsVersion)')


def first_install_appearance():
    # Switching to a newly installed skin can enter Home without Startup.xml.
    # Once setup has started, an explicit Glass Off choice must remain off.
    from flixium_first_install import apply
    apply()


class SetupSurface(xbmcgui.WindowXML):
    """Keep a settings background in place while wizard dialogs are rebuilt."""

    def onInit(self):
        # ReloadSkin restores the active normal window, but closes its dialogs.
        # The original Python doModal() is still waiting, so restore that same
        # wizard instead of starting another setup script/session.
        if getattr(self, 'initialized', False):
            wizard = getattr(self, 'wizard', None)
            if wizard is not None and not wizard.finished and not wizard.open_sources:
                wizard.clearProperty('editing')
                wizard.show()
        self.initialized = True

    def onAction(self, action):
        # Only the wizard's explicit exit buttons may end the setup flow.
        pass


class SourceChooser(SetupSurface):
    """A real window so Kodi's source browsers can return through window history."""

    def onInit(self):
        self.setProperty('sources', 'true')
        self.setFocusId(getattr(self, 'last_focus', 101))

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            self.close()

    def onClick(self, control_id):
        routes = {101: 'Videos,sources://video/',
                  102: 'Music,sources://music/',
                  103: 'Pictures,sources://pictures/'}
        if control_id == 201:
            self.close()
        elif control_id in routes:
            self.last_focus = control_id
            xbmc.executebuiltin('ActivateWindow({},return)'.format(routes[control_id]))


class SetupWizard(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.automatic = kwargs.pop('automatic', False)
        self.previous = kwargs.pop('previous', None)
        self.restore_focus = kwargs.pop('restore_focus', None)
        super().__init__(*args, **kwargs)
        try:
            self.page = max(0, min(4, int(xbmc.getInfoLabel('Skin.String(Flixium.Setup.Step)') or '0')))
        except ValueError:
            self.page = 0
        self.dirty = False
        self.open_sources = False
        self.reopen = False
        self.replacement = None
        self.finished = False

    def onInit(self):
        boolean('Seen', True)
        boolean('Started', True)
        boolean('AutoResume', self.automatic)
        boolean('Pending', self.automatic)
        self.render()
        if self.restore_focus is not None:
            self.setFocusId(self.restore_focus)
        if self.previous is not None:
            # The new dialog has loaded its XML and populated its controls.
            # Retire the old one only now, never between the two dialogs.
            self.previous.close()
            self.previous = None

    def refresh(self, focus_id):
        self.replacement = SetupWizard('script-FlixiumSetup.xml', SKIN, 'Default', '1080i',
                                       automatic=self.automatic, previous=self,
                                       restore_focus=focus_id)
        self.reopen = True
        self.replacement.show()

    def render(self):
        setting('Step', self.page)
        self.setProperty('page', str(self.page))
        self.setProperty('step', '{} / 5'.format(self.page + 1))
        self.setProperty('title', PAGES[self.page])
        self.setProperty('next', L(31540) if self.page == 0 else L(31544) if self.page == 4 else L(31545))
        self.setProperty('skip', L(31541) if self.page == 0 else L(31542))
        subtitles = ('', L(31536), L(31537),
                     L(31538), L(31539))
        self.setProperty('subtitle', subtitles[self.page])
        for i in range(4):
            self.setProperty('option{}'.format(i + 1), '')
        self.setProperty('preview', '')
        if self.page == 1:
            import flixium_theme as theme
            name = theme.presets()[theme.scheme_index()][0]
            glass = xbmc.getCondVisibility('Skin.HasSetting(Flixium.Glass.Enabled)')
            corner = L(31543) if xbmc.getCondVisibility('Skin.HasSetting(Flixium.Unrounded)') else L(31361) if xbmc.getCondVisibility('Skin.HasSetting(Flixium.ExtraRounded)') else L(31362)
            for key, value in enumerate((L(31547) + name, L(31548) + (L(31517) if glass else L(31429)), L(31549) + corner, L(31290))):
                self.setProperty('option{}'.format(key + 1), value)
        elif self.page == 2:
            from flixium_home_menu import initial_items
            self.setProperty('option1', L(31546))
            self.setProperty('preview', '[CAPITALIZE]' + '  ·  '.join(r['label'] for r in initial_items() if r['enabled'] and r['section'] != 'settings') + '[/CAPITALIZE]')
        elif self.page == 3:
            self.setProperty('option1', L(31550))
            self.setProperty('option2', L(31283))
            has_media = xbmc.getCondVisibility('Library.HasContent(movies) | Library.HasContent(tvshows) | Library.HasContent(music)')
            self.setProperty('preview', L(31551) if has_media else L(31552))
        elif self.page == 4:
            from flixium_home_menu import initial_items
            rows = [r for r in initial_items() if r['enabled'] and r['section'] != 'settings']
            self.setProperty('preview', L(31555).format(len(rows)))
        self.setProperty('ready', 'true')
        # Visibility expressions update on the GUI thread. Wait a frame before
        # focusing a control on a newly shown page; never blank a live page.
        xbmc.sleep(40)
        self.setFocusId(101 if self.page in (1, 2, 3) else 203)

    def finish(self):
        self.finished = True
        boolean('Completed', True)
        boolean('Pending', False)
        boolean('Started', False)
        boolean('AutoResume', False)
        setting('Step', 0)
        self.close()

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            if self.page:
                self.page -= 1
                self.render()

    def onClick(self, control_id):
        if control_id == 201:
            self.page = max(0, self.page - 1)
            self.render()
        elif control_id == 202:
            self.finish()
        elif control_id == 203:
            if self.page == 4:
                self.finish()
            else:
                self.page += 1
                self.render()
        elif 101 <= control_id <= 104:
            # Only full-page editors replace the wizard's contents. Small
            # popups keep the existing page visible throughout their transition.
            if (self.page == 2 and control_id == 101) or (self.page == 3 and control_id == 102):
                self.setProperty('editing', 'true')
                xbmc.sleep(30)
            try:
                self.choose(control_id - 101)
            except (RuntimeError, ValueError, ImportError) as error:
                xbmc.log('Flixium setup: {}'.format(error), xbmc.LOGERROR)
                xbmcgui.Dialog().ok(L(31556), L(31557))
            finally:
                if not self.open_sources and not self.reopen:
                    self.clearProperty('editing')
            if not self.open_sources and not self.reopen:
                self.render()
                self.setFocusId(control_id)

    def choose(self, index):
        dialog = xbmcgui.Dialog()
        if self.page == 1:
            import flixium_theme as theme
            if index == 0:
                choice = dialog.select(L(31286), [r[0] for r in theme.presets()], preselect=theme.scheme_index())
                if choice < 0:
                    return
                theme.apply_preset(choice)
            elif index == 1:
                if not xbmc.getCondVisibility('System.AddonIsEnabled(script.flixium.helper)'):
                    dialog.ok(L(31287), L(31553))
                    return
                xbmc.executebuiltin('Skin.ToggleSetting(Flixium.Glass.Enabled)', True)
            elif index == 2:
                current = 0 if xbmc.getCondVisibility('Skin.HasSetting(Flixium.Unrounded)') else 2 if xbmc.getCondVisibility('Skin.HasSetting(Flixium.ExtraRounded)') else 1
                choice = dialog.select(L(31554), [L(31543), L(31362), L(31361)], preselect=current)
                if choice < 0:
                    return
                for key, enabled in (('Flixium.Unrounded', choice == 0), ('Flixium.ExtraRounded', choice == 2)):
                    xbmc.executebuiltin('Skin.{}({})'.format('SetBool' if enabled else 'Reset', key), True)
            else:
                import flixium_fonts
                flixium_fonts.main()
            self.dirty = True
            xbmc.sleep(100)
            from flixium_glass import prepare
            prepare()
            # Load the new conditional includes above the existing page. Its
            # onInit closes this dialog after the replacement is ready.
            self.refresh(101 + index)
        elif self.page == 2:
            if index == 0:
                from flixium_home_menu import HomeMenuEditor
                editor = HomeMenuEditor('script-FlixiumHomeMenu.xml', SKIN, 'Default', '1080i')
                editor.doModal()
                self.dirty = self.dirty or editor.applied
                del editor
        elif self.page == 3 and index == 0:
            self.open_sources = True
            self.close()
        elif self.page == 3 and index == 1:
            from flixium_widgets import WidgetEditor
            editor = WidgetEditor('script-FlixiumWidgets.xml', SKIN, 'Default', '1080i')
            editor.doModal()
            self.dirty = self.dirty or editor.applied
            del editor


def main():
    automatic = len(sys.argv) > 1 and sys.argv[1] == 'auto'
    if xbmc.getSkinDir() != 'skin.flixium' or HOME.getProperty('flixium.setup.running') == 'true':
        return
    if automatic:
        if not auto_eligible():
            boolean('Seen', True)
            boolean('Pending', False)
            return
    else:
        if flag('Completed') and not flag('Started'):
            setting('Step', 0)
        # Redoing setup must never arm automatic setup on the next Kodi start.
        boolean('AutoResume', False)
        boolean('Pending', False)
    HOME.setProperty('flixium.setup.running', 'true')
    surface = None
    try:
        first_install_appearance()
        if automatic:
            # Let Kodi's keep-this-skin confirmation finish before presenting setup.
            monitor = xbmc.Monitor()
            deadline = time.monotonic() + 30
            while xbmc.getCondVisibility('System.HasActiveModalDialog'):
                if time.monotonic() >= deadline or monitor.waitForAbort(0.25) or xbmc.getSkinDir() != 'skin.flixium':
                    return
            if not xbmc.getCondVisibility('Window.IsActive(home)'):
                return
        if xbmc.getCondVisibility('Skin.HasSetting(Flixium.Glass.Enabled) + System.AddonIsEnabled(script.flixium.helper)'):
            # Resolve the active profile's glass materials before the XML window
            # reads the same theme includes used by Skin Settings.
            from flixium_glass import prepare
            prepare()
        dirty = False
        surface = SetupSurface('script-FlixiumSetupSurface.xml', SKIN, 'Default', '1080i')
        surface.show()
        wizard = SetupWizard('script-FlixiumSetup.xml', SKIN, 'Default', '1080i', automatic=automatic)
        while True:
            surface.wizard = wizard
            wizard.doModal()
            dirty = dirty or wizard.dirty
            sources, replacement = wizard.open_sources, wizard.replacement
            surface.wizard = None
            del wizard
            if replacement is not None:
                wizard = replacement
                continue
            if sources:
                chooser = SourceChooser('script-FlixiumSetupSurface.xml', SKIN, 'Default', '1080i')
                chooser.doModal()
                del chooser
                wizard = SetupWizard('script-FlixiumSetup.xml', SKIN, 'Default', '1080i', automatic=automatic)
                continue
            break
    finally:
        if surface is not None:
            surface.close()
        HOME.clearProperty('flixium.setup.running')
    if dirty:
        from flixium_reload import request_reload
        request_reload()


if __name__ == '__main__':
    main()
