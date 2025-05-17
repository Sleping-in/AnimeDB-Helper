"""
AnimeDB Helper - Core Package

This package contains all the core functionality for the AnimeDB Helper addon.
"""

# Import core modules to make them available at the package level
from resources.lib.api import API, AnimeDBAPI
from resources.lib.library import LIBRARY, show_library, show_continue_watching
from resources.lib.player import PLAYER, play_episode, mark_episode_watched
from resources.lib.ui_utils import (
    get_episode_display_name, create_episode_list_item, show_progress_notification
)
from resources.lib.ui import (
    home, list_trending, list_seasonal, list_genres, list_genre,
    search, show_anime_details, list_episodes, play_item_route
)

__all__ = [
    # Core API
    'API', 'AnimeDBAPI',
    
    # Library
    'LIBRARY', 'show_library', 'show_continue_watching',
    
    # Player
    'PLAYER', 'play_episode', 'mark_episode_watched',
    
    # UI
    'home', 'list_trending', 'list_seasonal', 'list_genres', 'list_genre',
    'search', 'show_anime_details', 'list_episodes', 'play_item_route',
    
    # UI Utilities
    'get_episode_display_name', 'create_episode_list_item', 'show_progress_notification'
]
