"""
player.py: Video player integration for AnimeDB Helper

This module handles video playback with progress tracking and watch status updates.
"""
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import time
import json
from typing import Dict, Any, Optional, Callable

from resources.lib.library import LIBRARY
from resources.lib.api import AnimeDBAPI
from resources.lib.ui_utils import show_progress_notification

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

class AnimePlayer(xbmc.Player):
    """Custom player class to track watch progress and update library."""
    
    def __init__(self, *args, **kwargs):
        """Initialize the player with progress tracking."""
        super(AnimePlayer, self).__init__()
        self.current_item = None
        self.start_time = 0
        self.duration = 0
        self.anime_id = None
        self.source = None
        self.episode = None
        self.total_episodes = None
        self.last_progress_update = 0
        self.watch_threshold = 0.9  # 90% watched to mark as complete
        self.progress_update_interval = 30  # Update progress every 30 seconds
        self.min_watch_time = 60  # Minimum watch time in seconds to count as progress
        
    def play_episode(self, anime_id: str, source: str, episode: int, 
                      url: str, total_episodes: Optional[int] = None) -> None:
        """
        Play an episode and track progress.
        
        Args:
            anime_id: The anime ID
            source: The source service (anilist, mal, etc.)
            episode: The episode number
            url: The video URL to play
            total_episodes: Total number of episodes (optional)
        """
        self.anime_id = anime_id
        self.source = source
        self.episode = int(episode)
        self.total_episodes = int(total_episodes) if total_episodes else None
        
        # Get anime details if needed
        anime = LIBRARY.get_anime_status(anime_id, source)
        if not anime:
            # Add to library if not already there
            LIBRARY.add_to_library(
                anime_id=anime_id,
                source=source,
                status='WATCHING',
                progress=episode - 1,  # Previous episode
                total_episodes=total_episodes
            )
        
        # Play the video
        super().play(item=url)
        
        # Wait for playback to start
        xbmc.sleep(1000)
        
        # Monitor playback
        self._monitor_playback()
    
    def _monitor_playback(self) -> None:
        """Monitor playback progress and update library."""
        if not self.isPlaying():
            return
            
        try:
            # Get video info
            self.duration = self.getTotalTime()
            if self.duration <= 0:
                return
                
            # Start monitoring
            while self.isPlaying():
                current_time = self.getTime()
                progress = (current_time / self.duration) * 100
                
                # Update progress every 10% or when near the end
                if int(progress) % 10 == 0 or progress > 90:
                    self._update_watch_progress(current_time, progress)
                
                xbmc.sleep(1000)  # Check every second
                
        except Exception as e:
            xbmc.log(f"Error monitoring playback: {str(e)}", xbmc.LOGERROR)
        finally:
            self._on_playback_ended()
    
    def _update_watch_progress(self, current_time: float, progress: float) -> None:
        """Update the watch progress in the library."""
        try:
            current_timestamp = time.time()
            
            # Only update if we're past 5% to avoid false starts
            if progress < 5 or current_time < self.min_watch_time:
                return
                
            # Only update at specified intervals or when crossing important thresholds
            update_needed = False
            
            # Check if we need to update based on time interval
            if (current_timestamp - self.last_progress_update) >= self.progress_update_interval:
                update_needed = True
            # Or if we've crossed an important threshold (25%, 50%, 75%, 90%)
            elif progress >= 90 and progress < 95:  # About to mark as watched
                update_needed = True
            elif progress in (25, 50, 75):  # Major progress points
                update_needed = True
                
            if not update_needed:
                return
                
            # Show progress notification at key points
            if progress in (25, 50, 75, 90, 95):
                show_progress_notification(self.episode, progress)
            
            # Update the last progress update time
            self.last_progress_update = current_timestamp
            
            # Mark as watched if we've passed the threshold
            if progress >= (self.watch_threshold * 100):
                try:
                    LIBRARY.mark_episode_watched(
                        anime_id=self.anime_id,
                        source=self.source,
                        episode=self.episode,
                        total_episodes=self.total_episodes
                    )
                    xbmc.log(
                        f"Marked {self.anime_id} episode {self.episode} as watched",
                        xbmc.LOGINFO
                    )
                    # Refresh the container to update the UI
                    xbmc.executebuiltin('Container.Refresh')
                except Exception as e:
                    xbmc.log(f"Error marking episode as watched: {str(e)}", xbmc.LOGERROR)
            else:
                # Update progress in library without marking as watched
                try:
                    LIBRARY.update_episode_progress(
                        anime_id=self.anime_id,
                        source=self.source,
                        episode=self.episode,
                        progress=progress / 100,  # Convert to 0-1 range
                        total_episodes=self.total_episodes
                    )
                except Exception as e:
                    xbmc.log(f"Error updating episode progress: {str(e)}", xbmc.LOGERROR)
                
        except Exception as e:
            xbmc.log(f"Error in _update_watch_progress: {str(e)}", xbmc.LOGERROR)
    
    def _on_playback_ended(self) -> None:
        """Handle playback end or stop."""
        try:
            current_time = self.getTime()
            total_time = self.getTotalTime()
            
            if total_time > 0 and current_time > 0:
                progress = (current_time / total_time) * 100
                
                # If we didn't reach the threshold but watched more than 50%
                if 50 <= progress < (self.watch_threshold * 100):
                    LIBRARY.mark_episode_watched(
                        anime_id=self.anime_id,
                        source=self.source,
                        episode=self.episode,
                        total_episodes=self.total_episodes
                    )
                    
        except Exception as e:
            xbmc.log(f"Error in playback ended handler: {str(e)}", xbmc.LOGERROR)

# Global player instance
PLAYER = AnimePlayer()

def play_episode(anime_id: str, source: str, episode: int, url: str, 
                total_episodes: Optional[int] = None) -> None:
    """
    Play an episode with progress tracking.
    
    Args:
        anime_id: The anime ID
        source: The source service (anilist, mal, etc.)
        episode: The episode number
        url: The video URL to play
        total_episodes: Total number of episodes (optional)
    """
    try:
        # Start playback with tracking
        PLAYER.play_episode(
            anime_id=anime_id,
            source=source,
            episode=episode,
            url=url,
            total_episodes=total_episodes
        )
    except Exception as e:
        xbmc.log(f"Error playing episode: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Playback Error",
            "Failed to start playback",
            xbmcgui.NOTIFICATION_ERROR
        )

def mark_episode_watched(anime_id: str, source: str, episode: int, 
                       total_episodes: Optional[int] = None) -> None:
    """
    Mark an episode as watched manually.
    
    Args:
        anime_id: The anime ID
        source: The source service (anilist, mal, etc.)
        episode: The episode number
        total_episodes: Total number of episodes (optional)
    """
    try:
        success = LIBRARY.mark_episode_watched(
            anime_id=anime_id,
            source=source,
            episode=episode,
            total_episodes=total_episodes
        )
        
        if success:
            xbmcgui.Dialog().notification(
                "Marked as Watched",
                f"Episode {episode} marked as watched",
                xbmcgui.NOTIFICATION_INFO
            )
            
            # Refresh the current container to update the UI
            xbmc.executebuiltin('Container.Refresh')
            
    except Exception as e:
        xbmc.log(f"Error marking episode as watched: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Error",
            "Failed to update watch status",
            xbmcgui.NOTIFICATION_ERROR
        )
