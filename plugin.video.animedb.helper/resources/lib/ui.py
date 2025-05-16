"""
ui.py: Kodi UI navigation and directory listing for the AnimeDB Helper plugin.

This module provides all user-facing directory and detail views, including anime lists, details, genres, watchlists, history,
and search. It integrates with the API and player systems, and handles all Kodi plugin UI actions.
"""
import sys
import xbmcplugin
import xbmcgui
import xbmc
import xbmcaddon
import xbmcvfs
from urllib.parse import urlencode, parse_qs

from resources.lib.api import AnimeDBAPI
from resources.lib.fanart import fetch_art

from resources.lib.history import get_watch_history, get_continue_watching

def list_last_watched(handle):
    """
    Show the most recently watched episode
    """
    history = get_watch_history(limit=1)
    if not history:
        xbmcgui.Dialog().notification("Last Watched", "No watch history found.", xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.endOfDirectory(handle)
        return
    item = history[0]
    anime_id = item['id']
    episode = item['episode']
    source = item.get('source', 'anilist')
    # Fetch anime details
    api = AnimeDBAPI()
    details = api.anime_details(anime_id, source)
    if not details:
        xbmcgui.Dialog().notification("Last Watched", "Could not fetch anime details.", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle)
        return
    # Compose label
    label = f"{details.get('title', '')} - Episode {episode}"
    li = xbmcgui.ListItem(label)
    li.setInfo('video', {'title': details.get('title', ''), 'episode': episode})
    url = f"plugin://{ADDON_ID}/?action=play_item_route&id={anime_id}&source={source}&episode={episode}"
    xbmcplugin.addDirectoryItem(handle, url, li, isFolder=False)
    xbmcplugin.endOfDirectory(handle)

from resources.lib.recommendations import get_recommendations, get_similar_anime
from resources.lib.upcoming import get_upcoming, get_calendar
from resources.lib.watchlist import get_local_watchlist, is_in_watchlist, toggle_watchlist

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Create API instance
API = AnimeDBAPI()

def list_anime(handle, anime_list, title=None):
    """
    Show a list of anime with Arctic Fuse 2 optimizations
    """
    # Set content type
    xbmcplugin.setContent(handle, 'tvshows')
    
    # Set category
    if title:
        xbmcplugin.setPluginCategory(handle, title)
    
    from resources.lib.tmdb_bridge import get_tmdb_api, find_tmdb_id
    for anime in anime_list:
        title = anime.get('title', '')
        anime_id = anime.get('id', '')
        source = anime.get('source', 'anilist')

        # Try TMDB first
        tmdb_api = get_tmdb_api()
        tmdb_meta = None
        if tmdb_api:
            tmdb_id = find_tmdb_id(title)
            if tmdb_id:
                try:
                    tmdb_meta = tmdb_api.get_tv_details(tmdb_id)
                except Exception:
                    tmdb_meta = None
        # Compose artwork and info
        art = {}
        fallback_img = xbmcvfs.translatePath('special://home/addons/' + ADDON_ID + '/resources/media/studio_fallback.png')
        if tmdb_meta:
            art['poster'] = tmdb_meta.get('poster_path') and tmdb_api.IMAGE_BASE + tmdb_meta['poster_path'] or ''
            art['fanart'] = tmdb_meta.get('backdrop_path') and tmdb_api.IMAGE_BASE + tmdb_meta['backdrop_path'] or ''
            art['banner'] = tmdb_meta.get('backdrop_path') and tmdb_api.IMAGE_BASE + tmdb_meta['backdrop_path'] or ''
            art['landscape'] = tmdb_meta.get('backdrop_path') and tmdb_api.IMAGE_BASE + tmdb_meta['backdrop_path'] or ''
            art['clearlogo'] = ''
        else:
            # AniList fallback
            art = fetch_art(anime_id, source)
            if 'poster' in anime and anime['poster']:
                art['poster'] = anime['poster']
            if not art.get('poster'):
                art['poster'] = fallback_img
            if 'banner' in anime and anime['banner']:
                art['fanart'] = anime['banner']
                art['banner'] = anime['banner']
                art['landscape'] = anime['banner']
            if not art.get('fanart'):
                art['fanart'] = fallback_img
            if not art.get('banner'):
                art['banner'] = fallback_img
            if not art.get('landscape'):
                art['landscape'] = fallback_img
            if not art.get('clearlogo'):
                art['clearlogo'] = fallback_img
        # Create list item
        li = xbmcgui.ListItem(title)
        # Set info
        info = {'title': title, 'mediatype': 'tvshow'}
        # Plot/description
        if tmdb_meta and tmdb_meta.get('overview'):
            info['plot'] = tmdb_meta['overview']
        elif ADDON.getSettingBool('show_plot') and 'description' in anime:
            info['plot'] = anime.get('description', '')
        # Score/rating
        if tmdb_meta and tmdb_meta.get('vote_average'):
            info['rating'] = tmdb_meta['vote_average']
        elif ADDON.getSettingBool('show_score') and 'score' in anime:
            score = anime.get('score')
            if score is not None:
                info['rating'] = score / 10.0  # Convert to 0-10 scale
            else:
                info['rating'] = 0.0
        
        # Add year if available
        if 'season_year' in anime:
            info['year'] = anime.get('season_year', 0)
        
        # Add genres if available
        if 'genres' in anime:
            info['genre'] = ', '.join(anime.get('genres', []))
        
        # Use InfoTagVideo for video properties
        info_tag = li.getVideoInfoTag()
        if 'title' in info:
            info_tag.setTitle(info['title'])
        if 'plot' in info:
            info_tag.setPlot(info['plot'])
        if 'rating' in info:
            info_tag.setRating(info['rating'])
        if 'year' in info:
            info_tag.setYear(info['year'])
        if 'genre' in info:
            info_tag.setGenres(info['genre'].split(', ') if isinstance(info['genre'], str) else info['genre'])
        # Add other properties as needed
        
        # Set artwork
        li.setArt({
            'poster': art.get('poster', ''),
            'fanart': art.get('fanart', ''),
            'banner': art.get('banner', ''),
            'clearlogo': art.get('clearlogo', ''),
            'landscape': art.get('landscape', ''),
            'thumb': art.get('poster', '')
        })
        
        # Set default click: open episode list for TV/ONA/TV_SHORT/SPECIAL, open details for others
        anime_format = anime.get('format', '').upper()
        if anime_format in ['TV', 'TV_SHORT', 'ONA', 'SPECIAL']:
            url = f"plugin://{ADDON_ID}/?action=list_episodes&id={anime_id}&source={source}&title={title}"
        else:
            url = f"plugin://{ADDON_ID}/?action=details&id={anime_id}&source={source}"
        
        # Add context menu items
        context_items = []
        
        # Add "Play" option to context menu that shows episode list
        context_items.append((
            'Play',
            f"Container.Update(plugin://{ADDON_ID}/?action=list_episodes&id={anime_id}&source={source}&title={title})"
        ))
        
        # Add direct play option (for non-TV shows)
        context_items.append((
            'Play Directly',
            f"RunPlugin(plugin://{ADDON_ID}/?action=play_item_route&id={anime_id}&source={source}&episode=1)"
        ))
        
        # Add "Toggle Watchlist" option
        if is_in_watchlist(anime_id, source):
            context_items.append((
                'Remove from Watchlist',
                f"RunPlugin(plugin://{ADDON_ID}/?action=toggle_watchlist&id={anime_id}&source={source})"
            ))
        else:
            context_items.append((
                'Add to Watchlist',
                f"RunPlugin(plugin://{ADDON_ID}/?action=toggle_watchlist&id={anime_id}&source={source})"
            ))
        
        # Add "Similar Anime" option
        context_items.append((
            'Similar Anime',
            f"Container.Update(plugin://{ADDON_ID}/?action=similar&id={anime_id}&source={source}&title={title})"
        ))
        
        # Set context menu
        li.addContextMenuItems(context_items)
        
        # Set properties for Arctic Fuse 2
        li.setProperty("AnimeDB.ID", anime_id)
        li.setProperty("AnimeDB.Source", source)
        if 'score' in anime:
            li.setProperty("AnimeDB.Rating", str(anime.get('score', 0)))
        
        # Add to directory
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    # Add sort methods
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    
    # Set view mode
    set_view_mode('tvshows')

# --- PLACEHOLDER UI FUNCTIONS FOR NAVIGATION ---
def home(handle):
    # Show a main menu with navigation options
    ADDON = xbmcaddon.Addon()
    ADDON_ID = ADDON.getAddonInfo('id')
    menu_items = [
        {'label': 'Recommended Anime', 'action': 'recommendations'},
        {'label': 'Watchlist', 'action': 'watchlist'},
        {'label': 'Trending', 'action': 'trending'},
        {'label': 'Genres', 'action': 'genres'},
        {'label': 'Search', 'action': 'search'},
        {'label': 'History', 'action': 'history'},
        {'label': 'Continue Watching', 'action': 'continue_watching'},
        {'label': 'Upcoming', 'action': 'upcoming'},
        {'label': 'Calendar', 'action': 'calendar'},
        {'label': 'Settings', 'action': 'settings'}
    ]
    for item in menu_items:
        url = sys.argv[0] + '?' + urlencode({'action': item['action']})
        li = xbmcgui.ListItem(item['label'])
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    xbmcplugin.setPluginCategory(handle, 'AnimeDB Main Menu')
    xbmcplugin.setContent(handle, 'addons')
    xbmcplugin.endOfDirectory(handle)


def list_watchlist(handle):
    # Show user's AniList watchlist
    anime_list = API.anilist_watchlist()
    list_anime(handle, anime_list, title='Watchlist')

def show_settings_menu(handle):
    # Display settings menu for player configurations
    player_name = ADDON.getSetting('player_name')
    plugin_id = ADDON.getSetting('plugin_id')
    command = ADDON.getSetting('command')
    is_resolvable = ADDON.getSetting('is_resolvable')

    # Create dialog for user input
    dialog = xbmcgui.Dialog()
    new_name = dialog.input('Enter Player Name', defaultt=player_name)
    new_plugin_id = dialog.input('Enter Plugin ID', defaultt=plugin_id)
    new_command = dialog.input('Enter Command', defaultt=command)
    new_is_resolvable = dialog.yesno('Is Resolvable?', yeslabel='Yes', nolabel='No', defaultt=is_resolvable.lower() == 'true')

    # Save new settings
    ADDON.setSetting('player_name', new_name)
    ADDON.setSetting('plugin_id', new_plugin_id)
    ADDON.setSetting('command', new_command)
    ADDON.setSetting('is_resolvable', 'true' if new_is_resolvable else 'false')
    xbmcgui.Dialog().notification('Settings', 'Player settings updated successfully.', xbmcgui.NOTIFICATION_INFO)
    xbmcplugin.setPluginCategory(handle, 'Continue Watching')
    xbmcplugin.endOfDirectory(handle)

def list_genres(handle):
    # Fetch genres dynamically from AniList
    genres = API.genres()
    xbmcplugin.setPluginCategory(handle, 'Genres')
    for genre in genres:
        url = sys.argv[0] + '?' + urlencode({'action': 'list_genre', 'genre': genre})
        li = xbmcgui.ListItem(genre)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    xbmcplugin.endOfDirectory(handle)

def list_genre(handle, genre):
    # Show anime for a specific genre using the API's genre method
    anime_list = API.genre(genre)
    list_anime(handle, anime_list, title=f'Genre: {genre}')

def list_history(handle):
    # Show recently watched anime
    anime_list = get_watch_history()
    list_anime(handle, anime_list, title='History')

def list_continue_watching(handle):
    from resources.lib.history import get_continue_watching
    anime_list = get_continue_watching()
    if not anime_list:
        xbmcgui.Dialog().notification("AnimeDB", "No continue watching items found", xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setPluginCategory(handle, 'Continue Watching')
        xbmcplugin.endOfDirectory(handle)
        return
    list_anime(handle, anime_list, title='Continue Watching')

def list_upcoming(handle):
    from resources.lib.upcoming import get_upcoming
    anime_list = get_upcoming()
    if not anime_list:
        xbmcgui.Dialog().notification("AnimeDB", "No upcoming episodes found", xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setPluginCategory(handle, 'Upcoming')
        xbmcplugin.endOfDirectory(handle)
        return
    list_anime(handle, anime_list, title='Upcoming')

def list_calendar(handle):
    from resources.lib.upcoming import get_calendar
    calendar_items = get_calendar()
    if not calendar_items:
        xbmcgui.Dialog().notification("AnimeDB", "No calendar items found", xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setPluginCategory(handle, 'Calendar')
        xbmcplugin.endOfDirectory(handle)
        return
    # Implement calendar listing logic here
    xbmcplugin.setPluginCategory(handle, 'Calendar')
    xbmcplugin.endOfDirectory(handle)

def list_calendar_date(handle, date):
    from resources.lib.upcoming import get_calendar
    calendar_items = get_calendar(date)
    if not calendar_items:
        xbmcgui.Dialog().notification("AnimeDB", f"No calendar items found for {date}", xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setPluginCategory(handle, f'Calendar: {date}')
        xbmcplugin.endOfDirectory(handle)
        return
    # Implement calendar date listing logic here
    xbmcplugin.setPluginCategory(handle, f'Calendar: {date}')
    xbmcplugin.endOfDirectory(handle)

def search(handle):
    # Prompt for a search term and show results
    term = xbmcgui.Dialog().input('Search Anime')
    if not term:
        xbmcplugin.endOfDirectory(handle)
        return
    anime_list = API.search(term)
    list_anime(handle, anime_list, title=f'Search: {term}')

def set_skin_properties():
    pass

# --- END PLACEHOLDERS ---

def show_anime_details(anime_id, source='anilist'):
    """
    Show detailed information about an anime and its episodes
    """
    from resources.lib.tmdb_bridge import get_tmdb_api, find_tmdb_id
    # Get AniList details as fallback
    details = API.anime_details(anime_id, source)
    tmdb_api = get_tmdb_api()
    tmdb_meta = None
    if tmdb_api and details:
        tmdb_id = find_tmdb_id(details.get('title', ''))
        if tmdb_id:
            try:
                tmdb_meta = tmdb_api.get_tv_details(tmdb_id)
            except Exception:
                tmdb_meta = None
    # Compose info
    info = []
    # Title
    show_title = tmdb_meta['name'] if tmdb_meta and tmdb_meta.get('name') else details.get('title', 'Unknown')
    info.append(f"Title: {show_title}")
    # Original title
    if tmdb_meta and tmdb_meta.get('original_name'):
        info.append(f"Original Title: {tmdb_meta['original_name']}")
    elif details.get('original_title'):
        info.append(f"Original Title: {details.get('original_title', '')}")
    # Format
    if details.get('format'):
        info.append(f"Format: {details.get('format', '')}")
    # Status
    if tmdb_meta and tmdb_meta.get('status'):
        info.append(f"Status: {tmdb_meta['status']}")
    elif details.get('status'):
        info.append(f"Status: {details.get('status', '')}")
    # Duration
    if details.get('duration'):
        info.append(f"Duration: {details.get('duration', 0)} minutes")
    # Genres
    if tmdb_meta and tmdb_meta.get('genres'):
        genres = ', '.join([g['name'] for g in tmdb_meta['genres']])
        info.append(f"Genres: {genres}")
    elif details.get('genres'):
        info.append(f"Genres: {', '.join(details.get('genres', []))}")
    # Score/rating
    if tmdb_meta and tmdb_meta.get('vote_average'):
        info.append(f"Rating: {tmdb_meta['vote_average']}/10")
    elif details.get('score'):
        info.append(f"Score: {details.get('score', 0)}/100")
    # Dates
    if tmdb_meta and tmdb_meta.get('first_air_date'):
        info.append(f"First Air Date: {tmdb_meta['first_air_date']}")
    elif details.get('start_date'):
        info.append(f"Start Date: {details.get('start_date', '')}")
    if tmdb_meta and tmdb_meta.get('last_air_date'):
        info.append(f"Last Air Date: {tmdb_meta['last_air_date']}")
    elif details.get('end_date'):
        info.append(f"End Date: {details.get('end_date', '')}")
    # Studios
    if tmdb_meta and tmdb_meta.get('production_companies'):
        studios = ', '.join([s['name'] for s in tmdb_meta['production_companies']])
        info.append(f"Studios: {studios}")
    elif details.get('studios'):
        info.append(f"Studios: {', '.join(details.get('studios', []))}")
    # Description/overview
    if tmdb_meta and tmdb_meta.get('overview'):
        info.append(f"\nDescription:\n{tmdb_meta['overview']}")
    elif details.get('description'):
        info.append(f"\nDescription:\n{details.get('description', '')}")
    # For TV shows, show episode list directly
    if details.get('format') in ['TV', 'TV_SHORT', 'ONA', 'SPECIAL']:
        xbmc.executebuiltin(f"Container.Update(plugin://{ADDON_ID}/?action=list_episodes&id={anime_id}&source={source}&title={show_title})")
        return
    # Create dialog with play option
    dialog = xbmcgui.Dialog()
    ret = dialog.select(
        show_title,
        ["Play"] + info
    )
    if ret == 0:  # Play button was clicked
        xbmc.executebuiltin(f"RunPlugin(plugin://{ADDON_ID}/?action=play_item_route&id={anime_id}&source={source}&episode=1")

def set_view_mode(content_type):
    """
    Set the appropriate view mode for Arctic Fuse 2
    """
    view_mode = {
        'tvshows': 55,  # List view for TV shows
        'episodes': 55,  # List view for episodes
        'movies': 50,    # Poster view for movies
    }.get(content_type, 50)  # Default to poster view
    
    xbmc.executebuiltin(f'Container.SetViewMode({view_mode})')

# [Rest of the file remains the same...]
