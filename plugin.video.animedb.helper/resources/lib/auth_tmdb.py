import xbmcaddon
import xbmcgui
from resources.lib.tmdb import TMDBAPI

ADDON = xbmcaddon.Addon()

def authenticate_tmdb():
    from resources.lib.tmdb_bridge import test_tmdb_connection
    ok, msg = test_tmdb_connection()
    xbmcgui.Dialog().notification("TMDB", msg, xbmcgui.NOTIFICATION_INFO if ok else xbmcgui.NOTIFICATION_ERROR)
    return ok
