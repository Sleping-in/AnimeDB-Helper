"""
UI Utilities for AnimeDB Helper

This module contains helper functions for UI-related operations.
"""
import xbmc
import xbmcgui
import xbmcaddon
from typing import Dict, Any, Optional, List, Tuple

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

def get_episode_display_name(episode: Dict[str, Any], watched_episodes: List[int] = None) -> str:
    """
    Generate a display name for an episode with progress indicator.
    
    Args:
        episode: Dictionary containing episode details
        watched_episodes: List of watched episode numbers
        
    Returns:
        Formatted episode name with progress indicator
    """
    episode_number = episode.get('number', 0)
    episode_title = episode.get('title', f'Episode {episode_number}')
    
    # Check if episode is watched
    is_watched = watched_episodes and episode_number in watched_episodes
    
    # Add progress indicator
    if is_watched:
        return f"✓ {episode_number}. {episode_title}"
    return f"{episode_number}. {episode_title}"

def create_episode_list_item(episode: Dict[str, Any], show_title: str, watched_episodes: List[int] = None,
                           progress: Optional[float] = None) -> xbmcgui.ListItem:
    """
    Create a list item for an episode with progress indicator.
    
    Args:
        episode: Dictionary containing episode details
        show_title: Title of the show
        watched_episodes: List of watched episode numbers
        progress: Optional progress percentage (0-100)
        
    Returns:
        xbmcgui.ListItem: Configured list item
    """
    episode_number = episode.get('number', 0)
    is_watched = watched_episodes and episode_number in watched_episodes
    
    # Create list item with progress indicator
    display_name = get_episode_display_name(episode, watched_episodes)
    li = xbmcgui.ListItem(display_name)
    
    # Set additional properties for watched status
    if is_watched:
        li.setProperty('IsPlayable', 'false')
        li.setProperty('IsWatched', 'true')
    else:
        li.setProperty('IsPlayable', 'true')
        li.setProperty('IsWatched', 'false')
    
    # Set progress property if available
    if progress is not None:
        li.setProperty('ResumeTime', str(progress))
        li.setProperty('TotalTime', '100')  # 100% as base
    
    return li

def show_progress_notification(episode_number: int, progress: float):
    """
    Show a notification for episode progress.
    
    Args:
        episode_number: Episode number
        progress: Progress percentage (0-100)
    """
    if progress >= 90:
        message = f"Marked episode {episode_number} as watched"
    else:
        message = f"Watched {int(progress)}% of episode {episode_number}"
    
    xbmcgui.Dialog().notification(
        "Watch Progress",
        message,
        xbmcgui.NOTIFICATION_INFO,
        3000  # 3 seconds
    )
