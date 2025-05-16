## Recent Changes

### May 15, 2025
- Improved error handling in critical modules (`api.py`, `auth.py`, `episodes_new.py`).
- Implemented logic for `sync_ratings` in `sync.py`.
- Added input validation to `ListItem` in `players.py`.
- Enhanced test discovery by adding `__init__.py` to the `tests/` directory.

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   ```

2. Navigate to the plugin directory:
   ```bash
   cd plugin.video.animedb.helper
   ```

3. Install dependencies (if any):
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Copy the `plugin.video.animedb.helper` folder to your Kodi add-ons directory.
2. Restart Kodi to load the plugin.
3. Configure the plugin settings as needed.

## Features

- Unified anime metadata and watchlist integration from AniList, MyAnimeList, and Trakt
- Flexible player system with support for external and internal players, resume, and player selection
- Modern Kodi UI navigation: watchlists, genres, history, trending, seasonal, and search
- Robust caching and error handling for all API calls
- Fully compatible with Kodi Omega (v21+) and xbmcvfs file I/O
- Extensible: add new players or providers via JSON configuration

## Configuration