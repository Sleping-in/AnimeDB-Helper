"""
Test script for AnimeDB Helper Player functionality.

This script tests the player module's ability to track watch progress and update the library.
"""
import unittest
from unittest.mock import MagicMock, patch

# Import the player module
from resources.lib.player import AnimePlayer, PLAYER, play_episode, mark_episode_watched
from resources.lib.library import LIBRARY

class TestAnimePlayer(unittest.TestCase):
    """Test cases for the AnimePlayer class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.player = AnimePlayer()
        self.anime_id = "12345"
        self.source = "anilist"
        self.episode = 5
        self.url = "plugin://test/play/anime/12345/5"
        self.total_episodes = 12
        
        # Mock the Kodi player methods
        self.player.isPlaying = MagicMock(return_value=True)
        self.player.getTime = MagicMock(return_value=120)  # 2 minutes
        self.player.getTotalTime = MagicMock(return_value=1200)  # 20 minutes
        
        # Mock the LIBRARY methods
        LIBRARY.get_anime_status = MagicMock(return_value=None)
        LIBRARY.add_to_library = MagicMock(return_value=True)
        LIBRARY.mark_episode_watched = MagicMock(return_value=True)
    
    def test_play_episode(self):
        """Test playing an episode with progress tracking."""
        # Call the play_episode function
        play_episode(
            anime_id=self.anime_id,
            source=self.source,
            episode=self.episode,
            url=self.url,
            total_episodes=self.total_episodes
        )
        
        # Verify that the player was called with the correct URL
        self.player.play.assert_called_once_with(item=self.url)
        
        # Verify that the anime was added to the library
        LIBRARY.add_to_library.assert_called_once_with(
            anime_id=self.anime_id,
            source=self.source,
            status='WATCHING',
            progress=self.episode - 1,
            total_episodes=self.total_episodes
        )
    
    @patch('xbmc.sleep')
    def test_monitor_playback(self, mock_sleep):
        """Test monitoring playback progress."""
        # Set up the player state
        self.player.anime_id = self.anime_id
        self.player.source = self.source
        self.player.episode = self.episode
        self.player.total_episodes = self.total_episodes
        
        # Simulate playback monitoring
        self.player._monitor_playback()
        
        # Verify that the episode was marked as watched (progress > 90%)
        LIBRARY.mark_episode_watched.assert_called_once_with(
            anime_id=self.anime_id,
            source=self.source,
            episode=self.episode,
            total_episodes=self.total_episodes
        )
    
    def test_mark_episode_watched(self):
        """Test manually marking an episode as watched."""
        # Call the mark_episode_watched function
        mark_episode_watched(
            anime_id=self.anime_id,
            source=self.source,
            episode=self.episode,
            total_episodes=self.total_episodes
        )
        
        # Verify that the episode was marked as watched
        LIBRARY.mark_episode_watched.assert_called_once_with(
            anime_id=self.anime_id,
            source=self.source,
            episode=self.episode,
            total_episodes=self.total_episodes
        )

if __name__ == "__main__":
    unittest.main()
