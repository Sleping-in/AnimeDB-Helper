"""
AnimeDBAPI: Unified API interface for anime metadata, watchlists, and details from AniList, MyAnimeList, and Trakt.

This module provides a single class, AnimeDBAPI, which abstracts access to multiple anime metadata providers and user lists.
It handles authentication, caching, and error handling for each service, and exposes unified methods for fetching anime details,
watchlists, trending/seasonal anime, genres, and search results.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, TypeVar, Union, Callable, Tuple

import requests

try:
    import xbmc
    import xbmcaddon
    import xbmcvfs
    import xbmcgui
    import xbmcplugin
except ImportError:
    from resources.lib import xbmc, xbmcaddon, xbmcvfs, xbmcgui, xbmcplugin

from resources.lib.auth_utils import refresh_token

# Type variables
T = TypeVar('T')

# Cache expiration times in seconds
CACHE_TTL = {
    'episodes': 3600,  # 1 hour
    'genres': 86400,   # 24 hours
    'search': 1800,    # 30 minutes
    'details': 86400,  # 24 hours
    'default': 3600    # 1 hour
}

# API endpoints
ANILIST_API = 'https://graphql.anilist.co'
MAL_API = 'https://api.myanimelist.net/v2'
TRAKT_API = 'https://api.trakt.tv'

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Setup cache directory
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
CACHE_DIR = os.path.join(PROFILE, 'cache')
if not xbmcvfs.exists(CACHE_DIR):
    xbmcvfs.mkdirs(CACHE_DIR)

def cache_key_generator(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from function arguments."""
    key = f"{prefix}_{json.dumps(args, sort_keys=True)}_{json.dumps(kwargs, sort_keys=True)}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()

