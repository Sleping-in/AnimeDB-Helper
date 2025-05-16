"""
AnimeDBAPI: Unified API interface for anime metadata, watchlists, and details from AniList, MyAnimeList, and Trakt.

This module provides a single class, AnimeDBAPI, which abstracts access to multiple anime metadata providers and user lists.
It handles authentication, caching, and error handling for each service, and exposes unified methods for fetching anime details,
watchlists, trending/seasonal anime, genres, and search results.

All file I/O uses xbmcvfs for Kodi Omega compatibility. Caching is handled via JSON files in the addon's profile cache directory.
"""
import os
import time
import json
import requests
from datetime import datetime
try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
except ImportError:
    from resources.lib import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
from resources.lib.auth_utils import refresh_token

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Setup cache directory
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
CACHE_DIR = os.path.join(PROFILE, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# API endpoints
ANILIST_API = 'https://graphql.anilist.co'
MAL_API = 'https://api.myanimelist.net/v2'
TRAKT_API = 'https://api.trakt.tv'

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def cached(key, func, ttl=None):
    """
    Cache the result of a function call
    """
    if ttl is None:
        try:
            ttl = int(ADDON.getSetting('cache_ttl'))
        except (ValueError, TypeError):
            log("Invalid cache_ttl setting. Using default TTL of 3600 seconds.", xbmc.LOGWARNING)
            ttl = 3600
        # Convert to seconds
        ttl = ttl * 3600

    # Skip cache if disabled
    if not ADDON.getSettingBool('cache_enabled'):
        return func()

    path = os.path.join(CACHE_DIR, f"{key}.json")

    # Check if cache exists and is valid
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"Error reading cache: {e}", xbmc.LOGWARNING)

    # Call the function and cache the result
    result = func()
    try:
        with open(path, 'w') as f:
            json.dump(result, f)
    except Exception as e:
        log(f"Error writing cache: {e}", xbmc.LOGWARNING)

    return result

def clear_cache():
    """
    Clear all cached data
    """
    for file in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, file))
        except Exception as e:
            log(f"Error removing cache file: {e}", xbmc.LOGWARNING)

    log("Cache cleared")
    return True

