import xbmcaddon
import xbmc
import time
import os
import json
import xbmcvfs

from resources.lib.api import AnimeDBAPI, cached

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

# Recommendations cache directory
RECS_CACHE_DIR = os.path.join(PROFILE, 'recommendations')
os.makedirs(RECS_CACHE_DIR, exist_ok=True)

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def get_recommendations():
    # Fetch trending anime (not personalized)
    api = AnimeDBAPI()
    trending = api.trending()
    # Label as 'Top Rated Anime' instead of 'Recommended Anime'
    return trending

def get_anilist_recommendations():
    """
    Get recommendations from AniList
    """
    api = AnimeDBAPI()
    
    # Get user's AniList ID
    user_id = get_anilist_user_id()
    
    if not user_id:
        return []
    
    # Query for recommendations
    query = '''
    query ($userId: Int, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        recommendations(userId: $userId, sort: RATING_DESC) {
          media {
            id title { romaji english } description averageScore genres coverImage { large medium } bannerImage
          }
        }
      }
    }'''
    
    data = api._anilist_query(query, {
        'userId': user_id,
        'page': 1,
        'perPage': int(ADDON.getSetting('items_per_page'))
    })
    
    if not data:
        return []
    
    return [
        {
            'id': str(r['media']['id']),
            'title': r['media']['title'].get('english') or r['media']['title'].get('romaji', ''),
            'description': r['media'].get('description', ''),
            'score': r['media'].get('averageScore', 0),
            'genres': r['media'].get('genres', []),
            'poster': r['media'].get('coverImage', {}).get('large', ''),
            'banner': r['media'].get('bannerImage', ''),
            'source': 'anilist'
        } for r in data.get('data', {}).get('Page', {}).get('recommendations', [])
    ]

def get_anilist_user_id():
    """
    Get AniList user ID
    """
    api = AnimeDBAPI()
    
    query = '''
    query {
      Viewer {
        id
      }
    }'''
    
    data = api._anilist_query(query)
    
    if not data:
        return None
    
    return data.get('data', {}).get('Viewer', {}).get('id')

def get_mal_recommendations():
    """
    Get recommendations from MyAnimeList
    """
    api = AnimeDBAPI()
    
    resp = api._mal_request('https://api.myanimelist.net/v2/anime/suggestions?limit=10')
    
    if not resp:
        return []
    
    data = resp.json()
    
    recommendations = []
    for a in data.get('data', []):
        anime_id = str(a['node']['id'])
        details = api._mal_anime_details(anime_id) or {}
        recommendations.append({
            'id': anime_id,
            'title': a['node']['title'],
            'description': details.get('description', '') or 'No description available.',
            'score': details.get('score', 0),
            'genres': details.get('genres', []),
            'poster': a['node'].get('main_picture', {}).get('large', '') or a['node'].get('main_picture', {}).get('medium', ''),
            'banner': '',
            'episodes': details.get('episodes', 0),
            'source': 'mal'
        })
    return recommendations

def get_trakt_recommendations():
    """
    Get recommendations from Trakt
    """
    api = AnimeDBAPI()
    
    resp = api._trakt_request('https://api.trakt.tv/recommendations/shows?limit=10')
    
    if not resp:
        return []
    
    data = resp.json()
    
    return [
        {
            'id': str(show['ids'].get('trakt', '')),
            'title': show.get('title', ''),
            'description': show.get('overview', ''),
            'score': 0,  # Trakt API doesn't provide score in this endpoint
            'genres': [],  # Trakt API doesn't provide genres in this endpoint
            'poster': '',  # Trakt API doesn't provide images in this endpoint
            'banner': '',
            'source': 'trakt'
        } for show in data
    ]

def get_similar_anime(anime_id, source='anilist'):
    """
    Get similar anime
    """
    if source == 'anilist':
        return get_anilist_similar(anime_id)
    elif source == 'mal':
        return get_mal_similar(anime_id)
    elif source == 'trakt':
        return get_trakt_similar(anime_id)
    
    return []

def get_anilist_similar(anime_id):
    """
    Get similar anime from AniList
    """
    api = AnimeDBAPI()
    
    query = '''
    query ($id: Int, $page: Int, $perPage: Int) {
      Media(id: $id, type: ANIME) {
        recommendations(page: $page, perPage: $perPage, sort: RATING_DESC) {
          nodes {
            mediaRecommendation {
              id title { romaji english } description averageScore genres coverImage { large medium } bannerImage
            }
          }
        }
      }
    }'''
    
    data = api._anilist_query(query, {
        'id': int(anime_id),
        'page': 1,
        'perPage': int(ADDON.getSetting('items_per_page'))
    })
    
    if not data:
        return []
    
    return [
        {
            'id': str(r['mediaRecommendation']['id']),
            'title': r['mediaRecommendation']['title'].get('english') or r['mediaRecommendation']['title'].get('romaji', ''),
            'description': r['mediaRecommendation'].get('description', ''),
            'score': r['mediaRecommendation'].get('averageScore', 0),
            'genres': r['mediaRecommendation'].get('genres', []),
            'poster': r['mediaRecommendation'].get('coverImage', {}).get('large', ''),
            'banner': r['mediaRecommendation'].get('bannerImage', ''),
            'source': 'anilist'
        } for r in data.get('data', {}).get('Media', {}).get('recommendations', {}).get('nodes', [])
    ]

def get_mal_similar(anime_id):
    """
    Get similar anime from MyAnimeList
    """
    api = AnimeDBAPI()
    
    resp = api._mal_request(f'https://api.myanimelist.net/v2/anime/{anime_id}/recommendations?limit=10')
    
    if not resp:
        return []
    
    data = resp.json()
    
    return [
        {
            'id': str(r['node']['id']),
            'title': r['node']['title'],
            'description': '',  # MAL API doesn't provide description in this endpoint
            'score': 0,  # MAL API doesn't provide score in this endpoint
            'genres': [],  # MAL API doesn't provide genres in this endpoint
            'poster': r['node'].get('main_picture', {}).get('large', '') or r['node'].get('main_picture', {}).get('medium', ''),
            'banner': '',
            'source': 'mal'
        } for r in data.get('data', [])
    ]

def get_trakt_similar(anime_id):
    """
    Get similar anime from Trakt
    """
    api = AnimeDBAPI()
    
    resp = api._trakt_request(f'https://api.trakt.tv/shows/{anime_id}/related?limit=10')
    
    if not resp:
        return []
    
    data = resp.json()
    
    return [
        {
            'id': str(show['ids'].get('trakt', '')),
            'title': show.get('title', ''),
            'description': show.get('overview', ''),
            'score': 0,  # Trakt API doesn't provide score in this endpoint
            'genres': [],  # Trakt API doesn't provide genres in this endpoint
            'poster': '',  # Trakt API doesn't provide images in this endpoint
            'banner': '',
            'source': 'trakt'
        } for show in data
    ]