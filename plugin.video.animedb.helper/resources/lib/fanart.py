import os
import requests
import json
import xbmcaddon
import xbmcvfs
import xbmc

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Setup cache directory
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
ART_CACHE_DIR = os.path.join(PROFILE, 'art_cache')
os.makedirs(ART_CACHE_DIR, exist_ok=True)

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def fetch_art(anime_id, source='anilist'):
    """
    Fetch artwork for an anime
    """
    # Check cache first
    cache_file = os.path.join(ART_CACHE_DIR, f"{source}_{anime_id}.json")
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"Error reading art cache: {e}", xbmc.LOGWARNING)
    
    # Default art
    art = {
        'poster': '',
        'fanart': '',
        'banner': '',
        'clearlogo': ''
    }
    
    # Fetch from API
    try:
        if source == 'anilist':
            art = fetch_anilist_art(anime_id)
        elif source == 'mal':
            art = fetch_mal_art(anime_id)
        elif source == 'trakt':
            art = fetch_trakt_art(anime_id)
        
        # Cache result
        with open(cache_file, 'w') as f:
            json.dump(art, f)
        
        return art
    
    except Exception as e:
        log(f"Error fetching art: {e}", xbmc.LOGWARNING)
        return art

def fetch_anilist_art(anime_id):
    """
    Fetch artwork from AniList
    """
    from resources.lib.api import AnimeDBAPI
    api = AnimeDBAPI()
    
    details = api._anilist_anime_details(anime_id)
    
    if not details:
        return {
            'poster': '',
            'fanart': '',
            'banner': '',
            'clearlogo': ''
        }
    
    return {
        'poster': details.get('poster', ''),
        'fanart': details.get('banner', ''),
        'banner': details.get('banner', ''),
        'clearlogo': ''
    }

def fetch_mal_art(anime_id):
    """
    Fetch artwork from MyAnimeList
    """
    from resources.lib.api import AnimeDBAPI
    api = AnimeDBAPI()
    
    details = api._mal_anime_details(anime_id)
    
    if not details:
        return {
            'poster': '',
            'fanart': '',
            'banner': '',
            'clearlogo': ''
        }
    
    return {
        'poster': details.get('poster', ''),
        'fanart': '',
        'banner': '',
        'clearlogo': ''
    }

def fetch_trakt_art(anime_id):
    """
    Fetch artwork from Trakt (via TMDB)
    """
    from resources.lib.api import AnimeDBAPI
    api = AnimeDBAPI()
    
    details = api._trakt_anime_details(anime_id)
    
    if not details:
        return {
            'poster': '',
            'fanart': '',
            'banner': '',
            'clearlogo': ''
        }
    
    # Trakt doesn't provide images directly, would need to use TMDB or TVDB
    # This is a simplified version
    return {
        'poster': '',
        'fanart': '',
        'banner': '',
        'clearlogo': ''
    }

def clear_art_cache():
    """
    Clear artwork cache
    """
    for file in os.listdir(ART_CACHE_DIR):
        try:
            os.remove(os.path.join(ART_CACHE_DIR, file))
        except Exception as e:
            log(f"Error removing art cache file: {e}", xbmc.LOGWARNING)
    
    log("Art cache cleared")
    return True