# AnimeDB Helper - Player Module

This document provides an overview of the player functionality in the AnimeDB Helper addon, including how it tracks watch progress and updates the user's library.

## Features

- **Progress Tracking**: Automatically tracks how much of an episode has been watched
- **Continue Watching**: Keeps track of partially watched episodes
- **Library Integration**: Updates the user's library with watch status and progress
- **Manual Controls**: Allows manually marking episodes as watched/unwatched

## How It Works

### Player Initialization

The `AnimePlayer` class extends Kodi's `xbmc.Player` to add progress tracking functionality. When an episode is played, the player:

1. Records the start time and duration
2. Monitors playback progress
3. Updates the library when significant progress is made (e.g., 90% watched)
4. Handles playback completion and errors

### Playback Flow

1. **Starting Playback**:
   ```python
   from resources.lib.player import play_episode
   
   play_episode(
       anime_id="12345",
       source="anilist",
       episode=5,
       url="plugin://plugin.video.example/play/12345/5",
       total_episodes=12
   )
   ```

2. **Monitoring Progress**:
   - The player checks progress every second
   - When progress reaches certain thresholds (e.g., 10%, 20%, etc.), it updates the library
   - If the user watches more than 90% of an episode, it's marked as watched

3. **Manual Control**:
   ```python
   from resources.lib.player import mark_episode_watched
   
   mark_episode_watched(
       anime_id="12345",
       source="anilist",
       episode=5,
       total_episodes=12
   )
   ```

## Integration with Other Components

### Library Integration

The player updates the user's library through the `LIBRARY` singleton. It calls:
- `LIBRARY.add_to_library()` when starting a new anime
- `LIBRARY.mark_episode_watched()` when an episode is fully or mostly watched

### UI Updates

The player triggers UI updates by:
- Broadcasting Kodi notifications for important events
- Refreshing the current container when watch status changes
- Updating the "Continue Watching" section

## Testing

A test suite is available to verify the player's functionality:

```bash
python -m unittest test_player.py
```

## Best Practices

1. **Error Handling**: Always wrap player calls in try/except blocks
2. **Progress Thresholds**: Use reasonable thresholds for marking progress
3. **User Feedback**: Provide visual feedback for important actions
4. **Performance**: Be mindful of how often you update the library during playback

## Troubleshooting

- **Playback Not Starting**: Check that the URL is valid and the source is accessible
- **Progress Not Updating**: Verify that the player has proper permissions to update the library
- **Incorrect Watch Status**: Check the library database for inconsistencies

## Future Improvements

- Add support for multiple video sources
- Implement more granular progress tracking
- Add support for syncing progress with external services (e.g., AniList, MyAnimeList)
