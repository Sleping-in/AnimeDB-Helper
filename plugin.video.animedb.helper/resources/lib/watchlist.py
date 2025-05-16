import xbmcaddon
import xbmc
import os
import json
import xbmcvfs

from resources.lib.api import AnimeDBAPI

try:
    import xbmcgui
    import xbmcplugin
except ImportError:
    from . import xbmcgui, xbmcplugin

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

# Watchlist directory
WATCHLIST_DIR = os.path.join(PROFILE, 'watchlist')
os.makedirs(WATCHLIST_DIR, exist_ok=True)

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def get_local_watchlist():
    """
    Get local watchlist
    """
    watchlist_file = os.path.join(WATCHLIST_DIR, 'watchlist.json')
    
    if os.path.exists(watchlist_file):
        try:
            with open(watchlist_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"Error reading watchlist: {e}", xbmc.LOGWARNING)
    
    return []

def save_local_watchlist(watchlist):
    """
    Save local watchlist
    """
    watchlist_file = os.path.join(WATCHLIST_DIR, 'watchlist.json')
    
    try:
        with open(watchlist_file, 'w') as f:
            json.dump(watchlist, f)
        
        return True
    except Exception as e:
        log(f"Error saving watchlist: {e}", xbmc.LOGERROR)
        return False

def add_to_watchlist(anime_id, source='anilist'):
    """
    Add anime to watchlist
    """
    # Get anime details
    api = AnimeDBAPI()
    details = api.anime_details(anime_id, source)
    
    if not details:
        return False
    
    # Create watchlist item
    item = {
        'id': anime_id,
        'title': details.get('title', ''),
        'poster': details.get('poster', ''),
        'banner': details.get('banner', ''),
        'source': source
    }
    
    # Get current watchlist
    watchlist = get_local_watchlist()
    
    # Check if already in watchlist
    for existing in watchlist:
        if existing.get('id') == anime_id and existing.get('source') == source:
            return True
    
    # Add to watchlist
    watchlist.append(item)
    
    # Save watchlist
    return save_local_watchlist(watchlist)

def remove_from_watchlist(anime_id, source='anilist'):
    """
    Remove anime from watchlist
    """
    # Get current watchlist
    watchlist = get_local_watchlist()
    
    # Remove from watchlist
    watchlist = [item for item in watchlist if not (item.get('id') == anime_id and item.get('source') == source)]
    
    # Save watchlist
    return save_local_watchlist(watchlist)

def is_in_watchlist(anime_id, source='anilist'):
    """
    Check if anime is in watchlist
    """
    watchlist = get_local_watchlist()
    
    for item in watchlist:
        if item.get('id') == anime_id and item.get('source') == source:
            return True
    
    return False

def toggle_watchlist(anime_id, source='anilist'):
    """
    Toggle anime in watchlist
    """
    if is_in_watchlist(anime_id, source):
        return remove_from_watchlist(anime_id, source)
    else:
        return add_to_watchlist(anime_id, source)

def sync_watchlist_to_services():
    """
    Sync local watchlist to services
    """
    # Get local watchlist
    watchlist = get_local_watchlist()
    
    # Sync to enabled services
    if ADDON.getSettingBool('anilist_enabled'):
        sync_to_anilist(watchlist)
    
    if ADDON.getSettingBool('mal_enabled'):
        sync_to_mal(watchlist)
    
    if ADDON.getSettingBool('trakt_enabled'):
        sync_to_trakt(watchlist)
    
    return True

def sync_to_anilist(watchlist):
    """
    Sync watchlist to AniList
    """
    api = AnimeDBAPI()
    
    # Filter for AniList items
    anilist_items = [item for item in watchlist if item.get('source') == 'anilist']
    
    # In a real add-on, you would implement logic to sync with AniList API
    # This would involve adding items to the user's AniList watchlist
    # For this example, we'll just log the count
    
    log(f"Syncing {len(anilist_items)} items to AniList")
    return True

def sync_to_mal(watchlist):
    """
    Sync watchlist to MyAnimeList
    """
    api = AnimeDBAPI()
    
    # Filter for MAL items
    mal_items = [item for item in watchlist if item.get('source') == 'mal']
    
    # In a real add-on, you would implement logic to sync with MAL API
    # This would involve adding items to the user's MAL watchlist
    # For this example, we'll just log the count
    
    log(f"Syncing {len(mal_items)} items to MyAnimeList")
    return True

def sync_to_trakt(watchlist):
    """
    Sync watchlist to Trakt
    """
    api = AnimeDBAPI()
    
    # Filter for Trakt items
    trakt_items = [item for item in watchlist if item.get('source') == 'trakt']
    
    # In a real add-on, you would implement logic to sync with Trakt API
    # This would involve adding items to the user's Trakt watchlist
    # For this example, we'll just log the count
    
    log(f"Syncing {len(trakt_items)} items to Trakt")
    return True

def list_watchlist(handle):
    from resources.lib.watchlist import get_local_watchlist
    anime_list = get_local_watchlist()
    if not anime_list:
        xbmcgui.Dialog().notification(ADDON.getLocalizedString(31022), ADDON.getLocalizedString(31023), xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setPluginCategory(handle, 'Watchlist')
        xbmcplugin.endOfDirectory(handle)
        return
    from resources.lib.ui import list_anime
    list_anime(handle, anime_list, title='Watchlist')