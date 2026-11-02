"""Reload only after the requesting script and its Python windows have exited."""
import gc
import sys
import xbmc

ALARM = "Flixium.ReloadSkin"

def request_reload(focus=None):
    # WindowXMLDialog.close() queues GUI teardown; del alone is not a GUI barrier.
    # Collect Python cycles now, then let Kodi finish closing/freeing the window
    # before it clears the shared texture manager for ReloadSkin.
    gc.collect()
    target = str(int(focus)) if focus is not None else "0"
    xbmc.executebuiltin("CancelAlarm({},true)".format(ALARM), True)
    xbmc.executebuiltin("AlarmClock({},RunScript(special://skin/extras/flixium_reload.py,apply,{}),00:01,silent)".format(ALARM, target), True)

def apply_reload(focus=0):
    # Setup also owns normal windows (its background and source chooser), and
    # briefly replaces dialogs for theme previews. Defer through the whole flow.
    if xbmc.getCondVisibility("System.HasActiveModalDialog | String.IsEqual(Window(home).Property(flixium.setup.running),true)"):
        request_reload(focus or None)
        return
    if xbmc.getCondVisibility("Window.IsActive(skinsettings)"):
        xbmc.executebuiltin("SetProperty(Flixium.Customisation.Restoring,true,home)", True)
    xbmc.executebuiltin("ReloadSkin()", True)
    if focus and xbmc.getCondVisibility("Window.IsActive(skinsettings)"):
        xbmc.executebuiltin("SetFocus(9000,1)", True)
        xbmc.executebuiltin("SetFocus({})".format(int(focus)), True)

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "apply":
    apply_reload(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
