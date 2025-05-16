import xbmcaddon
import xbmc
import time
import datetime
import os
import json
import xbmcvfs

from resources.lib.api import AnimeDBAPI, cached

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def get_upcoming():
    """
    Get upcoming anime episodes
    """
    def _fetch():
        api = AnimeDBAPI()
        
        # Get upcoming episodes from enabled services
        upcoming = []
        
        if ADDON.getSettingBool('anilist_enabled'):
            upcoming.extend(get_anilist_upcoming())
        
        if ADDON.getSettingBool('mal_enabled'):
            upcoming.extend(get_mal_upcoming())
        
        if ADDON.getSettingBool('trakt_enabled'):
            upcoming.extend(get_trakt_upcoming())
        
        # Sort by airing time
        upcoming.sort(key=lambda x: x.get('airing_at', 0))
        
        return upcoming
    
    return cached('upcoming', _fetch, ttl=3600)  # Cache for 1 hour

def get_anilist_upcoming():
    """
    Get upcoming episodes from AniList
    """
    api = AnimeDBAPI()
    
    # Get current time
    now = int(time.time())
    
    # Get upcoming episodes in the next week
    week_later = now + (7 * 24 * 3600)
    
    query = '''
    query ($page: Int, $perPage: Int, $airingAtGreater: Int, $airingAtLesser: Int) {
      Page(page: $page, perPage: $perPage) {
        airingSchedules(airingAt_greater: $airingAtGreater, airingAt_lesser: $airingAtLesser, sort: TIME) {
          airingAt
          episode
          media {
            id title { romaji english } coverImage { large medium }
          }
        }
      }
    }'''
    
    data = api._anilist_query(query, {
        'page': 1,
        'perPage': 50,
        'airingAtGreater': now,
        'airingAtLesser': week_later
    })
    
    if not data:
        return []
    
    return [
        {
            'id': str(a['media']['id']),
            'title': a['media']['title'].get('english') or a['media']['title'].get('romaji', ''),
            'episode': a['episode'],
            'airing_at': a['airingAt'],
            'airing_date': datetime.datetime.fromtimestamp(a['airingAt']).strftime('%Y-%m-%d %H:%M'),
            'poster': a['media'].get('coverImage', {}).get('large', '') or a['media'].get('coverImage', {}).get('medium', ''),
            'source': 'anilist'
        } for a in data.get('data', {}).get('Page', {}).get('airingSchedules', [])
    ]

def get_mal_upcoming():
    """
    Get upcoming episodes from MyAnimeList
    """
    # MyAnimeList API doesn't provide airing schedule information
    # This is a placeholder for future implementation if the API adds this feature
    return []

def get_trakt_upcoming():
    """
    Get upcoming episodes from Trakt
    """
    api = AnimeDBAPI()
    
    # Get user's watchlist shows
    watchlist = []
    
    if ADDON.getSettingBool('trakt_enabled'):
        resp = api._trakt_request('https://api.trakt.tv/users/me/watchlist/shows')
        
        if resp:
            watchlist = resp.json()
    
    # Get calendar for watchlist shows
    upcoming = []
    
    for show in watchlist:
        show_id = show.get('show', {}).get('ids', {}).get('trakt')
        
        if not show_id:
            continue
        
        resp = api._trakt_request(f'https://api.trakt.tv/shows/{show_id}/next_episode')
        
        if not resp:
            continue
        
        episode = resp.json()
        
        if not episode:
            continue
        
        # Convert first_aired to timestamp
        first_aired = episode.get('first_aired')
        
        if not first_aired:
            continue
        
        try:
            airing_at = int(datetime.datetime.fromisoformat(first_aired.replace('Z', '+00:00')).timestamp())
        except:
            continue
        
        # Only include episodes airing in the next week
        now = int(time.time())
        week_later = now + (7 * 24 * 3600)
        
        if airing_at < now or airing_at > week_later:
            continue
        
        upcoming.append({
            'id': str(show_id),
            'title': show.get('show', {}).get('title', ''),
            'episode': episode.get('number', 0),
            'airing_at': airing_at,
            'airing_date': datetime.datetime.fromtimestamp(airing_at).strftime('%Y-%m-%d %H:%M'),
            'poster': '',  # Trakt API doesn't provide images in this endpoint
            'source': 'trakt'
        })
    
    return upcoming

def get_calendar():
    """
    Get calendar of upcoming anime episodes
    """
    upcoming = get_upcoming()
    
    # Group by date
    calendar = {}
    
    for episode in upcoming:
        date = datetime.datetime.fromtimestamp(episode['airing_at']).strftime('%Y-%m-%d')
        
        if date not in calendar:
            calendar[date] = []
        
        calendar[date].append(episode)
    
    return calendar