class AnimeDBAPI:
    """
    Unified API interface for anime metadata, watchlists, and details from AniList, MyAnimeList, and Trakt.

    This class provides methods to fetch anime details, watchlists, trending/seasonal anime, genres, and search results
    from multiple sources. It handles authentication, caching, and error handling for each service.
    """
    def anilist_episodes(self, anime_id):
        """
        Fetch episode details (number, title, description, thumbnail, air date, duration) from AniList for a given anime_id.
        Returns a list of episode dicts.
        """
        query = '''
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            id
            title { romaji english native }
            coverImage { extraLarge large medium }
            bannerImage
            duration
            episodes
            streamingEpisodes {
              title
              thumbnail
              url
              site
            }
            airingSchedule(notYetAired: false) {
              nodes {
                episode
                airingAt
              }
            }
          }
        }'''
        data = self._anilist_query(query, {'id': int(anime_id)})
        if not data or 'errors' in data:
            return []
        media = data.get('data', {}).get('Media', {})
        poster = media.get('coverImage', {}).get('extraLarge') or media.get('coverImage', {}).get('large') or media.get('coverImage', {}).get('medium', '')
        banner = media.get('bannerImage', '')
        duration = media.get('duration', 0)
        # Map episode air dates by number
        airing_nodes = media.get('airingSchedule', {}).get('nodes', [])
        air_dates = {int(n.get('episode', 0)): n.get('airingAt') for n in airing_nodes if n.get('episode')}
        # Try to get streamingEpisodes (AniList sometimes provides thumbnails here)
        streaming_eps = media.get('streamingEpisodes', [])
        episodes = []
        show_description = media.get('description', '')
        for ep in streaming_eps:
            num = int(ep.get('episode', 0))
            thumb = ep.get('thumbnail') or poster or banner
            episodes.append({
                'number': num,
                'title': ep.get('title', f"Episode {num}"),
                'description': show_description or '',  # Use show-level description as fallback
                'thumbnail': thumb,
                'air_date': air_dates.get(num),
                'duration': duration
            })
        # Fallback: If there are missing episodes, fill in with generic info
        total_eps = media.get('episodes', 0) or len(episodes)
        existing = {ep['number'] for ep in episodes}
        for i in range(1, total_eps + 1):
            if i not in existing:
                episodes.append({
                    'number': i,
                    'title': f"Episode {i}",
                    'description': show_description or '',
                    'thumbnail': poster or banner,
                    'air_date': air_dates.get(i),
                    'duration': duration
                })
        # Sort by episode number
        episodes.sort(key=lambda x: x['number'])
        return episodes


    def __init__(self):
        """
        Initialize the API wrapper, reading debug logging setting from the Kodi addon.
        """
        self.debug = ADDON.getSettingBool('debug_logging')

    def _log(self, message, level=xbmc.LOGINFO):
        """
        Log a message if debug logging is enabled, or if the log level is not DEBUG.
        """
        if self.debug or level != xbmc.LOGDEBUG:
            log(message, level)

    # AniList API methods

    def _get_anilist_token(self):
        """
        Get AniList token from settings. Returns the token string or an empty string if not set.
        """
        try:
            return ADDON.getSetting('anilist_token')
        except Exception:
            return ''

    def _refresh_anilist_token(self):
        """
        Refresh AniList token using the refresh_token utility.
        """
        return refresh_token('anilist')

    def _anilist_query(self, query, variables=None):
        """
        Execute a GraphQL query against the AniList API. Handles token refresh and error logging.
        Returns the parsed JSON response or None on error.
        """
        import xbmc
        xbmc.log(f"AniList query: {query}", xbmc.LOGWARNING)
        xbmc.log(f"AniList variables: {variables}", xbmc.LOGWARNING)
        if not ADDON.getSettingBool('anilist_enabled'):
            return None

        headers = {'Content-Type': 'application/json'}
        token = self._get_anilist_token()

        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            resp = requests.post(
                ANILIST_API,
                json={'query': query, 'variables': variables or {}},
                headers=headers,
                timeout=10
            )

            if resp.status_code == 400:
                import xbmc
                xbmc.log(f"AniList 400 response: {resp.text}", xbmc.LOGERROR)
                # If a token is set, try again without the token
                if 'Authorization' in headers:
                    headers_no_token = {'Content-Type': 'application/json'}
                    resp2 = requests.post(
                        ANILIST_API,
                        json={'query': query, 'variables': variables or {}},
                        headers=headers_no_token,
                        timeout=10
                    )
                    if resp2.status_code == 200:
                        return resp2.json()
                    xbmc.log(f"AniList 400 response without token: {resp2.text}", xbmc.LOGERROR)

            if resp.status_code == 401:
                self._log("AniList token expired, refreshing", xbmc.LOGINFO)
                if self._refresh_anilist_token():
                    token = self._get_anilist_token()
                    headers['Authorization'] = f'Bearer {token}'
                    resp = requests.post(
                        ANILIST_API,
                        json={'query': query, 'variables': variables or {}},
                        headers=headers,
                        timeout=10
                    )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self._log(f"AniList API error: {e}", xbmc.LOGERROR)
            return None

    # MyAnimeList API methods

    def _get_mal_token(self):
        """
        Get MyAnimeList token from settings. Returns the token string or an empty string if not set.
        """
        try:
            return ADDON.getSetting('mal_token')
        except Exception:
            return ''

    def _refresh_mal_token(self):
        """
        Refresh MyAnimeList token using the refresh_token utility.
        """
        return refresh_token('mal')

    def _mal_request(self, url, method='GET', **kwargs):
        """
        Make a request to the MyAnimeList API. Handles token refresh and error logging.
        Returns the response object or None on error.
        """
        if not ADDON.getSettingBool('mal_enabled'):
            return None

        headers = kwargs.pop('headers', {})
        token = self._get_mal_token()

        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            resp = requests.request(method, url, headers=headers, **kwargs)

            if resp.status_code == 401:
                self._log("MAL token expired, refreshing", xbmc.LOGINFO)
                if self._refresh_mal_token():
                    token = self._get_mal_token()
                    headers['Authorization'] = f'Bearer {token}'
                    resp = requests.request(method, url, headers=headers, **kwargs)

            resp.raise_for_status()
            return resp

        except Exception as e:
            self._log(f"MAL API error: {e}", xbmc.LOGERROR)
            return None

    # Trakt API methods

    def _get_trakt_token(self):
        """
        Get Trakt token from settings. Returns the token string or an empty string if not set.
        """
        try:
            return ADDON.getSetting('trakt_token')
        except Exception:
            return ''

    def _refresh_trakt_token(self):
        """
        Refresh Trakt token using the refresh_token utility.
        """
        return refresh_token('trakt')

    def _trakt_request(self, url, method='GET', **kwargs):
        """
        Make a request to the Trakt API. Handles token refresh and error logging.
        Returns the response object or None on error.
        """
        if not ADDON.getSettingBool('trakt_enabled'):
            return None

        headers = kwargs.pop('headers', {})
        token = self._get_trakt_token()

        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['trakt-api-version'] = '2'
            headers['trakt-api-key'] = ADDON.getSetting('trakt_client_id')

        try:
            resp = requests.request(method, url, headers=headers, **kwargs)

            if resp.status_code == 401:
                self._log("Trakt token expired, refreshing", xbmc.LOGINFO)
                if self._refresh_trakt_token():
                    token = self._get_trakt_token()
                    headers['Authorization'] = f'Bearer {token}'
                    resp = requests.request(method, url, headers=headers, **kwargs)

            resp.raise_for_status()
            return resp

        except Exception as e:
            self._log(f"Trakt API error: {e}", xbmc.LOGERROR)
            return None

    # Watchlist methods

    def anilist_watchlist(self):
        """
        Fetch user's AniList anime watchlist (status: CURRENT/PLANNING). Returns a list of anime dicts.
        """
        def _fetch():
            query = '''
            query ($status: [MediaListStatus], $page: Int, $perPage: Int) {
              Page(page: $page, perPage: $perPage) {
                mediaList(userName: null, type: ANIME, status_in: $status) {
                  media {
                    id title { romaji english } type
                  }
                }
              }
            }'''

            data = self._anilist_query(query, {
                'status': ['CURRENT', 'PLANNING'],
                'page': 1,
                'perPage': int(ADDON.getSetting('items_per_page'))
            })

            if not data:
                return []

            return [
                {
                    'id': str(m['media']['id']),
                    'title': m['media']['title'].get('english') or m['media']['title'].get('romaji', ''),
                    'type': m['media'].get('type', 'ANIME'),
                    'source': 'anilist'
                } for m in data.get('data', {}).get('Page', {}).get('mediaList', [])
            ]

        return cached('anilist_watchlist', _fetch)

    def mal_watchlist(self):
        """
        Fetch user's MAL anime watchlist (status: watching/plan_to_watch). Returns a list of anime dicts.
        """
        def _fetch():
            resp = self._mal_request(
                f"{MAL_API}/users/@me/animelist?status=watching,plan_to_watch&limit={ADDON.getSetting('items_per_page')}"
            )

            if not resp:
                return []

            data = resp.json()

            return [
                {
                    'id': str(a['node']['id']),
                    'title': a['node']['title'],
                    'type': 'ANIME',
                    'source': 'mal'
                } for a in data.get('data', [])
            ]

        return cached('mal_watchlist', _fetch)

    def trakt_watchlist(self):
        """
        Fetch user's Trakt anime watchlist (type: shows, filter by anime genre if desired). Returns a list of anime dicts.
        """
        def _fetch():
            resp = self._trakt_request(f"{TRAKT_API}/users/me/watchlist/shows")

            if not resp:
                return []

            data = resp.json()

            return [
                {
                    'id': str(a['show']['ids'].get('trakt', '')),
                    'title': a['show'].get('title', ''),
                    'type': 'SHOW',
                    'source': 'trakt'
                } for a in data if a.get('show')
            ]

        return cached('trakt_watchlist', _fetch)

    def watchlist(self):
        """
        Fetch combined watchlist from all enabled services. Returns a list of anime dicts.
        """
        items = []

        if ADDON.getSettingBool('anilist_enabled'):
            items.extend(self.anilist_watchlist())

        if ADDON.getSettingBool('mal_enabled'):
            items.extend(self.mal_watchlist())

        if ADDON.getSettingBool('trakt_enabled'):
            items.extend(self.trakt_watchlist())

        return items

    # Trending anime

    def trending(self):
        """
        Fetch trending anime from AniList. Returns a list of anime dicts.
        """
        def _fetch():
            query = '''
            query ($page: Int, $perPage: Int) {
              Page(page: $page, perPage: $perPage) {
                media(type: ANIME, sort: TRENDING_DESC) {
                  id title { romaji english } description averageScore genres coverImage { large medium } bannerImage
                }
              }
            }'''

            data = self._anilist_query(query, {
                'page': 1,
                'perPage': int(ADDON.getSetting('items_per_page'))
            })

            if not data:
                return []

            return [
                {
                    'id': str(m['id']),
                    'title': m['title'].get('english') or m['title'].get('romaji', ''),
                    'description': m.get('description', ''),
                    'score': m.get('averageScore', 0),
                    'genres': m.get('genres', []),
                    'poster': m.get('coverImage', {}).get('extraLarge') or m.get('coverImage', {}).get('large') or m.get('coverImage', {}).get('medium', ''),
                    'banner': m.get('bannerImage', ''),
                    'source': 'anilist'
                } for m in data.get('data', {}).get('Page', {}).get('media', [])
            ]

        return cached('trending', _fetch)

    # Seasonal anime

    def seasonal(self):
        """
        Fetch seasonal anime from AniList. Returns a list of anime dicts.
        """
        def _fetch():
            # Get current season/year
            now = datetime.now()
            month = now.month

            if month in [12, 1, 2]:
                season = 'WINTER'
            elif month in [3, 4, 5]:
                season = 'SPRING'
            elif month in [6, 7, 8]:
                season = 'SUMMER'
            else:
                season = 'FALL'

            year = now.year if month != 12 else now.year + 1

            query = '''
            query ($season: MediaSeason, $seasonYear: Int, $page: Int, $perPage: Int) {
              Page(page: $page, perPage: $perPage) {
                media(type: ANIME, season: $season, seasonYear: $seasonYear, sort: POPULARITY_DESC) {
                  id title { romaji english } description averageScore genres coverImage { large medium } bannerImage
                }
              }
            }'''

            data = self._anilist_query(query, {
                'season': season,
                'seasonYear': year,
                'page': 1,
                'perPage': int(ADDON.getSetting('items_per_page'))
            })

            if not data:
                return []

            return [
                {
                    'id': str(m['id']),
                    'title': m['title'].get('english') or m['title'].get('romaji', ''),
                    'description': m.get('description', ''),
                    'score': m.get('averageScore', 0),
                    'genres': m.get('genres', []),
                    'poster': m.get('coverImage', {}).get('extraLarge') or m.get('coverImage', {}).get('large') or m.get('coverImage', {}).get('medium', ''),
                    'banner': m.get('bannerImage', ''),
                    'source': 'anilist'
                } for m in data.get('data', {}).get('Page', {}).get('media', [])
            ]

        return cached('seasonal', _fetch)

    # Genres

    def genres(self):
        """
        Fetch anime genres from AniList. Returns a list of genre strings.
        """
        def _fetch():
            query = '''
            query { GenreCollection }'''

            data = self._anilist_query(query)

            if not data:
                return ['Action', 'Adventure', 'Comedy', 'Drama', 'Fantasy', 'Romance', 'Sci-Fi', 'Slice of Life']

            return data.get('data', {}).get('GenreCollection', [])

        return cached('genres', _fetch)

    def genre(self, genre_name):
        """
        Fetch anime by genre from AniList. Returns a list of anime dicts.
        """
        def _fetch():
            query = '''
            query ($genre: String, $page: Int, $perPage: Int) {
              Page(page: $page, perPage: $perPage) {
                media(type: ANIME, genre_in: [$genre], sort: POPULARITY_DESC) {
                  id title { romaji english } description averageScore genres coverImage { large medium } bannerImage
                }
              }
            }'''

            data = self._anilist_query(query, {
                'genre': genre_name,
                'page': 1,
                'perPage': int(ADDON.getSetting('items_per_page'))
            })

            if not data:
                return []

            return [
                {
                    'id': str(m['id']),
                    'title': m['title'].get('english') or m['title'].get('romaji', ''),
                    'description': m.get('description', ''),
                    'score': m.get('averageScore', 0),
                    'genres': m.get('genres', []),
                    'poster': m.get('coverImage', {}).get('extraLarge') or m.get('coverImage', {}).get('large') or m.get('coverImage', {}).get('medium', ''),
                    'banner': m.get('bannerImage', ''),
                    'source': 'anilist'
                } for m in data.get('data', {}).get('Page', {}).get('media', [])
            ]

        return cached(f'genre_{genre_name}', _fetch)

    # Search

    def search(self, term):
        """
        Search for anime on AniList by term. Returns a list of anime dicts.
        """
        def _fetch():
            query = '''
            query ($search: String, $page: Int, $perPage: Int) {
              Page(page: $page, perPage: $perPage) {
                media(type: ANIME, search: $search, sort: SEARCH_MATCH) {
                  id title { romaji english } description averageScore genres coverImage { large medium } bannerImage
                }
              }
            }'''

            data = self._anilist_query(query, {
                'search': term,
                'page': 1,
                'perPage': int(ADDON.getSetting('items_per_page'))
            })

            if not data:
                return []

            return [
                {
                    'id': str(m['id']),
                    'title': m['title'].get('english') or m['title'].get('romaji', ''),
                    'description': m.get('description', ''),
                    'score': m.get('averageScore', 0),
                    'genres': m.get('genres', []),
                    'poster': m.get('coverImage', {}).get('extraLarge') or m.get('coverImage', {}).get('large') or m.get('coverImage', {}).get('medium', ''),
                    'banner': m.get('bannerImage', ''),
                    'source': 'anilist'
                } for m in data.get('data', {}).get('Page', {}).get('media', [])
            ]

        # Don't cache search results
        return _fetch()

    # Anime details

    def anime_details(self, anime_id, source='anilist'):
        """
        Fetch anime details from the specified source (anilist, mal, or trakt). Returns a dict or None.
        """
        if source == 'anilist':
            return self._anilist_anime_details(anime_id)
        elif source == 'mal':
            return self._mal_anime_details(anime_id)
        elif source == 'trakt':
            return self._trakt_anime_details(anime_id)
        else:
            return None

    def _anilist_anime_details(self, anime_id):
        """
        Fetch anime details from AniList for a given anime_id. Returns a dict or None.
        """
        def _fetch():
            query = '''
            query ($id: Int) {
              Media(id: $id, type: ANIME) {
                id
                title { romaji english native }
                description
                format
                status
                episodes
                duration
                genres
                tags { name }
                averageScore
                popularity
                startDate { year month day }
                endDate { year month day }
                season
                seasonYear
                coverImage { large medium }
                bannerImage
                studios { nodes { name } }
                externalLinks { url site }
                nextAiringEpisode { airingAt episode }
              }
            }'''

            data = self._anilist_query(query, {'id': int(anime_id)})

            if not data or 'errors' in data:
                return None

            media = data.get('data', {}).get('Media', {})

            return {
                'id': str(media.get('id', '')),
                'title': media.get('title', {}).get('english') or media.get('title', {}).get('romaji', ''),
                'original_title': media.get('title', {}).get('native', ''),
                'description': media.get('description', ''),
                'format': media.get('format', ''),
                'status': media.get('status', ''),
                'episodes': media.get('episodes', 0),
                'duration': media.get('duration', 0),
                'genres': media.get('genres', []),
                'tags': [tag.get('name', '') for tag in media.get('tags', [])],
                'score': media.get('averageScore', 0),
                'popularity': media.get('popularity', 0),
                'start_date': self._format_date(media.get('startDate', {})),
                'end_date': self._format_date(media.get('endDate', {})),
                'season': media.get('season', ''),
                'season_year': media.get('seasonYear', 0),
                'poster': media.get('coverImage', {}).get('extraLarge') or media.get('coverImage', {}).get('large') or media.get('coverImage', {}).get('medium', ''),
                'banner': media.get('bannerImage', ''),
                'studios': [studio.get('name', '') for studio in media.get('studios', {}).get('nodes', [])],
                'external_links': media.get('externalLinks', []),
                'next_episode': {
                    'airing_at': media.get('nextAiringEpisode', {}).get('airingAt', 0),
                    'episode': media.get('nextAiringEpisode', {}).get('episode', 0)
                } if media.get('nextAiringEpisode') else None,
                'source': 'anilist'
            }

        return cached(f'anilist_anime_{anime_id}', _fetch)

    def _mal_anime_details(self, anime_id):
        """
        Fetch anime details from MyAnimeList for a given anime_id. Returns a dict or None.
        """
        def _fetch():
            resp = self._mal_request(
                f"{MAL_API}/anime/{anime_id}?fields=id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,num_list_users,num_scoring_users,nsfw,created_at,updated_at,media_type,status,genres,my_list_status,num_episodes,start_season,broadcast,source,average_episode_duration,rating,pictures,background,related_anime,related_manga,recommendations,studios,statistics"
            )

            if not resp:
                return None

            data = resp.json()

            return {
                'id': str(data.get('id', '')),
                'title': data.get('title', ''),
                'original_title': data.get('alternative_titles', {}).get('ja', ''),
                'description': data.get('synopsis', ''),
                'format': data.get('media_type', ''),
                'status': data.get('status', ''),
                'episodes': data.get('num_episodes', 0),
                'duration': data.get('average_episode_duration', 0) // 60,  # Convert seconds to minutes
                'genres': [g.get('name', '') for g in data.get('genres', [])],
                'tags': [],
                'score': data.get('mean', 0),
                'popularity': data.get('popularity', 0),
                'start_date': data.get('start_date', ''),
                'end_date': data.get('end_date', ''),
                'season': data.get('start_season', {}).get('season', ''),
                'season_year': data.get('start_season', {}).get('year', 0),
                'poster': data.get('main_picture', {}).get('large', '') or data.get('main_picture', {}).get('medium', ''),
                'banner': '',
                'studios': [s.get('name', '') for s in data.get('studios', [])],
                'external_links': [],
                'source': 'mal'
            }

        return cached(f'mal_anime_{anime_id}', _fetch)

    def _trakt_anime_details(self, anime_id):
        """
        Fetch anime details from Trakt for a given anime_id. Returns a dict or None.
        """
        def _fetch():
            resp = self._trakt_request(
                f"{TRAKT_API}/shows/{anime_id}?extended=full"
            )

            if not resp:
                return None

            data = resp.json()

            return {
                'id': str(data.get('ids', {}).get('trakt', '')),
                'title': data.get('title', ''),
                'original_title': '',
                'description': data.get('overview', ''),
                'format': '',
                'status': data.get('status', ''),
                'episodes': 0,  # Need to fetch seasons/episodes separately
                'duration': data.get('runtime', 0),
                'genres': data.get('genres', []),
                'tags': [],
                'score': data.get('rating', 0),
                'popularity': 0,
                'start_date': data.get('first_aired', ''),
                'end_date': '',
                'season': '',
                'season_year': 0,
                'poster': '',  # Need to fetch images separately
                'banner': '',
                'studios': [data.get('network', '')],
                'external_links': [],
                'source': 'trakt'
            }

        return cached(f'trakt_anime_{anime_id}', _fetch)

    # Helper methods

    def _format_date(self, date_obj):
        """
        Format a date object from AniList (dict with year, month, day) as YYYY-MM-DD string.
        Returns an empty string if year is missing.
        """
        if not date_obj or not date_obj.get('year'):
            return ''

        year = date_obj.get('year', 0)
        month = date_obj.get('month', 1)
        day = date_obj.get('day', 1)

        try:
            return datetime(year, month, day).strftime('%Y-%m-%d')
        except:
            return f"{year}-{month:02d}-{day:02d}"
