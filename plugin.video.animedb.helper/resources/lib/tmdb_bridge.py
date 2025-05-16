import xbmcaddon
from resources.lib.tmdb import TMDBAPI

ADDON = xbmcaddon.Addon()

def get_tmdb_api():
    if not ADDON.getSettingBool('tmdb_enabled'):
        return None
    api_key = ADDON.getSetting('tmdb_api_key')
    if not api_key:
        return None
    return TMDBAPI(api_key)

def test_tmdb_connection():
    api_key = ADDON.getSetting('tmdb_api_key')
    if not api_key:
        return False, 'No TMDB API Key found.'
    try:
        tmdb = TMDBAPI(api_key)
        tmdb.search_tv('Naruto')
        return True, 'TMDB authentication successful!'
    except Exception as e:
        return False, f'TMDB authentication failed: {e}'

def find_tmdb_id(anime_title):
    tmdb = get_tmdb_api()
    if not tmdb:
        return None
    results = tmdb.search_tv(anime_title)
    if not results:
        return None
    # Try to match exactly first
    for result in results:
        if result['name'].lower() == anime_title.lower():
            return result['id']
    # Otherwise, return the first result
    return results[0]['id'] if results else None

def get_tmdb_episodes(anime_title, season=1):
    tmdb = get_tmdb_api()
    if not tmdb:
        return []
    tmdb_id = find_tmdb_id(anime_title)
    if not tmdb_id:
        return []
    return tmdb.get_episodes(tmdb_id, season)
