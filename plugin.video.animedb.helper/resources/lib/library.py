"""
library.py: User library management for AnimeDB Helper

This module handles the user's personal anime library, including watch status, progress tracking,
and syncing across different services.
"""
import os
import json
import time
import xbmc
import xbmcgui
import xbmcvfs
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

from resources.lib.api import AnimeDBAPI
from resources.lib.ui import ADDON, ADDON_ID, add_directory_item

class AnimeLibrary:
    """Manages the user's anime library and watch status."""
    
    def __init__(self):
        """Initialize the library with paths and load data."""
        self.addon_profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        self.library_file = os.path.join(self.addon_profile, 'library.json')
        self.history_file = os.path.join(self.addon_profile, 'watch_history.json')
        
        # Create addon profile directory if it doesn't exist
        if not xbmcvfs.exists(self.addon_profile):
            xbmcvfs.mkdirs(self.addon_profile)
        
        # Initialize data structures
        self.library = self._load_library()
        self.watch_history = self._load_watch_history()
        
        # Initialize API
        self.api = AnimeDBAPI()
    
    def _load_library(self) -> Dict[str, Any]:
        """Load the user's library from disk."""
        if not xbmcvfs.exists(self.library_file):
            return {
                'version': 1,
                'anime': {},
                'last_updated': int(time.time())
            }
            
        try:
            with xbmcvfs.File(self.library_file, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            xbmc.log(f"Error loading library: {str(e)}", xbmc.LOGERROR)
            return {
                'version': 1,
                'anime': {},
                'last_updated': int(time.time())
            }
    
    def _save_library(self) -> bool:
        """Save the library to disk."""
        self.library['last_updated'] = int(time.time())
        try:
            with xbmcvfs.File(self.library_file, 'w') as f:
                json.dump(self.library, f, indent=2)
            return True
        except (IOError, TypeError) as e:
            xbmc.log(f"Error saving library: {str(e)}", xbmc.LOGERROR)
            return False
    
    def _load_watch_history(self) -> Dict[str, Any]:
        """Load watch history from disk."""
        if not xbmcvfs.exists(self.history_file):
            return {
                'version': 1,
                'history': [],
                'last_updated': 0
            }
            
        try:
            with xbmcvfs.File(self.history_file, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            xbmc.log(f"Error loading watch history: {str(e)}", xbmc.LOGERROR)
            return {
                'version': 1,
                'history': [],
                'last_updated': 0
            }
    
    def _save_watch_history(self) -> bool:
        """Save watch history to disk."""
        self.watch_history['last_updated'] = int(time.time())
        try:
            with xbmcvfs.File(self.history_file, 'w') as f:
                json.dump(self.watch_history, f, indent=2)
            return True
        except (IOError, TypeError) as e:
            xbmc.log(f"Error saving watch history: {str(e)}", xbmc.LOGERROR)
            return False
    
    def add_to_library(self, anime_id: str, source: str = 'anilist', status: str = 'PLANNING', 
                      progress: int = 0, total_episodes: int = 0, score: int = 0, 
                      rewatch_count: int = 0, notes: str = '') -> bool:
        """Add or update an anime in the user's library."""
        anime_key = f"{source}_{anime_id}"
        
        if anime_key not in self.library['anime']:
            self.library['anime'][anime_key] = {
                'id': anime_id,
                'source': source,
                'status': status,
                'progress': progress,
                'total_episodes': total_episodes,
                'score': score,
                'rewatch_count': rewatch_count,
                'notes': notes,
                'added_at': int(time.time()),
                'updated_at': int(time.time())
            }
        else:
            # Update existing entry
            self.library['anime'][anime_key].update({
                'status': status,
                'progress': progress,
                'total_episodes': total_episodes,
                'score': score,
                'rewatch_count': rewatch_count,
                'notes': notes,
                'updated_at': int(time.time())
            })
        
        return self._save_library()
    
    def remove_from_library(self, anime_id: str, source: str = 'anilist') -> bool:
        """Remove an anime from the user's library."""
        anime_key = f"{source}_{anime_id}"
        if anime_key in self.library['anime']:
            del self.library['anime'][anime_key]
            return self._save_library()
        return False
    
    def get_library_anime(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all anime in the user's library, optionally filtered by status."""
        anime_list = list(self.library['anime'].values())
        
        if status_filter:
            anime_list = [a for a in anime_list if a.get('status', '').upper() == status_filter.upper()]
        
        # Sort by title
        return sorted(anime_list, key=lambda x: x.get('title', '').lower())
    
    def get_anime_status(self, anime_id: str, source: str = 'anilist') -> Optional[Dict[str, Any]]:
        """Get the status of an anime in the user's library."""
        anime_key = f"{source}_{anime_id}"
        return self.library['anime'].get(anime_key)
    
    def update_watch_status(self, anime_id: str, source: str, episode: int, 
                          total_episodes: int = 0, status: str = None) -> bool:
        """Update the watch status of an anime."""
        anime_key = f"{source}_{anime_id}"
        now = int(time.time())
        
        # Add to watch history
        self.watch_history['history'].append({
            'anime_id': anime_id,
            'source': source,
            'episode': episode,
            'watched_at': now
        })
        
        # Update library entry
        if anime_key not in self.library['anime']:
            self.library['anime'][anime_key] = {
                'id': anime_id,
                'source': source,
                'status': status or 'WATCHING',
                'progress': episode,
                'total_episodes': total_episodes,
                'score': 0,
                'rewatch_count': 0,
                'notes': '',
                'added_at': now,
                'updated_at': now
            }
        else:
            entry = self.library['anime'][anime_key]
            entry['progress'] = max(episode, entry.get('progress', 0))
            entry['total_episodes'] = total_episodes or entry.get('total_episodes', 0)
            
            # Update status if provided or auto-update based on progress
            if status:
                entry['status'] = status
            elif entry['progress'] >= entry['total_episodes'] and entry['total_episodes'] > 0:
                entry['status'] = 'COMPLETED'
            elif entry['status'] == 'PLANNING':
                entry['status'] = 'WATCHING'
            
            entry['updated_at'] = now
        
        # Save changes
        success = self._save_library() and self._save_watch_history()
        
        # Sync with online services if enabled
        if success and ADDON.getSettingBool('sync_watch_status'):
            self.sync_watch_status(anime_id, source, episode, status)
        
        return success
    
    def sync_watch_status(self, anime_id: str, source: str, episode: int, status: str = None) -> bool:
        """Sync watch status with online services."""
        if source == 'anilist' and ADDON.getSettingBool('anilist_enabled'):
            return self._sync_anilist(anime_id, episode, status)
        elif source == 'mal' and ADDON.getSettingBool('mal_enabled'):
            return self._sync_mal(anime_id, episode, status)
        return False
    
    def _sync_anilist(self, anime_id: str, episode: int, status: str = None) -> bool:
        """Sync watch status with AniList."""
        try:
            variables = {
                'mediaId': int(anime_id),
                'progress': episode
            }
            
            if status:
                status_map = {
                    'CURRENT': 'CURRENT',
                    'PLANNING': 'PLANNING',
                    'COMPLETED': 'COMPLETED',
                    'DROPPED': 'DROPPED',
                    'PAUSED': 'PAUSED',
                    'REPEATING': 'REPEATING'
                }
                if status.upper() in status_map:
                    variables['status'] = status_map[status.upper()]
            
            query = """
            mutation ($mediaId: Int, $progress: Int, $status: MediaListStatus) {
                SaveMediaListEntry(mediaId: $mediaId, progress: $progress, status: $status) {
                    id
                    progress
                    status
                }
            }
            """
            
            result = self.api._anilist_query(query, variables)
            return result is not None and 'data' in result
            
        except Exception as e:
            xbmc.log(f"Error syncing with AniList: {str(e)}", xbmc.LOGERROR)
            return False
    
    def _sync_mal(self, anime_id: str, episode: int, status: str = None) -> bool:
        """Sync watch status with MyAnimeList."""
        try:
            # MAL API requires the anime to be in the user's list first
            # This is a simplified version - actual implementation would need to handle OAuth
            params = {
                'num_watched_episodes': episode
            }
            
            if status:
                status_map = {
                    'CURRENT': 'watching',
                    'PLANNING': 'plan_to_watch',
                    'COMPLETED': 'completed',
                    'DROPPED': 'dropped',
                    'PAUSED': 'on_hold',
                    'REPEATING': 'watching'  # MAL doesn't have a direct equivalent for rewatching
                }
                if status.upper() in status_map:
                    params['status'] = status_map[status.upper()]
            
            # This would need proper OAuth implementation
            result = self.api._mal_request(f'anime/{anime_id}/my_list_status', params=params, method='PATCH')
            return result is not None
            
        except Exception as e:
            xbmc.log(f"Error syncing with MyAnimeList: {str(e)}", xbmc.LOGERROR)
            return False
    
    def get_watch_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get the user's watch history."""
        return sorted(
            self.watch_history['history'],
            key=lambda x: x.get('watched_at', 0),
            reverse=True
        )[:limit]

    def get_continue_watching(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get a list of anime to continue watching.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of anime dictionaries with watch progress
        """
        in_progress = []
        
        for anime_id, anime in self.library['anime'].items():
            if (anime.get('status') in ['CURRENT', 'WATCHING', None] and 
                anime.get('progress', 0) > 0 and
                (not anime.get('total_episodes') or 
                 anime.get('progress', 0) < anime.get('total_episodes', 0))):
                
                # Calculate progress percentage
                progress = anime.get('progress', 0)
                total = anime.get('total_episodes', 0)
                progress_pct = (progress / total * 100) if total > 0 else 0
                
                # Get last watched timestamp
                last_watched = self._get_last_watched_episode(anime_id, anime['source'])
                
                in_progress.append({
                    **anime,
                    'progress_pct': progress_pct,
                    'last_watched': last_watched,
                    'next_episode': progress + 1,
                    'key': anime_id
                })
        
        # Sort by most recently watched, then by progress percentage
        in_progress.sort(
            key=lambda x: (
                -x.get('last_watched', 0),
                -x.get('progress_pct', 0)
            )
        )
        
        return in_progress[:limit]
    
    def _get_last_watched_episode(self, anime_id: str, source: str) -> int:
        """Get the timestamp of the last watched episode for an anime."""
        last_watched = 0
        for entry in reversed(self.watch_history.get('history', [])):
            if (entry.get('anime_id') == anime_id and 
                entry.get('source') == source):
                last_watched = entry.get('watched_at', 0)
                break
        return last_watched
    
    def get_recently_watched(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recently watched anime, regardless of completion status.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of recently watched anime with watch progress
        """
        recent_entries = []
        processed = set()
        
        # Get unique anime from watch history, most recent first
        for entry in reversed(self.watch_history.get('history', [])):
            anime_key = f"{entry.get('source')}_{entry.get('anime_id')}"
            if anime_key in processed:
                continue
                
            anime = self.library['anime'].get(anime_key)
            if not anime:
                continue
                
            recent_entries.append({
                **anime,
                'last_watched': entry.get('watched_at', 0),
                'key': anime_key
            })
            processed.add(anime_key)
            
            if len(recent_entries) >= limit:
                break
                
        return recent_entries
    
    def update_episode_progress(self, anime_id: str, source: str, episode: int, 
                              progress: float, total_episodes: Optional[int] = None) -> bool:
        """
        Update the progress for an episode without marking it as fully watched.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            episode: The episode number
            progress: Progress as a float between 0 and 1
            total_episodes: Total number of episodes (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            anime = self.get_anime_status(anime_id, source)
            if not anime:
                return False
                
            # Update episode progress
            if 'episode_progress' not in anime:
                anime['episode_progress'] = {}
                
            anime['episode_progress'][str(episode)] = progress
            
            # Update overall progress if total_episodes is provided
            if total_episodes and total_episodes > 0:
                # Calculate overall progress based on watched episodes and current progress
                watched_episodes = set(anime.get('watched_episodes', []))
                total_watched = len(watched_episodes)
                
                if episode not in watched_episodes:
                    # If current episode isn't marked as watched, include its progress
                    current_episode_progress = progress
                else:
                    current_episode_progress = 1.0
                
                # Calculate overall progress (0-1 range)
                overall_progress = (total_watched + current_episode_progress) / total_episodes
                anime['progress'] = min(1.0, overall_progress) * 100
                
                # Update status based on progress
                if overall_progress >= 0.95:  # 95% or more considered complete
                    anime['status'] = 'COMPLETED'
                elif overall_progress > 0:
                    anime['status'] = 'WATCHING'
            
            self.save_library()
            return True
            
        except Exception as e:
            xbmc.log(f"Error updating episode progress: {str(e)}", xbmc.LOGERROR)
            return False
    
    def mark_episode_watched(self, anime_id: str, source: str, episode: int, 
                           total_episodes: Optional[int] = None) -> bool:
        """
        Mark an episode as watched and update the library.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            episode: The episode number
            total_episodes: Total number of episodes (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            anime = self.get_anime_status(anime_id, source)
            if not anime:
                return False
                
            # Update watched episodes
            watched_episodes = set(anime.get('watched_episodes', []))
            watched_episodes.add(episode)
            anime['watched_episodes'] = list(watched_episodes)
            
            # Ensure episode progress is marked as complete
            if 'episode_progress' not in anime:
                anime['episode_progress'] = {}
            anime['episode_progress'][str(episode)] = 1.0  # 100% watched
            
            # Update progress if total_episodes is provided
            if total_episodes and total_episodes > 0:
                progress = len(watched_episodes) / total_episodes * 100
                anime['progress'] = min(100, progress)
                
                # Update status based on progress
                if progress >= 95:  # 95% or more considered complete
                    anime['status'] = 'COMPLETED'
                elif progress > 0:
                    anime['status'] = 'WATCHING'
            
            self.save_library()
            return True
            
        except Exception as e:
            xbmc.log(f"Error marking episode as watched: {str(e)}", xbmc.LOGERROR)
            return False
    
    def get_episode_progress(self, anime_id: str, source: str, episode: int) -> float:
        """
        Get the progress for a specific episode.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            episode: The episode number
            
        Returns:
            float: Progress as a value between 0 and 1, or 0 if not found
        """
        try:
            anime = self.get_anime_status(anime_id, source)
            if not anime:
                return 0.0
                
            # Check if episode is marked as watched
            if episode in anime.get('watched_episodes', []):
                return 1.0
                
            # Check for partial progress
            episode_progress = anime.get('episode_progress', {}).get(str(episode))
            if episode_progress is not None:
                return float(episode_progress)
                
            return 0.0
            
        except Exception as e:
            xbmc.log(f"Error getting episode progress: {str(e)}", xbmc.LOGERROR)
            return 0.0
    
    def get_anime_status(self, anime_id: str, source: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of an anime in the library.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            
        Returns:
            dict: The anime data if found, None otherwise
        """
        try:
            for anime in self.library:
                if anime.get('id') == anime_id and anime.get('source') == source:
                    # Ensure all required fields exist
                    if 'watched_episodes' not in anime:
                        anime['watched_episodes'] = []
                    if 'episode_progress' not in anime:
                        anime['episode_progress'] = {}
                    if 'progress' not in anime:
                        anime['progress'] = 0
                    if 'status' not in anime:
                        anime['status'] = 'PLANNING'
                    return anime
            return None
        except Exception as e:
            xbmc.log(f"Error getting anime status: {str(e)}", xbmc.LOGERROR)
            return None
    
    def mark_episode_watched(self, anime_id: str, source: str, episode: int, 
                           total_episodes: int = 0) -> bool:
        """
        Mark an episode as watched and update progress.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            episode: The episode number that was watched
            total_episodes: Total number of episodes (if known)
            
        Returns:
            bool: True if successful, False otherwise
        """
        anime_key = f"{source}_{anime_id}"
        now = int(time.time())
        
        # Add to watch history
        self.watch_history['history'].append({
            'anime_id': anime_id,
            'source': source,
            'episode': episode,
            'watched_at': now,
            'timestamp': now
        })
        
        # Update library entry
        if anime_key in self.library['anime']:
            entry = self.library['anime'][anime_key]
            entry['progress'] = max(episode, entry.get('progress', 0))
            entry['total_episodes'] = total_episodes or entry.get('total_episodes', 0)
            entry['updated_at'] = now
            
            # Auto-update status if needed
            if entry['progress'] >= entry['total_episodes'] and entry['total_episodes'] > 0:
                entry['status'] = 'COMPLETED'
            elif entry.get('status') == 'PLANNING':
                entry['status'] = 'WATCHING'
        
        return self._save_library() and self._save_watch_history()
    
    def get_episode_progress(self, anime_id: str, source: str) -> Dict[int, bool]:
        """
        Get watch status for all episodes of an anime.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            
        Returns:
            Dict mapping episode numbers to watched status (True/False)
        """
        watched_episodes = set()
        for entry in self.watch_history.get('history', []):
            if (entry.get('anime_id') == anime_id and 
                entry.get('source') == source):
                watched_episodes.add(entry.get('episode', 0))
        
        anime_key = f"{source}_{anime_id}"
        total_episodes = self.library['anime'].get(anime_key, {}).get('total_episodes', 0)
        
        # If we don't know the total, use the highest watched episode
        if total_episodes == 0 and watched_episodes:
            total_episodes = max(watched_episodes)
        
        progress = {}
        for ep in range(1, total_episodes + 1):
            progress[ep] = ep in watched_episodes
            
        return progress

# Global instance
LIBRARY = AnimeLibrary()

def show_library(handle, status_filter=None):
    """Show the user's anime library with optional status filter."""
    anime_list = LIBRARY.get_library_anime(status_filter)
    
    if not anime_list:
        status_display = f" ({status_filter})" if status_filter else ""
        xbmcgui.Dialog().notification(
            "Library Empty",
            f"No anime found in your library{status_display}",
            xbmcgui.NOTIFICATION_INFO
        )
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Add status filter options
    if not status_filter:
        add_directory_item(
            handle,
            "Watching",
            {'action': 'library_status', 'status': 'CURRENT'},
            'watching.png'
        )
        add_directory_item(
            handle,
            "Completed",
            {'action': 'library_status', 'status': 'COMPLETED'},
            'completed.png'
        )
        add_directory_item(
            handle,
            "On Hold",
            {'action': 'library_status', 'status': 'PAUSED'},
            'onhold.png'
        )
        add_directory_item(
            handle,
            "Dropped",
            {'action': 'library_status', 'status': 'DROPPED'},
            'dropped.png'
        )
        add_directory_item(
            handle,
            "Plan to Watch",
            {'action': 'library_status', 'status': 'PLANNING'},
            'plantowatch.png'
        )
    
    # Add anime items
    for anime in anime_list:
        # Get additional details from cache or API
        details = anime.get('details')
        if not details:
            details = LIBRARY.api.anime_details(anime['id'], anime['source'])
            if details:
                anime['details'] = details
        
        # Create list item
        title = details.get('title', f"Anime {anime['id']}")
        if anime.get('progress', 0) > 0:
            title = f"{title} (Ep {anime['progress']}" + \
                   (f"/{anime['total_episodes']})" if anime.get('total_episodes') else ")")
        
        # Add context menu
        context_menu = [
            (
                "Remove from Library",
                f'RunPlugin(plugin://{ADDON_ID}/?action=remove_from_library&id={anime["id"]}&source={anime["source"]})'
            )
        ]
        
        # Add to directory
        add_directory_item(
            handle,
            title,
            {
                'action': 'anime_details',
                'anime_id': anime['id'],
                'source': anime['source']
            },
            details.get('cover_image'),
            description=details.get('description'),
            context_menu=context_menu
        )
    
    xbmcplugin.endOfDirectory(handle)

def show_continue_watching(handle):
    """
    Show the continue watching list with progress tracking.
    
    Displays anime that the user has started watching but not completed,
    sorted by most recently watched.
    """
    # Get continue watching list with progress info
    continue_list = LIBRARY.get_continue_watching(limit=50)  # Increased limit for pagination
    
    if not continue_list:
        # Try to show recently watched if nothing in progress
        recent_list = LIBRARY.get_recently_watched(limit=10)
        if recent_list:
            # Add a header
            add_directory_item(
                handle,
                "[B][COLOR=FF00FF00]Recently Watched[/COLOR][/B]",
                {'action': 'none'},
                is_folder=False
            )
            
            for anime in recent_list:
                _add_anime_item(handle, anime, is_recent=True)
        else:
            # Show empty state
            xbmcgui.Dialog().notification(
                "Nothing to Continue",
                "Start watching anime to see it here.",
                xbmcgui.NOTIFICATION_INFO
            )
        
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Add section header
    add_directory_item(
        handle,
        "[B][COLOR=FF00FF00]Continue Watching[/COLOR][/B]",
        {'action': 'none'},
        is_folder=False
    )
    
    # Add continue watching items
    for anime in continue_list:
        _add_anime_item(handle, anime)
    
    # Add recently watched section if there's space
    if len(continue_list) < 30:  # Only show if we have room
        recent_list = LIBRARY.get_recently_watched(limit=10)
        if recent_list:
            # Add a separator
            add_directory_item(
                handle,
                "[B][COLOR=FF00FF00]Recently Watched[/COLOR][/B]",
                {'action': 'none'},
                is_folder=False
            )
            
            for anime in recent_list:
                _add_anime_item(handle, anime, is_recent=True)
    
    xbmcplugin.endOfDirectory(handle)

def _add_anime_item(handle, anime, is_recent=False):
    """Helper function to add an anime item to the directory."""
    # Get additional details from cache or API
    anime_id = anime.get('id')
    source = anime.get('source')
    
    details = anime.get('details')
    if not details and anime_id and source:
        details = LIBRARY.api.anime_details(anime_id, source)
        if details:
            anime['details'] = details
    
    if not details:
        return  # Skip if we can't get details
    
    # Prepare title and progress info
    title = details.get('title', f"Anime {anime_id}")
    progress = anime.get('progress', 0)
    total_episodes = anime.get('total_episodes', 0)
    
    if is_recent:
        # For recently watched, show last watched info
        last_watched = anime.get('last_watched', 0)
        last_watched_str = ""
        if last_watched:
            from datetime import datetime
            last_watched_dt = datetime.fromtimestamp(last_watched)
            last_watched_str = last_watched_dt.strftime("%b %d, %Y")
            
        label = f"{title} (Watched {progress}{f'/{total_episodes}' if total_episodes else ''} - {last_watched_str})"
        
        # Play from beginning for recently watched
        play_episode = 1
        action = 'play_episode'
    else:
        # For continue watching, show next episode
        next_episode = progress + 1
        label = f"{title} (Ep {next_episode}{f'/{total_episodes}' if total_episodes else ''})"
        play_episode = next_episode
        action = 'play_episode'
    
    # Add progress to description
    description = details.get('description', '')
    if progress > 0 and total_episodes > 0:
        progress_pct = (progress / total_episodes) * 100
        progress_bar = "[" + "■" * int(progress_pct / 5) + "□" * (20 - int(progress_pct / 5)) + "]"
        description = f"{progress_bar} {progress}/{total_episodes} ({progress_pct:.1f}%)\n\n{description}"
    
    # Build context menu
    context_menu = []
    
    if not is_recent:
        # For continue watching, add mark as completed
        context_menu.append((
            "Mark as Completed",
            f'RunPlugin(plugin://{ADDON_ID}/?action=update_status&id={anime_id}&source={source}&status=COMPLETED)'
        ))
    
    # Always add remove from library option
    context_menu.append((
        "Remove from Library",
        f'RunPlugin(plugin://{ADDON_ID}/?action=remove_from_library&id={anime_id}&source={source})'
    ))
    
    # Add view details option
    context_menu.append((
        "View Details",
        f'Container.Update(plugin://{ADDON_ID}/?action=anime_details&id={anime_id}&source={source})'
    ))
    
    # Add to directory
    add_directory_item(
        handle,
        label,
        {
            'action': action,
            'anime_id': anime_id,
            'source': source,
            'episode': play_episode
        },
        details.get('cover_image'),
        description=description,
        context_menu=context_menu if context_menu else None
    )