def cached(cache_type: str = 'default'):
    """Decorator to cache function results with TTL."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> T:
            if not hasattr(self, 'cache_enabled') or not self.cache_enabled:
                return func(self, *args, **kwargs)
                
            cache_key = cache_key_generator(func.__name__, *args, **kwargs)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
            
            # Try to load from cache
            if xbmcvfs.exists(cache_file):
                try:
                    with xbmcvfs.File(cache_file, 'r') as f:
                        cached_data = json.loads(f.read())
                    
                    # Check if cache is still valid
                    cache_time = datetime.fromisoformat(cached_data['timestamp'])
                    if (datetime.now() - cache_time).total_seconds() < CACHE_TTL.get(cache_type, CACHE_TTL['default']):
                        self._log(f"Cache hit for {func.__name__}: {cache_key}")
                        return cached_data['data']
                except Exception as e:
                    self._log(f"Cache read error for {cache_key}: {str(e)}", xbmc.LOGWARNING)
            
            # Call the function and cache the result
            result = func(self, *args, **kwargs)
            
            try:
                cache_data = {
                    'timestamp': datetime.now().isoformat(),
                    'data': result
                }
                with xbmcvfs.File(cache_file, 'w') as f:
                    f.write(json.dumps(cache_data, default=str))
            except Exception as e:
                self._log(f"Cache write error for {cache_key}: {str(e)}", xbmc.LOGWARNING)
            
            return result
        return wrapper
    return decorator

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

def clear_all_caches() -> bool:
    """Clear all cached data.
    
    Returns:
        bool: True if cache was cleared successfully, False otherwise
    """
    try:
        if not xbmcvfs.exists(CACHE_DIR):
            return True
            
        _, files = xbmcvfs.listdir(CACHE_DIR)
        success = True
        for filename in files:
            if filename.endswith('.json'):
                try:
                    xbmcvfs.delete(os.path.join(CACHE_DIR, filename))
                except Exception as e:
                    log(f"Error removing cache file {filename}: {e}", xbmc.LOGWARNING)
                    success = False
        return success
    except Exception as e:
        log(f"Error clearing cache: {e}", xbmc.LOGERROR)
        return False

class AnimeDBAPI:
    """Unified API interface for anime metadata, watchlists, and details from AniList, MyAnimeList, and Trakt.

    This class provides methods to fetch anime details, watchlists, trending/seasonal anime, genres, and search results
    from multiple sources. It handles authentication, caching, and error handling for each service.
    
    Attributes:
        debug (bool): Enable debug logging
        cache_enabled (bool): Whether caching is enabled
        cache_dir (str): Directory to store cache files
        anilist_enabled (bool): Whether AniList is enabled
        mal_enabled (bool): Whether MyAnimeList is enabled
        trakt_enabled (bool): Whether Trakt is enabled
    """
    
    def __init__(self):
        """Initialize the API wrapper with settings from Kodi addon."""
        self.addon = xbmcaddon.Addon()
        self.debug = self.addon.getSettingBool('debug_logging')
        self.cache_enabled = self.addon.getSettingBool('enable_cache', True)
        
        # Service enable flags
        self.anilist_enabled = self.addon.getSettingBool('anilist_enabled', True)
        self.mal_enabled = self.addon.getSettingBool('mal_enabled', True)
        self.trakt_enabled = self.addon.getSettingBool('trakt_enabled', True)
        
        # Set up cache directory
        self.cache_dir = os.path.join(xbmcvfs.translatePath('special://temp/'), 'animedb_cache')
        if not xbmcvfs.exists(self.cache_dir):
            xbmcvfs.mkdirs(self.cache_dir)
            
        self._log(f"Initialized AnimeDBAPI (AniList: {'enabled' if self.anilist_enabled else 'disabled'}, "
                f"MAL: {'enabled' if self.mal_enabled else 'disabled'}, "
                f"Trakt: {'enabled' if self.trakt_enabled else 'disabled'}, "
                f"Cache: {'enabled' if self.cache_enabled else 'disabled'})")
    
    def _log(self, message: str, level: int = xbmc.LOGINFO) -> None:
        """Log a message with addon prefix.
        
        Args:
            message: The message to log
            level: The log level (default: xbmc.LOGINFO)
        """
        if self.debug or level >= xbmc.LOGWARNING:
            xbmc.log(f"[AnimeDB] {message}", level=level)
    
    def clear_cache(self) -> bool:
        """Clear all cached data for this instance.
        
        Returns:
            bool: True if cache was cleared successfully, False otherwise
        """
        try:
            if not xbmcvfs.exists(self.cache_dir):
                return True
                
            _, files = xbmcvfs.listdir(self.cache_dir)
            success = True
            for filename in files:
                if filename.endswith('.json'):
                    try:
                        xbmcvfs.delete(os.path.join(self.cache_dir, filename))
                    except Exception as e:
                        self._log(f"Error removing cache file {filename}: {e}", xbmc.LOGWARNING)
                        success = False
            
            if success:
                self._log("Cache cleared successfully")
            return success
            
        except Exception as e:
            self._log(f"Failed to clear cache: {str(e)}", xbmc.LOGERROR)
            return False

    @cached('episodes')
    def anilist_episodes(self, anime_id: int) -> List[Dict[str, Any]]:
        """Fetch episode details from AniList for a given anime ID.
        
        Args:
            anime_id: The AniList anime ID
            
        Returns:
            List[Dict[str, Any]]: List of episode dictionaries containing:
                - number (int): Episode number
                - title (str): Episode title
                - description (str): Episode description
                - thumbnail (str): URL to episode thumbnail
                - air_date (str): ISO format air date
                - duration (int): Episode duration in minutes
        """
        if not self.anilist_enabled:
            self._log("AniList is disabled, cannot fetch episodes", xbmc.LOGWARNING)
            return []
            
        query = '''
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            id
            title { romaji english native }
            description(asHtml: false)
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
        
        try:
            data = self._anilist_query(query, {'id': int(anime_id)})
            if not data or 'errors' in data:
                self._log(f"Error fetching episodes for anime {anime_id}: {data.get('errors', 'Unknown error')}", xbmc.LOGERROR)
                return []
                
            media = data.get('data', {}).get('Media', {})
            if not media:
                self._log(f"No media found for anime ID: {anime_id}", xbmc.LOGWARNING)
                return []
                
            # Extract show-level information
            poster = next((
                media.get('coverImage', {}).get('extraLarge') or 
                media.get('coverImage', {}).get('large') or 
                media.get('coverImage', {}).get('medium', '')
            ), '')
            banner = media.get('bannerImage', '')
            duration = int(media.get('duration', 0))
            show_description = media.get('description', '')
            
            # Map episode air dates by number
            airing_nodes = media.get('airingSchedule', {}).get('nodes', [])
            air_dates = {
                int(n.get('episode', 0)): datetime.fromtimestamp(n.get('airingAt', 0)).isoformat()
                for n in airing_nodes 
                if n and n.get('episode')
            }
            
            # Process streaming episodes
            episodes = []
            streaming_eps = media.get('streamingEpisodes', [])
            for ep in streaming_eps:
                if not ep:
                    continue
                    
                try:
                    num = int(ep.get('episode', 0))
                    if num <= 0:
                        continue
                        
                    episodes.append({
                        'number': num,
                        'title': ep.get('title', f"Episode {num}").strip() or f"Episode {num}",
                        'description': (ep.get('description') or show_description or '').strip(),
                        'thumbnail': ep.get('thumbnail') or poster or banner,
                        'air_date': air_dates.get(num),
                        'duration': duration,
                        'source': 'anilist',
                        'id': f"anilist_{anime_id}_{num}"
                    })
                except (ValueError, TypeError) as e:
                    self._log(f"Error processing streaming episode: {e}", xbmc.LOGWARNING)
            
            # Fill in any missing episodes
            total_eps = int(media.get('episodes', 0)) or len(episodes)
            if total_eps > 0:
                existing_eps = {ep['number'] for ep in episodes}
                for num in range(1, total_eps + 1):
                    if num not in existing_eps:
                        episodes.append({
                            'number': num,
                            'title': f"Episode {num}",
                            'description': show_description.strip() if show_description else '',
                            'thumbnail': poster or banner,
                            'air_date': air_dates.get(num),
                            'duration': duration,
                            'source': 'anilist',
                            'id': f"anilist_{anime_id}_{num}"
                        })
            
            # Sort by episode number
            episodes.sort(key=lambda x: x['number'])
            return episodes
            
        except Exception as e:
            self._log(f"Error in anilist_episodes for ID {anime_id}: {str(e)}", xbmc.LOGERROR)
            return []


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

    def _refresh_anilist_token(self) -> bool:
        """
        Refresh the AniList OAuth token.
        
        Returns:
            bool: True if token was refreshed successfully, False otherwise
        """
        self._log("Refreshing AniList token...", xbmc.LOGDEBUG)
        try:
            from resources.lib.auth_utils import refresh_token
            return bool(refresh_token('anilist'))
        except Exception as e:
            self._log(f"Failed to refresh AniList token: {str(e)}", xbmc.LOGERROR)
            return False

    def _anilist_query(self, query: str, variables: Optional[Dict] = None, 
                     max_retries: int = 3, backoff_factor: float = 0.5) -> Optional[Dict]:
        """Execute a GraphQL query against the AniList API with enhanced error handling and retry logic.
        
        Handles token refresh, rate limiting, network issues, and provides detailed error logging.
        
        Args:
            query: The GraphQL query string
            variables: Dictionary of variables for the query
            max_retries: Maximum number of retry attempts for failed requests
            backoff_factor: Factor for exponential backoff between retries
            
        Returns:
            Dict: Parsed JSON response, or None if the request failed after all retries
            
        Raises:
            requests.HTTPError: For HTTP errors that shouldn't be retried (e.g., 404, 403)
        """
        if variables is None:
            variables = {}
            
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': f'AnimeDB-Helper/{self.addon.getAddonInfo("version")}'
        }
        
        # Add auth header if we have a token
        token = self._get_anilist_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        data = {
            'query': query,
            'variables': variables
        }
        
        attempt = 0
        last_error = None
        last_status = None
        
        while attempt <= max_retries:
            try:
                # Calculate exponential backoff time
                wait_time = backoff_factor * (2 ** attempt) if attempt > 0 else 0
                if wait_time > 0:
                    self._log(f'Waiting {wait_time:.1f}s before attempt {attempt + 1}/{max_retries + 1}...', 
                             xbmc.LOGDEBUG)
                    xbmc.sleep(int(wait_time * 1000))
                
                # Make the request
                response = requests.post(
                    ANILIST_API,
                    headers=headers,
                    json=data,
                    timeout=30
                )
                last_status = response.status_code
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', min(5, 2 ** attempt)))
                    self._log(f'Rate limited. Waiting {retry_after} seconds before retry...', xbmc.LOGWARNING)
                    xbmc.sleep(retry_after * 1000)
                    continue
                    
                # Handle unauthorized (401) - try to refresh token once
                if response.status_code == 401 and attempt == 0:
                    self._log('Authentication failed. Attempting to refresh token...', xbmc.LOGWARNING)
                    if self._refresh_anilist_token():
                        new_token = self._get_anilist_token()
                        if new_token:
                            headers['Authorization'] = f'Bearer {new_token}'
                            attempt += 1
                            continue
                    
                # For client errors (4xx) other than 429/401, don't retry
                if 400 <= response.status_code < 500 and response.status_code not in [401, 429]:
                    response.raise_for_status()
                
                # For server errors (5xx), retry
                if response.status_code >= 500:
                    raise requests.HTTPError(f'Server error: {response.status_code} {response.reason}')
                
                result = response.json()
                
                # Check for GraphQL errors
                if 'errors' in result:
                    error_messages = []
                    for error in result['errors']:
                        msg = error.get('message', 'Unknown error')
                        locations = error.get('locations', [])
                        if locations:
                            loc = locations[0]
                            msg += f' at line {loc.get("line")}, column {loc.get("column")}'
                        error_messages.append(msg)
                    
                    error_msg = '; '.join(error_messages)
                    self._log(f'AniList GraphQL errors: {error_msg}', xbmc.LOGERROR)
                    headers.pop('Authorization', None)
                    attempt += 1
                    if attempt <= max_retries:
                        continue
                    return None
                
                return result
                
            except requests.exceptions.RequestException as e:
                last_error = e
                self._log(f"AniList API request failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}", 
                         xbmc.LOGWARNING)
                
                # Don't retry on client errors (4xx) except 429 (handled above) and 401 (handled above)
                if isinstance(e, requests.exceptions.HTTPError) and 400 <= e.response.status_code < 500:
                    break
                    
                attempt += 1
                if attempt <= max_retries:
                    # Exponential backoff with jitter
                    delay = min(2 ** attempt + (0.1 * attempt), 30)
                    xbmc.sleep(int(delay * 1000))
            except (ValueError, KeyError) as e:
                self._log(f"Error parsing AniList response: {str(e)}", xbmc.LOGERROR)
                last_error = e
                break
            except Exception as e:
                self._log(f"Unexpected error in _anilist_query: {str(e)}", xbmc.LOGERROR)
                last_error = e
                break
        
        self._log(f"Failed to execute AniList query after {attempt} attempts: {str(last_error)}", xbmc.LOGERROR)
        return None

    # MyAnimeList API methods

    def _get_mal_token(self) -> str:
        """Get MyAnimeList OAuth token from settings.
        
        Returns:
            str: The MAL OAuth token, or empty string if not set
        """
        try:
            token = self.addon.getSetting('mal_token')
            return token if token else ''
        except Exception as e:
            self._log(f"Error getting MAL token: {str(e)}", xbmc.LOGWARNING)
            return ''

    def _refresh_mal_token(self) -> bool:
        """Refresh MyAnimeList OAuth token using the refresh_token utility.
        
        Returns:
            bool: True if token was refreshed successfully, False otherwise
        """
        self._log("Refreshing MAL token...", xbmc.LOGDEBUG)
        try:
            return bool(refresh_token('mal'))
        except Exception as e:
            self._log(f"Failed to refresh MAL token: {str(e)}", xbmc.LOGERROR)
            return False

    @cached('details')
    def _mal_request(self, endpoint: str, method: str = 'GET', params: Optional[Dict] = None, 
                    data: Optional[Dict] = None, json_data: Optional[Dict] = None,
                    max_retries: int = 2) -> Optional[Dict]:
        """Make a request to the MyAnimeList API v2.
        
        Handles authentication, rate limiting, and error handling.
        
        Args:
            endpoint: API endpoint (e.g., 'anime/123')
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Form data for POST requests
            json_data: JSON data for POST requests
            max_retries: Maximum number of retry attempts
            
        Returns:
            Optional[Dict]: Parsed JSON response, or None on failure
        """
        if not self.mal_enabled:
            self._log("MyAnimeList is disabled", xbmc.LOGWARNING)
            return None
            
        if not endpoint.startswith(('http://', 'https://')):
            url = f"{MAL_API}/{endpoint.lstrip('/')}"
        else:
            url = endpoint
            
        headers = {
            'Accept': 'application/json',
            'X-MAL-CLIENT-ID': self.addon.getSetting('mal_client_id') or '',
            'User-Agent': f'AnimeDB-Helper/{self.addon.getAddonInfo("version")} (Kodi)'
        }
        
        # Add OAuth token if available
        token = self._get_mal_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        last_error = None
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Make the request
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=headers,
                    timeout=15
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    self._log(f"MAL rate limited. Waiting {retry_after} seconds...", xbmc.LOGWARNING)
                    xbmc.sleep(retry_after * 1000)
                    retry_count += 1
                    continue
                    
                # Handle 401 Unauthorized (token refresh)
                if response.status_code == 401 and 'Authorization' in headers:
                    self._log("MAL token expired, attempting to refresh...", xbmc.LOGINFO)
                    if self._refresh_mal_token():
                        token = self._get_mal_token()
                        if token:
                            headers['Authorization'] = f'Bearer {token}'
                            retry_count += 1
                            continue
                    
                    # If we get here, token refresh failed - try without auth
                    self._log("MAL token refresh failed, trying without authentication", xbmc.LOGWARNING)
                    headers.pop('Authorization', None)
                    retry_count += 1
                    continue
                
                # Check for other errors
                response.raise_for_status()
                
                # Parse and return response
                if response.status_code == 204:  # No Content
                    return {}
                    
                return response.json()
                
            except requests.exceptions.RequestException as e:
                last_error = e
                self._log(
                    f"MAL API request failed (attempt {retry_count + 1}/{max_retries + 1}): {str(e)}", 
                    xbmc.LOGWARNING
                )
                
                # Don't retry on client errors (4xx) except 429 (handled above) and 401 (handled above)
                if isinstance(e, requests.exceptions.HTTPError) and 400 <= e.response.status_code < 500:
                    break
                    
                retry_count += 1
                if retry_count <= max_retries:
                    # Exponential backoff with jitter
                    delay = min(2 ** retry_count + (0.1 * retry_count), 30)
                    xbmc.sleep(int(delay * 1000))
                    
            except (ValueError, json.JSONDecodeError) as e:
                self._log(f"Error parsing MAL response: {str(e)}", xbmc.LOGERROR)
                last_error = e
                break
                
            except Exception as e:
                self._log(f"Unexpected error in _mal_request: {str(e)}", xbmc.LOGERROR)
                last_error = e
                break
        
        self._log(
            f"Failed to execute MAL request to {endpoint} after {retry_count} attempts: {str(last_error)}", 
            xbmc.LOGERROR
        )
        return None

    # Trakt API methods

    def _get_trakt_token(self) -> str:
        """Get Trakt OAuth token from settings.
        
        Returns:
            str: The Trakt OAuth token, or empty string if not set
        """
        try:
            token = self.addon.getSetting('trakt_token')
            return token if token else ''
        except Exception as e:
            self._log(f"Error getting Trakt token: {str(e)}", xbmc.LOGWARNING)
            return ''

    def _refresh_trakt_token(self) -> bool:
        """Refresh Trakt OAuth token using the refresh_token utility.
        
        Returns:
            bool: True if token was refreshed successfully, False otherwise
        """
        self._log("Refreshing Trakt token...", xbmc.LOGDEBUG)
        try:
            return bool(refresh_token('trakt'))
        except Exception as e:
            self._log(f"Failed to refresh Trakt token: {str(e)}", xbmc.LOGERROR)
            return False

    @cached('details')
    def _trakt_request(self, endpoint: str, method: str = 'GET', params: Optional[Dict] = None, 
                      data: Optional[Dict] = None, json_data: Optional[Dict] = None,
                      max_retries: int = 2) -> Optional[Dict]:
        """Make a request to the Trakt API.
        
        Handles authentication, rate limiting, and error handling.
        
        Args:
            endpoint: API endpoint (e.g., 'users/me/watchlist/shows')
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Form data for POST requests
            json_data: JSON data for POST requests
            max_retries: Maximum number of retry attempts
            
        Returns:
            Optional[Dict]: Parsed JSON response, or None on failure
        """
        if not self.trakt_enabled:
            self._log("Trakt is disabled", xbmc.LOGWARNING)
            return None
            
        if not endpoint.startswith(('http://', 'https://')):
            url = f"{TRAKT_API}/{endpoint.lstrip('/')}"
        else:
            url = endpoint
            
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': self.addon.getSetting('trakt_client_id') or '',
            'User-Agent': f'AnimeDB-Helper/{self.addon.getAddonInfo("version")} (Kodi)'
        }
        
        # Add OAuth token if available
        token = self._get_trakt_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        last_error = None
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Make the request
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    data=json.dumps(data) if data else None,
                    json=json_data,
                    headers=headers,
                    timeout=15
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    self._log(f"Trakt rate limited. Waiting {retry_after} seconds...", xbmc.LOGWARNING)
                    xbmc.sleep(retry_after * 1000)
                    retry_count += 1
                    continue
                    
                # Handle 401 Unauthorized (token refresh)
                if response.status_code == 401 and 'Authorization' in headers:
                    self._log("Trakt token expired, attempting to refresh...", xbmc.LOGINFO)
                    if self._refresh_trakt_token():
                        token = self._get_trakt_token()
                        if token:
                            headers['Authorization'] = f'Bearer {token}'
                            retry_count += 1
                            continue
                    
                    # If we get here, token refresh failed - try without auth
                    self._log("Trakt token refresh failed, trying without authentication", xbmc.LOGWARNING)
                    headers.pop('Authorization', None)
                    retry_count += 1
                    continue
                
                # Check for other errors
                response.raise_for_status()
                
                # Parse and return response
                if response.status_code == 204:  # No Content
                    return {}
                    
                return response.json()
                
            except requests.exceptions.RequestException as e:
                last_error = e
                self._log(
                    f"Trakt API request failed (attempt {retry_count + 1}/{max_retries + 1}): {str(e)}", 
                    xbmc.LOGWARNING
                )
                
                # Don't retry on client errors (4xx) except 429 (handled above) and 401 (handled above)
                if isinstance(e, requests.exceptions.HTTPError) and 400 <= e.response.status_code < 500:
                    break
                    
                retry_count += 1
                if retry_count <= max_retries:
                    # Exponential backoff with jitter
                    delay = min(2 ** retry_count + (0.1 * retry_count), 30)
                    xbmc.sleep(int(delay * 1000))
                    
            except (ValueError, json.JSONDecodeError) as e:
                self._log(f"Error parsing Trakt response: {str(e)}", xbmc.LOGERROR)
                last_error = e
                break
                
            except Exception as e:
                self._log(f"Unexpected error in _trakt_request: {str(e)}", xbmc.LOGERROR)
                last_error = e
                break
        
        self._log(
            f"Failed to execute Trakt request to {endpoint} after {retry_count} attempts: {str(last_error)}", 
            xbmc.LOGERROR
        )
        return None

    # Watchlist methods

    @cached('watchlist')
    def anilist_watchlist(self, page: int = 1, per_page: int = 100) -> List[Dict[str, Any]]:
        """Fetch user's AniList anime watchlist (status: CURRENT/PLANNING).
        
        Args:
            page: Page number to fetch (1-based)
            per_page: Number of items per page
            
        Returns:
            List[Dict[str, Any]]: List of anime dictionaries containing:
                - id (str): AniList anime ID
                - title (str): Anime title (English or Romaji)
                - type (str): Media type (always 'ANIME')
                - source (str): Source identifier ('anilist')
        """
        if not self.anilist_enabled:
            return []
            
        query = '''
        query ($status: [MediaListStatus], $page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            pageInfo { hasNextPage }
            mediaList(userName: null, type: ANIME, status_in: $status, sort: UPDATED_TIME_DESC) {
              media {
                id
                title { romaji english native }
                type
                format
                status
                episodes
                duration
                averageScore
                coverImage { large medium }
                bannerImage
              }
              progress
              progressVolumes
              status
              score
              repeat
              private
              notes
              hiddenFromStatusLists
              startedAt { year month day }
              completedAt { year month day }
              updatedAt
              createdAt
            }
          }
        }'''

        data = self._anilist_query(query, {
            'status': ['CURRENT', 'PLANNING', 'REPEATING'],
            'page': page,
            'perPage': per_page
        })

        if not data:
            return []
            
        result = data.get('data', {}).get('Page', {})
        media_list = result.get('mediaList', [])
        
        return [
            {
                'id': str(m['media']['id']),
                'title': m['media']['title'].get('english') or m['media']['title'].get('romaji', ''),
                'type': m['media'].get('type', 'ANIME'),
                'format': m['media'].get('format'),
                'status': m['media'].get('status'),
                'episodes': m['media'].get('episodes'),
                'duration': m['media'].get('duration'),
                'score': m['media'].get('averageScore'),
                'poster': m['media'].get('coverImage', {}).get('large') or m['media'].get('coverImage', {}).get('medium', ''),
                'banner': m['media'].get('bannerImage', ''),
                'progress': m.get('progress'),
                'list_status': m.get('status'),
                'user_score': m.get('score'),
                'is_rewatching': m.get('repeat', 0) > 0,
                'updated_at': m.get('updatedAt'),
                'source': 'anilist'
            } for m in media_list if m.get('media')
        ]

    @cached('watchlist', ttl=300)  # Cache for 5 minutes
    def mal_watchlist(self, status: str = 'watching,plan_to_watch', 
                     limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch user's MAL anime watchlist.
        
        Args:
            status: Comma-separated list of statuses (watching, plan_to_watch, etc.)
            limit: Maximum number of items to return (max 1000 according to MAL API)
            offset: Pagination offset
            
        Returns:
            List[Dict[str, Any]]: List of anime dictionaries
        """
        if not self.mal_enabled:
            return []
            
        data = self._mal_request(
            'users/@me/animelist',
            params={
                'status': status,
                'limit': min(limit, 1000),  # MAL has a max limit of 1000
                'offset': offset,
                'fields': 'list_status,media_type,status,my_list_status{num_episodes_watched,score,status,updated_at}',
                'nsfw': 'true' if self.addon.getSettingBool('show_nsfw') else 'false'
            }
        )
        
        if not data or 'data' not in data:
            return []
            
        return [
            {
                'id': str(item['node']['id']),
                'title': item['node'].get('title', ''),
                'type': 'ANIME',
                'episodes': item['node'].get('num_episodes'),
                'status': item['node'].get('status', '').upper(),
                'score': item['node'].get('mean'),
                'poster': item['node'].get('main_picture', {}).get('large', '')
                              or item['node'].get('main_picture', {}).get('medium', ''),
                'progress': item.get('list_status', {}).get('num_episodes_watched', 0),
                'list_status': item.get('list_status', {}).get('status', ''),
                'user_score': item.get('list_status', {}).get('score', 0),
                'updated_at': item.get('list_status', {}).get('updated_at', ''),
                'source': 'mal'
            } for item in data.get('data', []) if item.get('node')
        ]

    @cached('watchlist', ttl=300)  # Cache for 5 minutes
    def trakt_watchlist(self, item_type: str = 'shows', limit: int = 100, page: int = 1) -> List[Dict[str, Any]]:
        """Fetch user's Trakt watchlist.
        
        Args:
            item_type: Type of items to fetch ('shows', 'movies', 'seasons', 'episodes')
            limit: Number of items per page (1-1000)
            page: Page number
            
        Returns:
            List[Dict[str, Any]]: List of watchlist items
        """
        if not self.trakt_enabled:
            return []
            
        data = self._trakt_request(
            f'users/me/watchlist/{item_type}',
            params={
                'extended': 'full',
                'limit': min(max(1, limit), 1000),  # Ensure between 1-1000
                'page': max(1, page)
            }
        )
        
        if not data:
            return []
            
        return [
            {
                'id': str(item['show']['ids'].get('trakt', '')),
                'trakt_id': item['show']['ids'].get('trakt'),
                'imdb_id': item['show']['ids'].get('imdb', ''),
                'tmdb_id': item['show']['ids'].get('tmdb'),
                'tvdb_id': item['show']['ids'].get('tvdb'),
                'title': item['show'].get('title', ''),
                'year': item['show'].get('year'),
                'type': 'SHOW',
                'status': item['show'].get('status', '').upper(),
                'episodes': item['show'].get('episode_count'),
                'score': item['show'].get('rating'),
                'poster': next(
                    (image['url'] for image in item['show'].get('images', {}).get('poster', []) 
                     if image.get('url') and 'thumb' not in image.get('url', '')),
                    ''
                ),
                'banner': next(
                    (image['url'] for image in item['show'].get('images', {}).get('banner', []) 
                     if image.get('url')),
                    ''
                ),
                'fanart': next(
                    (image['url'] for image in item['show'].get('images', {}).get('fanart', []) 
                     if image.get('url')),
                    ''
                ),
                'listed_at': item.get('listed_at', ''),
                'source': 'trakt'
            } for item in data if item.get('show')
        ]

    def watchlist(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch combined watchlist from all enabled services.
        
        Args:
            source: Optional source to filter by ('anilist', 'mal', 'trakt')
            
        Returns:
            List[Dict[str, Any]]: Combined list of watchlist items
        """
        items = []
        
        # Get from all enabled sources if none specified
        sources = [source] if source else ['anilist', 'mal', 'trakt']
        
        if 'anilist' in sources and self.anilist_enabled:
            try:
                items.extend(self.anilist_watchlist())
            except Exception as e:
                self._log(f"Error fetching AniList watchlist: {str(e)}", xbmc.LOGERROR)
        
        if 'mal' in sources and self.mal_enabled:
            try:
                items.extend(self.mal_watchlist())
            except Exception as e:
                self._log(f"Error fetching MAL watchlist: {str(e)}", xbmc.LOGERROR)
        
        if 'trakt' in sources and self.trakt_enabled:
            try:
                items.extend(self.trakt_watchlist())
            except Exception as e:
                self._log(f"Error fetching Trakt watchlist: {str(e)}", xbmc.LOGERROR)
        
        # Sort by title for consistent ordering
        return sorted(items, key=lambda x: x.get('title', '').lower())

    # Trending and Popular anime

    @cached('trending', ttl=3600)  # Cache for 1 hour
    def get_trending_anime(self, page: int = 1, per_page: int = 20, source: str = 'anilist') -> List[Dict[str, Any]]:
        """Fetch trending/popular anime from the specified source.
        
        Args:
            page: Page number (1-based)
            per_page: Number of items per page (max 50 for most APIs)
            source: Data source ('anilist', 'mal', or 'trakt')
            
        Returns:
            List[Dict[str, Any]]: List of trending anime with details
        """
        if source == 'anilist' and self.anilist_enabled:
            return self._get_anilist_trending(page, per_page)
        elif source == 'mal' and self.mal_enabled:
            return self._get_mal_trending(page, per_page)
        elif source == 'trakt' and self.trakt_enabled:
            return self._get_trakt_trending(page, per_page)
        else:
            self._log(f"Trending anime not available from {source} or service is disabled", xbmc.LOGWARNING)
            return []

    def _get_anilist_trending(self, page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        """Fetch trending anime from AniList."""
        query = '''
        query ($page: Int, $perPage: Int, $type: MediaType) {
          Page(page: $page, perPage: $perPage) {
            pageInfo {
              total
              perPage
              currentPage
              lastPage
              hasNextPage
            }
            media(type: $type, sort: TRENDING_DESC, status: RELEASING) {
              id
              idMal
              title {
                romaji
                english
                native
                userPreferred
              }
              type
              format
              status
              description(asHtml: false)
              startDate { year month day }
              endDate { year month day }
              season
              seasonYear
              episodes
              duration
              chapters
              volumes
              source
              hashtag
              isLicensed
              isAdult
              averageScore
              meanScore
              popularity
              favourites
              genres
              synonyms
              studios(isMain: true) {
                nodes { id name siteUrl }
              }
              coverImage {
                extraLarge
                large
                medium
                color
              }
              bannerImage
              nextAiringEpisode {
                airingAt
                timeUntilAiring
                episode
              }
              trailer {
                id
                site
                thumbnail
              }
              externalLinks {
                url
                site
              }
              rankings {
                rank
                type
                allTime
                season
                year
              }
              tags {
                name
                description
                category
                rank
                isGeneralSpoiler
                isMediaSpoiler
                isAdult
              }
            }
          }
        }'''

        data = self._anilist_query(query, {
            'page': page,
            'perPage': min(50, per_page),  # AniList max per_page is 50
            'type': 'ANIME'
        })

        if not data:
            return []

        media_list = data.get('data', {}).get('Page', {}).get('media', [])
        
        return [self._format_anilist_media(m) for m in media_list if m]

    def _get_mal_trending(self, page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        """Fetch trending anime from MyAnimeList."""
        data = self._mal_request(
            'anime/ranking',
            params={
                'ranking_type': 'airing',
                'limit': min(100, per_page),  # MAL max limit is 100
                'offset': (page - 1) * per_page,
                'fields': 'id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,num_list_users,num_scoring_users,nsfw,genres,media_type,status,num_episodes,start_season,broadcast,source,average_episode_duration,rating,pictures,background,related_anime,related_manga,recommendations,studios,statistics',
                'nsfw': 'true' if self.addon.getSettingBool('show_nsfw') else 'false'
            }
        )
        
        if not data or 'data' not in data:
            return []
            
        return [self._format_mal_anime(item['node']) for item in data.get('data', []) if item.get('node')]

    def _get_trakt_trending(self, page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        """Fetch trending anime from Trakt."""
        data = self._trakt_request(
            'shows/trending',
            params={
                'extended': 'full',
                'limit': min(100, per_page),  # Trakt max limit is 100
                'page': page,
                'genres': 'anime',
                'years': f"{datetime.now().year-1}-{datetime.now().year}"
            }
        )
        
        if not data:
            return []
            
        return [self._format_trakt_show(item['show']) for item in data if item.get('show')]

    # Seasonal anime methods

    @cached('seasonal', ttl=86400)  # Cache for 24 hours
    def get_seasonal_anime(self, year: Optional[int] = None, season: Optional[str] = None, 
                          page: int = 1, per_page: int = 20, source: str = 'anilist') -> List[Dict[str, Any]]:
        """Fetch seasonal anime from the specified source.
        
        Args:
            year: Year of the season (default: current year)
            season: Season name ('WINTER', 'SPRING', 'SUMMER', 'FALL')
            page: Page number (1-based)
            per_page: Number of items per page
            source: Data source ('anilist', 'mal', or 'trakt')
            
        Returns:
            List[Dict[str, Any]]: List of seasonal anime with details
        """
        if source == 'anilist' and self.anilist_enabled:
            return self._get_anilist_seasonal(year, season, page, per_page)
        elif source == 'mal' and self.mal_enabled:
            return self._get_mal_seasonal(year, season, page, per_page)
        elif source == 'trakt' and self.trakt_enabled:
            return self._get_trakt_seasonal(year, season, page, per_page)
        else:
            self._log(f"Seasonal anime not available from {source} or service is disabled", xbmc.LOGWARNING)
            return []

    def _get_anilist_seasonal(self, year: Optional[int] = None, season: Optional[str] = None, 
                             page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        """Fetch seasonal anime from AniList."""
        # Determine current season and year if not provided
        now = datetime.now()
        if not year:
            year = now.year
        if not season:
            month = now.month
            if month in [12, 1, 2]:
                season = 'WINTER'
            elif month in [3, 4, 5]:
                season = 'SPRING'
            elif month in [6, 7, 8]:
                season = 'SUMMER'
            else:
                season = 'FALL'

        query = '''
        query ($season: MediaSeason, $seasonYear: Int, $page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            pageInfo {
              total
              perPage
              currentPage
              lastPage
              hasNextPage
            }
            media(season: $season, seasonYear: $seasonYear, type: ANIME, sort: POPULARITY_DESC) {
              id
              idMal
              title {
                romaji
                english
                native
                userPreferred
              }
              type
              format
              status
              description(asHtml: false)
              startDate { year month day }
              endDate { year month day }
              season
              seasonYear
              episodes
              duration
              chapters
              volumes
              source
              hashtag
              isLicensed
              isAdult
              averageScore
              meanScore
              popularity
              favourites
              genres
              synonyms
              studios(isMain: true) {
                nodes { id name siteUrl }
              }
              coverImage {
                extraLarge
                large
                medium
                color
              }
              bannerImage
              nextAiringEpisode {
                airingAt
                timeUntilAiring
                episode
              }
              trailer {
                id
                site
                thumbnail
              }
              externalLinks {
                url
                site
              }
              rankings {
                rank
                type
                allTime
                season
                year
              }
              tags {
                name
                description
                category
                rank
                isGeneralSpoiler
                isMediaSpoiler
                isAdult
              }
            }
          }
        }'''

        data = self._anilist_query(query, {
            'season': season,
            'seasonYear': year,
            'page': page,
            'perPage': min(50, per_page)  # AniList max per_page is 50
        })

        if not data:
            return []
            
        media_list = data.get('data', {}).get('Page', {}).get('media', [])
        return [self._format_anilist_media(m) for m in media_list if m]

    def _get_mal_seasonal(self, year: Optional[int] = None, season: Optional[str] = None, 
                         page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        """Fetch seasonal anime from MyAnimeList."""
        # Determine current season and year if not provided
        now = datetime.now()
        if not year:
            year = now.year
        if not season:
            month = now.month
            if month in [12, 1, 2]:
                season = 'winter'
            elif month in [3, 4, 5]:
                season = 'spring'
            elif month in [6, 7, 8]:
                season = 'summer'
            else:
                season = 'fall'
        else:
            season = season.lower()

        data = self._mal_request(
            'anime/seasonal',
            params={
                'year': year,
                'season': season,
                'sort': 'anime_num_list_users',
                'limit': min(100, per_page),  # MAL max limit is 100
                'offset': (page - 1) * per_page,
                'fields': 'id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,num_list_users,num_scoring_users,nsfw,genres,media_type,status,num_episodes,start_season,broadcast,source,average_episode_duration,rating,pictures,background,related_anime,related_manga,recommendations,studios,statistics',
                'nsfw': 'true' if self.addon.getSettingBool('show_nsfw') else 'false'
            }
        )
        
        if not data or 'data' not in data:
            return []
            
        return [self._format_mal_anime(item['node']) for item in data.get('data', []) if item.get('node')]

    def _get_trakt_seasonal(self, year: Optional[int] = None, season: Optional[str] = None, 
                           page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        """Fetch seasonal anime from Trakt."""
        # Determine current season and year if not provided
        now = datetime.now()
        if not year:
            year = now.year
        if not season:
            month = now.month
            if month in [12, 1, 2]:
                season = 'winter'
            elif month in [3, 4, 5]:
                season = 'spring'
            elif month in [6, 7, 8]:
                season = 'summer'
            else:
                season = 'fall'

        # Map to Trakt's season format (winter -> winter-2022)
        trakt_season = f"{season}-{year}"
        
        data = self._trakt_request(
            'shows/trending',
            params={
                'extended': 'full',
                'limit': min(100, per_page),  # Trakt max limit is 100
                'page': page,
                'genres': 'anime',
                'years': str(year),
                'status': 'returning,new',
                'sort': 'watchers',
                'order': 'desc'
            }
        )
        
        if not data:
            return []
            
        return [self._format_trakt_show(item['show']) for item in data if item.get('show')]

    # Formatting helper methods

    def _format_anilist_media(self, media: Dict[str, Any]) -> Dict[str, Any]:
        """Format AniList media object into a standardized format."""
        if not media:
            return {}
            
        return {
            'id': str(media.get('id', '')),
            'mal_id': media.get('idMal'),
            'title': media.get('title', {}).get('english') or 
                    media.get('title', {}).get('romaji') or 
                    media.get('title', {}).get('native') or 
                    media.get('title', {}).get('userPreferred', ''),
            'title_english': media.get('title', {}).get('english', ''),
            'title_japanese': media.get('title', {}).get('native', ''),
            'title_romaji': media.get('title', {}).get('romaji', ''),
            'type': media.get('type', 'ANIME').lower(),
            'format': media.get('format', '').lower() if media.get('format') else None,
            'status': media.get('status', '').lower(),
            'description': media.get('description', ''),
            'start_date': self._format_date(media.get('startDate')),
            'end_date': self._format_date(media.get('endDate')),
            'season': media.get('season', '').lower(),
            'season_year': media.get('seasonYear'),
            'episodes': media.get('episodes'),
            'duration': media.get('duration'),
            'chapters': media.get('chapters'),
            'volumes': media.get('volumes'),
            'source': media.get('source', '').lower(),
            'is_adult': media.get('isAdult', False),
            'average_score': media.get('averageScore'),
            'mean_score': media.get('meanScore'),
            'popularity': media.get('popularity'),
            'favorites': media.get('favourites'),
            'genres': media.get('genres', []),
            'synonyms': media.get('synonyms', []),
            'studios': [{
                'id': studio.get('id'),
                'name': studio.get('name', ''),
                'url': studio.get('siteUrl', '')
            } for studio in (media.get('studios', {}).get('nodes', []) or []) if studio],
            'poster': media.get('coverImage', {}).get('extraLarge') or 
                     media.get('coverImage', {}).get('large') or 
                     media.get('coverImage', {}).get('medium', ''),
            'banner': media.get('bannerImage', ''),
            'color': media.get('coverImage', {}).get('color'),
            'next_airing_episode': {
                'airing_at': media.get('nextAiringEpisode', {}).get('airingAt'),
                'time_until_airing': media.get('nextAiringEpisode', {}).get('timeUntilAiring'),
                'episode': media.get('nextAiringEpisode', {}).get('episode')
            } if media.get('nextAiringEpisode') else None,
            'trailer': {
                'id': media.get('trailer', {}).get('id'),
                'site': media.get('trailer', {}).get('site'),
                'thumbnail': media.get('trailer', {}).get('thumbnail')
            } if media.get('trailer') else None,
            'external_links': [{
                'url': link.get('url', ''),
                'site': link.get('site', '')
            } for link in (media.get('externalLinks') or []) if link],
            'rankings': [{
                'rank': rank.get('rank'),
                'type': rank.get('type', '').lower(),
                'all_time': rank.get('allTime', False),
                'season': rank.get('season', '').lower(),
                'year': rank.get('year')
            } for rank in (media.get('rankings') or []) if rank],
            'tags': [{
                'name': tag.get('name', ''),
                'description': tag.get('description', ''),
                'category': tag.get('category', '').lower(),
                'rank': tag.get('rank'),
                'is_spoiler': tag.get('isGeneralSpoiler') or tag.get('isMediaSpoiler'),
                'is_adult': tag.get('isAdult', False)
            } for tag in (media.get('tags') or []) if tag],
            'source': 'anilist'
        }

    def _format_mal_anime(self, anime: Dict[str, Any]) -> Dict[str, Any]:
        """Format MyAnimeList anime object into a standardized format."""
        if not anime:
            return {}
            
        return {
            'id': str(anime.get('id', '')),
            'title': anime.get('title', ''),
            'title_english': anime.get('alternative_titles', {}).get('en', ''),
            'title_japanese': anime.get('alternative_titles', {}).get('ja', ''),
            'title_synonyms': anime.get('alternative_titles', {}).get('synonyms', []),
            'type': anime.get('media_type', '').lower(),
            'format': anime.get('media_type', '').lower(),
            'status': anime.get('status', '').lower(),
            'description': anime.get('synopsis', ''),
            'start_date': anime.get('start_date'),
            'end_date': anime.get('end_date'),
            'season': anime.get('start_season', {}).get('season', '').lower(),
            'season_year': anime.get('start_season', {}).get('year'),
            'episodes': anime.get('num_episodes'),
            'duration': anime.get('average_episode_duration'),
            'source': anime.get('source', '').lower(),
            'is_adult': anime.get('nsfw', False),
            'average_score': anime.get('mean'),
            'mean_score': anime.get('mean'),
            'popularity': anime.get('popularity'),
            'favorites': anime.get('num_list_users'),
            'genres': [genre.get('name', '') for genre in (anime.get('genres') or []) if genre],
            'studios': [{
                'id': studio.get('id'),
                'name': studio.get('name', '')
            } for studio in (anime.get('studios') or []) if studio],
            'poster': anime.get('main_picture', {}).get('large', '') or 
                     anime.get('main_picture', {}).get('medium', ''),
            'banner': next((pic['large'] for pic in (anime.get('pictures') or []) 
                          if pic.get('large')), ''),
            'background': anime.get('background', ''),
            'broadcast': anime.get('broadcast', {}).get('day_of_the_week', '').lower() 
                        if anime.get('broadcast') else '',
            'rating': anime.get('rating', '').lower(),
            'statistics': {
                'status': {s['status']: s['num_list_users'] 
                         for s in (anime.get('statistics', {}).get('status', {}).get('items', []) or [])},
                'score': {str(s['score']): s['num_users'] 
                         for s in (anime.get('statistics', {}).get('score', {}).get('items', []) or [])}
            } if anime.get('statistics') else {},
            'related_anime': [{
                'id': str(rel.get('node', {}).get('id', '')),
                'title': rel.get('node', {}).get('title', ''),
                'relation_type': rel.get('relation_type', '').lower(),
                'poster': rel.get('node', {}).get('main_picture', {}).get('medium', '')
            } for rel in (anime.get('related_anime') or []) if rel.get('node')],
            'recommendations': [{
                'id': str(rec.get('node', {}).get('id', '')),
                'title': rec.get('node', {}).get('title', ''),
                'num_recommendations': rec.get('num_recommendations', 0),
                'poster': rec.get('node', {}).get('main_picture', {}).get('medium', '')
            } for rec in (anime.get('recommendations', {}).get('data', []) or []) if rec.get('node')],
            'source': 'mal'
        }

    def search_anime(self, query: str, page: int = 1, per_page: int = 20, source: str = None, 
                    media_type: str = None, status: str = None, year: int = None, 
                    genres: List[str] = None, sort: str = 'SEARCH_MATCH') -> List[Dict[str, Any]]:
        """
        Search for anime across all enabled services or a specific source.
        
        Args:
            query: Search query string
            page: Page number (1-based)
            per_page: Number of results per page
            source: Specific source to search ('anilist', 'mal', 'trakt')
            media_type: Filter by media type (e.g., 'tv', 'movie')
            status: Filter by status (e.g., 'FINISHED', 'ONGOING')
            year: Filter by year
            genres: List of genres to filter by
            sort: Sort method ('SEARCH_MATCH', 'POPULARITY', 'SCORE', 'TRENDING', 'UPDATED_AT')
            
        Returns:
            List of anime items in standardized format
        """
        if source:
            sources = [source]
        else:
            sources = []
            if self.anilist_enabled:
                sources.append('anilist')
            if self.mal_enabled:
                sources.append('mal')
            if self.trakt_enabled:
                sources.append('trakt')
        
        results = []
        
        for src in sources:
            try:
                if src == 'anilist':
                    results.extend(self._search_anilist(query, page, per_page, media_type, status, year, genres, sort))
                elif src == 'mal':
                    results.extend(self._search_mal(query, page, per_page, media_type, status, year, genres))
                elif src == 'trakt':
                    results.extend(self._search_trakt(query, page, per_page, media_type, year, genres))
            except Exception as e:
                self._log(f"Error searching {src}: {str(e)}", xbmc.LOGERROR)
        
        # Remove duplicates by ID and source
        seen = set()
        unique_results = []
        for item in results:
            item_id = f"{item.get('id')}_{item.get('source')}"
            if item_id not in seen:
                seen.add(item_id)
                unique_results.append(item)
        
        # Sort by relevance/score if needed
        if sort == 'SEARCH_MATCH':
            # Simple sorting by title match (could be improved)
            query_lower = query.lower()
            unique_results.sort(
                key=lambda x: (
                    x.get('title', '').lower().startswith(query_lower),
                    -x.get('score', 0) if x.get('score') is not None else 0,
                    -x.get('popularity', 0) if x.get('popularity') is not None else 0
                ),
                reverse=True
            )
        
        return unique_results[:per_page]
    
    def _search_anilist(self, query: str, page: int, per_page: int, media_type: str = None, 
                       status: str = None, year: int = None, genres: List[str] = None, 
                       sort: str = 'SEARCH_MATCH') -> List[Dict[str, Any]]:
        """Search anime on AniList."""
        variables = {
            'search': query,
            'page': page,
            'perPage': per_page,
            'type': 'ANIME'
        }
        
        # Build the filter query
        filters = []
        if media_type:
            filters.append(f'type: {media_type.upper()}')
        if status:
            filters.append(f'status: {status.upper()}')
        if year:
            filters.append(f'startDate_like: "{year}%"')
        if genres:
            filters.append('genres: [' + ', '.join([f'"{g}"' for g in genres]) + ']')
        
        # Add sort
        sort_mapping = {
            'SEARCH_MATCH': 'SEARCH_MATCH',
            'POPULARITY': 'POPULARITY_DESC',
            'SCORE': 'SCORE_DESC',
            'TRENDING': 'TRENDING_DESC',
            'UPDATED_AT': 'UPDATED_AT_DESC'
        }
        sort_value = sort_mapping.get(sort, 'SEARCH_MATCH')
        
        query_str = f"""
        query ($search: String, $page: Int, $perPage: Int) {{
          Page(page: $page, perPage: $perPage) {{
            pageInfo {{
              total
              perPage
              currentPage
              lastPage
              hasNextPage
            }}
            media(
              search: $search
              type: ANIME
              {'sort: ' + sort_value + ',' if sort_value != 'SEARCH_MATCH' else ''}
              {'filter: {' + ', '.join(filters) + '}' if filters else ''}
            ) {{
              id
              idMal
              title {{
                romaji
                english
                native
                userPreferred
              }}
              type
              format
              status
              description(asHtml: false)
              startDate {{ year month day }}
              endDate {{ year month day }}
              season
              seasonYear
              episodes
              duration
              chapters
              volumes
              source
              hashtag
              isLicensed
              isAdult
              averageScore
              meanScore
              popularity
              favourites
              genres
              synonyms
              studios(isMain: true) {{
                nodes {{ id name siteUrl }}
              }}
              coverImage {{
                extraLarge
                large
                medium
                color
              }}
              bannerImage
              nextAiringEpisode {{
                airingAt
                timeUntilAiring
                episode
              }}
              trailer {{
                id
                site
                thumbnail
              }}
              externalLinks {{
                url
                site
              }}
              rankings {{
                rank
                type
                allTime
                season
                year
              }}
              tags {{
                name
                description
                category
                rank
                isGeneralSpoiler
                isMediaSpoiler
                isAdult
              }}
            }}
          }}
        }}
        """
        
        data = self._anilist_query(query_str, variables)
        if not data:
            return []
            
        media_list = data.get('data', {}).get('Page', {}).get('media', [])
        return [self._format_anilist_media(m) for m in media_list if m]
    
    def _search_mal(self, query: str, page: int, per_page: int, media_type: str = None, 
                   status: str = None, year: int = None, genres: List[str] = None) -> List[Dict[str, Any]]:
        """Search anime on MyAnimeList."""
        params = {
            'q': query,
            'limit': min(per_page, 100),  # MAL max limit is 100
            'offset': (page - 1) * per_page,
            'fields': 'id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,'
                     'num_list_users,num_scoring_users,nsfw,genres,media_type,status,num_episodes,start_season,'
                     'broadcast,source,average_episode_duration,rating,pictures,background,related_anime,related_manga,'
                     'recommendations,studios,statistics',
            'nsfw': 'true' if self.addon.getSettingBool('show_nsfw') else 'false'
        }
        
        # Add filters
        if media_type:
            params['type'] = media_type.lower()
        if status:
            status_mapping = {
                'FINISHED': 'completed',
                'ONGOING': 'currently_airing',
                'NOT_YET_RELEASED': 'not_yet_aired',
                'CANCELLED': 'cancelled'
            }
            params['status'] = status_mapping.get(status.upper(), '')
        if year:
            params['start_date'] = f'{year}-01-01'
        if genres:
            params['genres'] = ','.join(str(self._get_mal_genre_id(g)) for g in genres if self._get_mal_genre_id(g) is not None)
        
        data = self._mal_request('anime', params=params)
        if not data or 'data' not in data:
            return []
            
        return [self._format_mal_anime(item['node']) for item in data.get('data', []) if item.get('node')]
    
    def _search_trakt(self, query: str, page: int, per_page: int, media_type: str = None, 
                     year: int = None, genres: List[str] = None) -> List[Dict[str, Any]]:
        """Search anime on Trakt."""
        params = {
            'query': query,
            'limit': min(per_page, 100),  # Trakt max limit is 100
            'page': page,
            'extended': 'full',
            'fields': 'title,aliases,overview',
            'genres': 'anime'
        }
        
        # Add filters
        if year:
            params['years'] = str(year)
        if media_type:
            media_type = media_type.lower()
            if media_type in ['tv', 'show']:
                params['type'] = 'show'
            elif media_type == 'movie':
                params['type'] = 'movie'
        
        data = self._trakt_request('search', params=params)
        if not data:
            return []
            
        results = []
        for item in data:
            if 'show' in item:
                results.append(self._format_trakt_show(item['show']))
        
        return results
    
    def _get_mal_genre_id(self, genre_name: str) -> Optional[int]:
        """Get MAL genre ID by name."""
        genre_map = {
            'Action': 1, 'Adventure': 2, 'Cars': 3, 'Comedy': 4, 'Dementia': 5, 'Demons': 6,
            'Mystery': 7, 'Drama': 8, 'Ecchi': 9, 'Fantasy': 10, 'Game': 11, 'Hentai': 12,
            'Historical': 13, 'Horror': 14, 'Kids': 15, 'Magic': 16, 'Martial Arts': 17,
            'Mecha': 18, 'Music': 19, 'Parody': 20, 'Samurai': 21, 'Romance': 22, 'School': 23,
            'Sci-Fi': 24, 'Shoujo': 25, 'Shoujo Ai': 26, 'Shounen': 27, 'Shounen Ai': 28,
            'Space': 29, 'Sports': 30, 'Super Power': 31, 'Vampire': 32, 'Yaoi': 33, 'Yuri': 34,
            'Harem': 35, 'Slice of Life': 36, 'Supernatural': 37, 'Military': 38, 'Police': 39,
            'Psychological': 40, 'Thriller': 41, 'Seinen': 42, 'Josei': 43
        }
        return genre_map.get(genre_name.title())

    def _format_trakt_show(self, show: Dict[str, Any]) -> Dict[str, Any]:
        """Format Trakt show object into a standardized format."""
        if not show:
            return {}
            
        return {
            'id': str(show.get('ids', {}).get('trakt', '')),
            'trakt_id': show.get('ids', {}).get('trakt'),
            'imdb_id': show.get('ids', {}).get('imdb', ''),
            'tmdb_id': show.get('ids', {}).get('tmdb'),
            'tvdb_id': show.get('ids', {}).get('tvdb'),
            'tvrage_id': show.get('ids', {}).get('tvrage'),
            'title': show.get('title', ''),
            'year': show.get('year'),
            'type': 'anime',
            'status': show.get('status', '').lower(),
            'description': show.get('overview', ''),
            'first_aired': show.get('first_aired'),
            'air_day': show.get('air_day', '').lower(),
            'air_time': show.get('air_time', ''),
            'timezone': show.get('air_timezone', ''),
            'runtime': show.get('runtime'),
            'certification': show.get('certification', '').lower(),
            'network': show.get('network', ''),
            'country': show.get('country', '').lower(),
            'trailer': show.get('trailer'),
            'homepage': show.get('homepage', ''),
            'language': show.get('language', '').lower(),
            'genres': show.get('genres', []),
            'episode_count': show.get('episode_count'),
            'season_count': show.get('season_count'),
            'status': show.get('status', '').lower(),
            'rating': show.get('rating'),
            'votes': show.get('votes'),
            'comment_count': show.get('comment_count'),
            'updated_at': show.get('updated_at'),
            'available_translations': show.get('available_translations', []),
            'poster': next(
                (image['url'] for image in show.get('images', {}).get('poster', []) 
                 if image.get('url') and 'thumb' not in image.get('url', '')),
                ''
            ),
            'banner': next(
                (image['url'] for image in show.get('images', {}).get('banner', []) 
                 if image.get('url')),
                ''
            ),
            'fanart': next(
                (image['url'] for image in show.get('images', {}).get('fanart', []) 
                 if image.get('url')),
                ''
            ),
            'thumb': next(
                (image['url'] for image in show.get('images', {}).get('thumb', []) 
                 if image.get('url')),
                ''
            ),
            'logo': next(
                (image['url'] for image in show.get('images', {}).get('logo', []) 
                 if image.get('url')),
                ''
            ),
            'clearart': next(
                (image['url'] for image in show.get('images', {}).get('clearart', []) 
                 if image.get('url')),
                ''
            ),
            'characterart': next(
                (image['url'] for image in show.get('images', {}).get('characterart', []) 
                 if image.get('url')),
                ''
            ),
            'source': 'trakt'
        }

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
        if not date_obj or 'year' not in date_obj or not date_obj['year']:
            return ''
            
        year = date_obj['year']
        month = str(date_obj.get('month', 1)).zfill(2)
        day = str(date_obj.get('day', 1)).zfill(2)
        
        return f"{year}-{month}-{day}"
        
    def get_episodes_by_airdate(self, date_str):
        """
        Fetch episodes airing on a specific date from AniList
        Args:
            date_str (str): Date in YYYY-MM-DD format
        Returns:
            list: List of episode dictionaries with anime info
        """
        query = """
        query ($date: Int, $endDate: Int) {
            Page(page: 1, perPage: 50) {
                airingSchedules(airingAt_greater: $date, airingAt_lesser: $endDate, sort: TIME) {
                    episode
                    timeUntilAiring
                    media {
                        id
                        title {
                            romaji
                            english
                            native
                        }
                        coverImage {
                            large
                            color
                        }
                        bannerImage
                        description
                        format
                        episodes
                        averageScore
                        meanScore
                        popularity
                        genres
                        status
                        nextAiringEpisode {
                            episode
                            timeUntilAiring
                        }
                    }
                }
            }
        }
        """
        try:
            # Convert date to timestamp
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            start_timestamp = int(date_obj.timestamp())
            end_timestamp = start_timestamp + 86400  # Add 24 hours

            variables = {
                'date': start_timestamp,
                'endDate': end_timestamp
            }

            result = self._anilist_query(query, variables)
            if not result or 'data' not in result:
                return []

            schedules = result['data']['Page']['airingSchedules']
            episodes = []

            for schedule in schedules:
                media = schedule.get('media', {})
                if not media:
                    continue

                episode = {
                    'anime_id': media.get('id'),
                    'episode': schedule.get('episode'),
                    'title': next((t for t in [
                        media['title'].get('english'),
                        media['title'].get('romaji'),
                        media['title'].get('native')
                    ] if t), ''),
                    'description': media.get('description', ''),
                    'poster': media.get('coverImage', {}).get('large', ''),
                    'banner': media.get('bannerImage', ''),
                    'show_title': next((t for t in [
                        media['title'].get('english'),
                        media['title'].get('romaji'),
                        media['title'].get('native')
                    ] if t), ''),
                    'air_date': date_str
                }
                episodes.append(episode)

            return episodes

        except Exception as e:
            self._log(f"Error in get_episodes_by_airdate: {str(e)}", xbmc.LOGERROR)
            return []

    def get_genres(self):
        """
        Fetch all available anime genres from AniList with counts
        Returns:
            list: List of genre dictionaries with name and count
        """
        query = """
        {
            GenreCollection
            MediaTagCollection {
                name
                category
                isAdult
            }
        }
        """
        try:
            result = self._anilist_query(query)
            if not result or 'data' not in result:
                return []

            genres = []
            # Add regular genres
            for genre in result['data'].get('GenreCollection', []):
                genres.append({
                    'name': genre,
                    'count': None,  # AniList doesn't provide counts for genres
                    'is_adult': False
                })

            # Add tags (treated as additional genres)
            for tag in result['data'].get('MediaTagCollection', []):
                if tag.get('isAdult') or not tag.get('name'):
                    continue
                genres.append({
                    'name': tag['name'],
                    'count': None,
                    'is_adult': tag.get('isAdult', False)
                })

            return genres

        except Exception as e:
            self._log(f"Error in get_genres: {str(e)}", xbmc.LOGERROR)
            return []

    def get_anime_by_genre(self, genre, page=1, per_page=50):
        """
        Fetch anime by genre from AniList
        Args:
            genre (str): Genre to filter by
            page (int): Page number
            per_page (int): Items per page
        Returns:
            list: List of anime dictionaries
        """
        query = """
        query ($genre: String, $page: Int, $perPage: Int) {
            Page(page: $page, perPage: $perPage) {
                pageInfo {
                    total
                    perPage
                    currentPage
                    lastPage
                    hasNextPage
                }
                media(genre: $genre, type: ANIME, sort: POPULARITY_DESC) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    coverImage {
                        large
                        color
                    }
                    bannerImage
                    description
                    format
                    episodes
                    averageScore
                    meanScore
                    popularity
                    genres
                    status
                    season
                    seasonYear
                    nextAiringEpisode {
                        episode
                        timeUntilAiring
                    }
                }
            }
        }
        """
        try:
            variables = {
                'genre': genre,
                'page': page,
                'perPage': per_page
            }

            result = self._anilist_query(query, variables)
            if not result or 'data' not in result:
                return []

            anime_list = []
            for media in result['data']['Page']['media']:
                anime = {
                    'id': media.get('id'),
                    'title': next((t for t in [
                        media['title'].get('english'),
                        media['title'].get('romaji'),
                        media['title'].get('native')
                    ] if t), ''),
                    'year': media.get('seasonYear'),
                    'episodes': media.get('episodes'),
                    'score': media.get('averageScore'),
                    'poster': media.get('coverImage', {}).get('large', ''),
                    'banner': media.get('bannerImage', ''),
                    'description': media.get('description', ''),
                    'genres': media.get('genres', []),
                    'status': media.get('status'),
                    'source': 'anilist'
                }
                anime_list.append(anime)

            return anime_list

        except Exception as e:
            self._log(f"Error in get_anime_by_genre: {str(e)}", xbmc.LOGERROR)
            return []

    def search(self, query, media_type=None, status=None, year=None, genre=None, page=1, per_page=20):
        """
        Enhanced search with filters
        Args:
            query (str): Search term
            media_type (str): Filter by media type (TV, MOVIE, etc.)
            status (str): Filter by status (RELEASING, FINISHED, etc.)
            year (int): Filter by year
            genre (str): Filter by genre
            page (int): Page number
            per_page (int): Items per page
        Returns:
            list: List of anime dictionaries
        """
        query_str = """
        query ($search: String, $type: MediaType, $status: MediaStatus, $year: Int, $genre: String, 
               $page: Int, $perPage: Int) {
            Page(page: $page, perPage: $perPage) {
                pageInfo {
                    total
                    perPage
                    currentPage
                    lastPage
                    hasNextPage
                }
                media(search: $search, type: $type, status: $status, 
                      startDate_like: $year, genre: $genre, sort: POPULARITY_DESC) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    coverImage {
                        large
                        color
                    }
                    bannerImage
                    description
                    format
                    episodes
                    averageScore
                    meanScore
                    popularity
                    genres
                    status
                    season
                    seasonYear
                    nextAiringEpisode {
                        episode
                        timeUntilAiring
                    }
                }
            }
        }
        """
        try:
            variables = {
                'search': query,
                'type': media_type,
                'status': status,
                'year': f"{year}%" if year else None,
                'genre': genre,
                'page': page,
                'perPage': per_page
            }

            # Remove None values
            variables = {k: v for k, v in variables.items() if v is not None}

            result = self._anilist_query(query_str, variables)
            if not result or 'data' not in result:
                return []

            anime_list = []
            for media in result['data']['Page']['media']:
                anime = {
                    'id': media.get('id'),
                    'title': next((t for t in [
                        media['title'].get('english'),
                        media['title'].get('romaji'),
                        media['title'].get('native')
                    ] if t), ''),
                    'year': media.get('seasonYear'),
                    'episodes': media.get('episodes'),
                    'score': media.get('averageScore'),
                    'poster': media.get('coverImage', {}).get('large', ''),
                    'banner': media.get('bannerImage', ''),
                    'description': media.get('description', ''),
                    'genres': media.get('genres', []),
                    'status': media.get('status'),
                    'source': 'anilist'
                }
                anime_list.append(anime)

            return anime_list

        except Exception as e:
            self._log(f"Error in search: {str(e)}", xbmc.LOGERROR)
            return []
