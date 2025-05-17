"""
ui.py: Kodi UI navigation and directory listing for the AnimeDB Helper plugin.

This module provides all user-facing directory and detail views, including anime lists, details, genres, watchlists, history,
and search. It integrates with the API and player systems, and handles all Kodi plugin UI actions.
"""
import os
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
ADDON_PATH = ADDON.getAddonInfo('path')

# Create API instance
API = AnimeDBAPI()

def add_directory_item(handle, label, params, icon_image=None, is_folder=True, fanart=None, description=None, context_menu=None):
    """
    Helper function to add a directory item to the Kodi interface
    
    Args:
        handle: Kodi plugin handle
        label: Item label
        params: Dictionary of URL parameters
        icon_image: Optional icon image filename (will be prefixed with addon path)
        is_folder: Whether this item is a folder
        fanart: Optional fanart image path
        description: Optional description text
        context_menu: List of (label, action) tuples for context menu items
    """
    # Create list item
    li = xbmcgui.ListItem(label)
    
    # Set icon and fanart
    if icon_image:
        # Check if it's a full path or just a filename
        if not icon_image.startswith(('http://', 'https://', 'special://', '/')):
            icon_image = os.path.join(ADDON_PATH, 'resources', 'media', icon_image)
        li.setArt({'icon': icon_image, 'thumb': icon_image})
    
    if fanart:
        li.setProperty('fanart_image', fanart)
    
    # Set info
    info_labels = {'title': label}
    if description:
        info_labels['plot'] = description
    li.setInfo('video', info_labels)
    
    # Add context menu items if provided
    if context_menu:
        li.addContextMenuItems(context_menu)
    
    # Build URL
    url = f'plugin://{ADDON_ID}/?{urlencode(params)}'
    
    # Add to directory
    xbmcplugin.addDirectoryItem(
        handle=handle,
        url=url,
        listitem=li,
        isFolder=is_folder
    )
    
    return li

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
    

# --- PLACEHOLDER UI FUNCTIONS FOR NAVIGATION ---
def home(handle):
    """Show the main menu with all available sections"""
    # Set content type
    xbmcplugin.setContent(handle, 'files')
    
    # Add menu items
    add_directory_item(handle, 'Continue Watching', {'action': 'continue_watching'}, 'continue.png')
    add_directory_item(handle, 'My Library', {'action': 'library'}, 'library.png')
    add_directory_item(handle, 'Watchlist', {'action': 'watchlist'}, 'watchlist.png')
    add_directory_item(handle, 'Trending Now', {'action': 'trending'}, 'trending.png')
    add_directory_item(handle, 'Current Season', {'action': 'seasonal'}, 'seasonal.png')
    add_directory_item(handle, 'Search', {'action': 'search_menu'}, 'search.png')
    add_directory_item(handle, 'History', {'action': 'history'}, 'history.png')
    add_directory_item(handle, 'Upcoming', {'action': 'upcoming'}, 'upcoming.png')
    add_directory_item(handle, 'Calendar', {'action': 'calendar'}, 'calendar.png')
    add_directory_item(handle, 'Genres', {'action': 'genres'}, 'genres.png')
    add_directory_item(handle, 'Settings', {'action': 'settings'}, 'settings.png')
    
    # Set view mode
    set_view_mode('list')
    xbmcplugin.endOfDirectory(handle)

def list_trending(handle, page=1, source=None):
    """
    Display trending anime from the specified source
    
    Args:
        handle: Kodi plugin handle
        page: Page number (1-based)
        source: Data source ('anilist', 'mal', or 'trakt'). If None, uses addon settings
    """
    if source is None:
        source = ADDON.getSetting('default_source') or 'anilist'
    
    # Get trending anime
    anime_list = API.get_trending_anime(page=page, per_page=int(ADDON.getSetting('items_per_page') or 20), source=source)
    
    if not anime_list and page == 1:
        xbmcgui.Dialog().notification('No Results', 'No trending anime found', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Add items to directory
    list_anime(handle, anime_list, f'Trending on {source.upper()}')
    
    # Add pagination if needed
    if len(anime_list) >= int(ADDON.getSetting('items_per_page') or 20):
        next_page = page + 1
        add_directory_item(
            handle,
            f'Next Page ({next_page})',
            {'action': 'trending', 'page': next_page, 'source': source},
            'next.png',
            is_folder=True
        )
    
    # Add source selector
    add_source_selector(handle, 'trending', page, source)
    
    xbmcplugin.endOfDirectory(handle)

def list_seasonal(handle, year=None, season=None, page=1, source=None):
    """
    Display seasonal anime from the specified source
    
    Args:
        handle: Kodi plugin handle
        year: Year of the season
        season: Season name ('WINTER', 'SPRING', 'SUMMER', 'FALL')
        page: Page number (1-based)
        source: Data source ('anilist', 'mal', or 'trakt'). If None, uses addon settings
    """
    if source is None:
        source = ADDON.getSetting('default_source') or 'anilist'
    
    # Get seasonal anime
    anime_list = API.get_seasonal_anime(
        year=year,
        season=season,
        page=page,
        per_page=int(ADDON.getSetting('items_per_page') or 20),
        source=source
    )
    
    if not anime_list and page == 1:
        xbmcgui.Dialog().notification('No Results', 'No seasonal anime found', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Determine season title
    if season and year:
        season_title = f'{season.capitalize()} {year}'
    else:
        # Auto-detect current season if not specified
        import datetime
        now = datetime.datetime.now()
        month = now.month
        year = now.year
        
        if month in [12, 1, 2]:
            season = 'WINTER'
        elif month in [3, 4, 5]:
            season = 'SPRING'
        elif month in [6, 7, 8]:
            season = 'SUMMER'
        else:
            season = 'FALL'
        
        # Adjust year for winter season
        if month == 12:
            year += 1
            
        season_title = f'{season.capitalize()} {year}'
    
    # Add items to directory
    list_anime(handle, anime_list, f'{season_title} Anime on {source.upper()}')
    
    # Add pagination if needed
    if len(anime_list) >= int(ADDON.getSetting('items_per_page') or 20):
        next_page = page + 1
        add_directory_item(
            handle,
            f'Next Page ({next_page})',
            {'action': 'seasonal', 'year': year, 'season': season, 'page': next_page, 'source': source},
            'next.png',
            is_folder=True
        )
    
    # Add season selector
    add_season_selector(handle, year, season, source)
    
    # Add source selector
    add_source_selector(handle, 'seasonal', page, source, {'year': year, 'season': season})
    
    xbmcplugin.endOfDirectory(handle)

def add_season_selector(handle, current_year, current_season, source):
    """Add season navigation to the directory"""
    import datetime
    now = datetime.datetime.now()
    
    # Add previous/next season navigation
    seasons = ['WINTER', 'SPRING', 'SUMMER', 'FALL']
    current_season_idx = seasons.index(current_season.upper()) if current_season.upper() in seasons else 0
    
    # Previous season
    prev_season_idx = (current_season_idx - 1) % 4
    prev_season_year = current_year - 1 if current_season_idx == 0 and prev_season_idx == 3 else current_year
    add_directory_item(
        handle,
        f'← {seasons[prev_season_idx].capitalize()} {prev_season_year}',
        {'action': 'seasonal', 'year': prev_season_year, 'season': seasons[prev_season_idx], 'source': source},
        'previous.png',
        is_folder=True
    )
    
    # Next season
    next_season_idx = (current_season_idx + 1) % 4
    next_season_year = current_year + 1 if current_season_idx == 3 and next_season_idx == 0 else current_year
    add_directory_item(
        handle,
        f'{seasons[next_season_idx].capitalize()} {next_season_year} →',
        {'action': 'seasonal', 'year': next_season_year, 'season': seasons[next_season_idx], 'source': source},
        'next.png',
        is_folder=True
    )
    
    # Add year selector
    for year in range(now.year, now.year - 5, -1):
        for season in seasons:
            if year == current_year and season == current_season.upper():
                continue
                
            add_directory_item(
                handle,
                f'{season.capitalize()} {year}',
                {'action': 'seasonal', 'year': year, 'season': season, 'source': source},
                'calendar.png',
                is_folder=True
            )

def add_source_selector(handle, action, page, current_source, extra_params=None):
    """Add source selector to the directory"""
    if extra_params is None:
        extra_params = {}
        
    sources = [
        ('AniList', 'anilist'),
        ('MyAnimeList', 'mal'),
        ('Trakt', 'trakt')
    ]
    
    for name, source in sources:
        if source == current_source:
            continue
            
        params = {'action': action, 'page': page, 'source': source, **extra_params}
        add_directory_item(
            handle,
            f'Switch to {name}',
            params,
            f'source_{source}.png',
            is_folder=True
        )


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
    """
    List all available anime genres with counts
    """
    try:
        xbmcplugin.setPluginCategory(handle, 'Genres')
        xbmcplugin.setContent(handle, 'genres')
        
        api = AnimeDBAPI()
        genres = api.get_genres()
        
        if not genres:
            xbmcgui.Dialog().notification("No Genres", "No genres found", xbmcgui.NOTIFICATION_INFO)
            xbmcplugin.endOfDirectory(handle)
            return
            
        # Sort genres by name
        genres = sorted(genres, key=lambda x: x['name'].lower())
        
        for genre in genres:
            name = genre['name']
            count = genre.get('count', 0)
            label = f"{name}"
            if count:
                label += f" ({count})"
                
            li = xbmcgui.ListItem(label)
            
            # Set art
            li.setArt({
                'icon': 'DefaultGenre.png',
                'thumb': 'DefaultGenre.png'
            })
            
            # Set info
            info = {
                'title': name,
                'count': count
            }
            li.setInfo('video', info)
            
            # Create URL
            url = f'sys.argv[0]?action=list_genre&genre={name}'
            
            # Add to directory
            xbmcplugin.addDirectoryItem(
                handle=handle,
                url=url,
                listitem=li,
                isFolder=True
            )
            
        # Add sort method and end directory
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.endOfDirectory(handle)
        
    except Exception as e:
        xbmc.log(f"Error in list_genres: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error", "Failed to load genres", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)

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
    """
    Show a weekly calendar of anime episodes
    """
    try:
        from datetime import datetime, timedelta
        
        # Get today's date
        today = datetime.now()
        
        # Create a list of the next 7 days
        dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        
        # Set plugin content and category
        xbmcplugin.setPluginCategory(handle, 'Anime Calendar')
        xbmcplugin.setContent(handle, 'tvshows')
        
        # Add directory items for each day
        for date_str in dates:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day_name = date_obj.strftime('%A')
            date_display = date_obj.strftime('%b %d, %Y')
            
            # Create a list item for the day
            li = xbmcgui.ListItem(f"{day_name}, {date_display}")
            
            # Set art and info
            li.setArt({
                'icon': 'DefaultYear.png',
                'thumb': 'DefaultYear.png'
            })
            
            # Create URL for the date
            url = f'sys.argv[0]?action=calendar_date&date={date_str}'
            
            # Add to directory
            xbmcplugin.addDirectoryItem(
                handle=handle,
                url=url,
                listitem=li,
                isFolder=True
            )
        
        # Add sort method and end directory
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.endOfDirectory(handle)
        
    except Exception as e:
        xbmc.log(f"Error in list_calendar: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error", "Failed to load calendar", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)

def list_calendar_date(handle, date):
    """
    List all episodes airing on a specific date
    """
    try:
        # Get episodes for the date
        api = AnimeDBAPI()
        episodes = api.get_episodes_by_airdate(date)
        
        if not episodes:
            xbmcgui.Dialog().notification("No Episodes", f"No episodes found for {date}", xbmcgui.NOTIFICATION_INFO)
            xbmcplugin.setPluginCategory(handle, f'Calendar - {date}')
            xbmcplugin.endOfDirectory(handle)
            return
        
        # Set plugin content and category
        xbmcplugin.setPluginCategory(handle, f'Episodes - {date}')
        xbmcplugin.setContent(handle, 'episodes')
        
        # Add each episode to the list
        for episode in episodes:
            # Create list item
            title = f"{episode.get('show_title', 'Unknown')} - Episode {episode.get('episode', '?')}"
            li = xbmcgui.ListItem(title)
            
            # Set art
            art = {
                'poster': episode.get('poster', ''),
                'banner': episode.get('banner', ''),
                'thumb': episode.get('poster', '')
            }
            li.setArt(art)
            
            # Set info
            info = {
                'title': title,
                'tvshowtitle': episode.get('show_title', ''),
                'plot': episode.get('description', ''),
                'episode': episode.get('episode', 0),
                'premiered': episode.get('air_date', '')
            }
            li.setInfo('video', info)
            
            # Create URL (this would be updated to play the actual episode)
            url = f'sys.argv[0]?action=play&anime_id={episode.get("anime_id")}&episode={episode.get("episode")}'
            
            # Add to directory
            xbmcplugin.addDirectoryItem(
                handle=handle,
                url=url,
                listitem=li,
                isFolder=False
            )
        
        # Add sort method and end directory
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.endOfDirectory(handle)
        
    except Exception as e:
        xbmc.log(f"Error in list_calendar_date: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error", "Failed to load episodes", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)

def search(handle, query=None, media_type=None, status=None, year=None, genre=None, page=1):
    """
    Show search dialog and display results with filters
    """
    try:
        # Show search dialog if no query provided
        if not query:
            query = xbmcgui.Dialog().input('Search Anime')
            if not query:
                xbmcplugin.endOfDirectory(handle)
                return
        
        # Show filter dialog if no filters provided
        if media_type is None:
            filter_dialog = xbmcgui.Dialog()
            filter_options = [
                'Search Now',
                'Change Media Type',
                'Change Status',
                'Change Year',
                'Change Genre',
                'Reset Filters'
            ]
            
            # Show current filters
            current_filters = []
            if media_type:
                current_filters.append(f"Type: {media_type}")
            if status:
                current_filters.append(f"Status: {status}")
            if year:
                current_filters.append(f"Year: {year}")
            if genre:
                current_filters.append(f"Genre: {genre}")
                
            filter_title = "Search Filters"
            if current_filters:
                filter_title += " (" + ", ".join(current_filters) + ")"
            
            selected = 0
            while True:
                choice = filter_dialog.select(filter_title, filter_options, preselect=selected)
                if choice == -1:  # User cancelled
                    xbmcplugin.endOfDirectory(handle)
                    return
                elif choice == 0:  # Search Now
                    break
                elif choice == 1:  # Media Type
                    types = ['All', 'TV', 'Movie', 'OVA', 'ONA', 'Special', 'Music']
                    idx = filter_dialog.select('Select Media Type', types)
                    if idx >= 0:
                        media_type = types[idx] if types[idx] != 'All' else None
                elif choice == 2:  # Status
                    statuses = ['Any', 'FINISHED', 'RELEASING', 'NOT_YET_RELEASED', 'CANCELLED', 'HIATUS']
                    idx = filter_dialog.select('Select Status', statuses)
                    if idx >= 0:
                        status = statuses[idx] if statuses[idx] != 'Any' else None
                elif choice == 3:  # Year
                    current_year = datetime.now().year
                    years = ['Any'] + [str(y) for y in range(current_year, 1900, -1)]
                    idx = filter_dialog.select('Select Year', years)
                    if idx > 0:
                        year = int(years[idx])
                    else:
                        year = None
                elif choice == 4:  # Genre
                    api = AnimeDBAPI()
                    genres_data = api.get_genres()
                    genres = [g['name'] for g in genres_data]
                    genres.insert(0, 'Any')
                    idx = filter_dialog.select('Select Genre', genres)
                    if idx > 0:
                        genre = genres[idx]
                    else:
                        genre = None
                elif choice == 5:  # Reset Filters
                    media_type = status = year = genre = None
                
                # Update filter title
                current_filters = []
                if media_type:
                    current_filters.append(f"Type: {media_type}")
                if status:
                    current_filters.append(f"Status: {status}")
                if year:
                    current_filters.append(f"Year: {year}")
                if genre:
                    current_filters.append(f"Genre: {genre}")
                    
                filter_title = "Search Filters"
                if current_filters:
                    filter_title += " (" + ", ".join(current_filters) + ")"
                
                selected = choice
        
        # Initialize API and perform search
        api = AnimeDBAPI()
        results = api.search(
            query=query,
            media_type=media_type,
            status=status,
            year=year,
            genre=genre,
            page=page
        )
        
        if not results:
            xbmcgui.Dialog().notification("No Results", "No anime found matching your search", xbmcgui.NOTIFICATION_INFO)
            xbmcplugin.endOfDirectory(handle)
            return
            
        # Set plugin content and category
        title_parts = [f'Search: {query}']
        if media_type:
            title_parts.append(f'Type: {media_type}')
        if status:
            title_parts.append(f'Status: {status}')
        if year:
            title_parts.append(f'Year: {year}')
        if genre:
            title_parts.append(f'Genre: {genre}')
            
        xbmcplugin.setPluginCategory(handle, ' | '.join(title_parts))
        xbmcplugin.setContent(handle, 'tvshows')
        
        # Add results to directory
        for anime in results:
            # Create list item
            title = anime.get('title', 'Unknown')
            li = xbmcgui.ListItem(title)
            
            # Set art
            art = {
                'poster': anime.get('poster', ''),
                'banner': anime.get('banner', ''),
                'thumb': anime.get('poster', '')
            }
            li.setArt(art)
            
            # Set info
            info = {
                'title': title,
                'originaltitle': anime.get('original_title', ''),
                'plot': anime.get('description', ''),
                'year': anime.get('year'),
                'episode': anime.get('episodes', 0),
                'status': anime.get('status', ''),
                'genre': ", ".join(anime.get('genres', [])),
                'rating': anime.get('score', 0) / 10.0 if anime.get('score') else 0
            }
            li.setInfo('video', info)
            
            # Set additional properties for Arctic Fuse 2
            li.setProperty('IsPlayable', 'false')
            
            # Create URL for the anime
            url = f'sys.argv[0]?action=anime_details&anime_id={anime.get("id")}&source=anilist'
            
            # Add to directory
            xbmcplugin.addDirectoryItem(
                handle=handle,
                url=url,
                listitem=li,
                isFolder=True
            )
        
        # Add pagination if needed
        if len(results) >= 20:  # Default page size
            next_page = page + 1
            li = xbmcgui.ListItem('Next Page >>')
            url = f'sys.argv[0]?action=search&query={query}'
            if media_type:
                url += f'&media_type={media_type}'
            if status:
                url += f'&status={status}'
            if year:
                url += f'&year={year}'
            if genre:
                url += f'&genre={genre}'
            url += f'&page={next_page}'
            
            xbmcplugin.addDirectoryItem(
                handle=handle,
                url=url,
                listitem=li,
                isFolder=True
            )
        
        # Add sort method and end directory
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.endOfDirectory(handle)
        
    except Exception as e:
        xbmc.log(f"Error in search: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error", f"Search failed: {str(e)}", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)

# --- END PLACEHOLDERS ---

def show_anime_details(anime_id, source='anilist', title=None):
    """
    Show detailed information about an anime and its episodes with library management options
    """
    from resources.lib.tmdb_bridge import get_tmdb_api, find_tmdb_id
    from resources.lib.library import LIBRARY
    
    # Get anime details
    details = API.anime_details(anime_id, source)
    if not details:
        xbmcgui.Dialog().notification("Error", "Could not load anime details", xbmcgui.NOTIFICATION_ERROR)
        return
    
    # Get library status
    in_library = LIBRARY.get_anime_status(anime_id, source)
    
    # Get TMDB metadata if available
    tmdb_api = get_tmdb_api()
    tmdb_meta = None
    if tmdb_api and details:
        tmdb_id = find_tmdb_id(details.get('title', ''))
        if tmdb_id:
            try:
                tmdb_meta = tmdb_api.get_tv_details(tmdb_id)
            except Exception as e:
                xbmc.log(f"Error getting TMDB details: {str(e)}", xbmc.LOGERROR)
    
    # Get show title
    show_title = title or details.get('title', 'Unknown')
    if tmdb_meta and tmdb_meta.get('name'):
        show_title = tmdb_meta['name']
    
    # Create dialog items
    dialog_items = []
    
    # Main actions
    if details.get('format') in ['TV', 'TV_SHORT', 'ONA', 'SPECIAL']:
        dialog_items.append("View Episodes")
    else:
        dialog_items.append("Play")
    
    # Library actions
    if in_library:
        dialog_items.append("Remove from Library")
        
        # Add status options
        current_status = in_library.get('status', '').upper()
        status_options = [
            ("Watching", 'CURRENT'),
            ("Completed", 'COMPLETED'),
            ("On Hold", 'PAUSED'),
            ("Dropped", 'DROPPED'),
            ("Plan to Watch", 'PLANNING')
        ]
        
        dialog_items.append(f"Status: {current_status}")
        for status_name, status_value in status_options:
            if status_value != current_status:
                dialog_items.append(f"  - {status_name}")
    else:
        dialog_items.append("Add to Library")
    
    # Add to watchlist
    if is_in_watchlist(anime_id, source):
        dialog_items.append("Remove from Watchlist")
    else:
        dialog_items.append("Add to Watchlist")
    
    # Add metadata section
    dialog_items.append("\n[COLOR=FF00FF00]Details:[/COLOR]")
    
    # Title
    if details.get('original_title') and details['original_title'] != show_title:
        dialog_items.append(f"Original Title: {details['original_title']}")
    
    # Format and status
    format_text = details.get('format', 'N/A')
    if details.get('episodes'):
        format_text += f" ({details['episodes']} episodes)"
    dialog_items.append(f"Format: {format_text}")
    
    # Status
    if details.get('status'):
        dialog_items.append(f"Status: {details['status']}")
    
    # Airing dates
    if details.get('start_date'):
        airing_text = f"Aired: {details['start_date']}"
        if details.get('end_date'):
            airing_text += f" to {details['end_date']}"
        dialog_items.append(airing_text)
    
    # Score
    if details.get('score'):
        dialog_items.append(f"Score: {details['score']}/100")
    
    # Genres
    if details.get('genres'):
        dialog_items.append(f"Genres: {', '.join(details['genres'])}")
    
    # Studios
    if details.get('studios'):
        dialog_items.append(f"Studios: {', '.join(details['studios'])}")
    
    # Description
    if details.get('description'):
        dialog_items.append("\n[COLOR=FF00FF00]Description:[/COLOR]")
        # Split long description into multiple lines
        import textwrap
        desc_lines = textwrap.wrap(details['description'], width=80)
        dialog_items.extend(desc_lines)
    
    # Show dialog
    dialog = xbmcgui.Dialog()
    selection = dialog.select(show_title, dialog_items)
    
    if selection == -1:  # User cancelled
        return
    
    selected_item = dialog_items[selection]
    
    # Handle actions
    if selected_item == "View Episodes":
        xbmc.executebuiltin(f"Container.Update(plugin://{ADDON_ID}/?action=list_episodes&id={anime_id}&source={source}&title={show_title})")
    
    elif selected_item == "Play":
        xbmc.executebuiltin(f"RunPlugin(plugin://{ADDON_ID}/?action=play_item_route&id={anime_id}&source={source}&episode=1")
    
    elif selected_item == "Add to Library":
        LIBRARY.add_to_library(anime_id, source, status="PLANNING")
        xbmcgui.Dialog().notification("Added to Library", f"{show_title} has been added to your library", xbmcgui.NOTIFICATION_INFO)
        xbmc.executebuiltin('Container.Refresh')
    
    elif selected_item == "Remove from Library":
        if xbmcgui.Dialog().yesno("Confirm Removal", f"Remove {show_title} from your library?"):
            LIBRARY.remove_from_library(anime_id, source)
            xbmcgui.Dialog().notification("Removed from Library", f"{show_title} has been removed from your library", xbmcgui.NOTIFICATION_INFO)
            xbmc.executebuiltin('Container.Refresh')
    
    elif selected_item.startswith("  - ") and in_library:
        # Status change
        new_status = None
        for status_name, status_value in status_options:
            if selected_item.strip().endswith(status_name):
                new_status = status_value
                break
        
        if new_status:
            LIBRARY.add_to_library(anime_id, source, status=new_status)
            xbmcgui.Dialog().notification("Status Updated", f"Status changed to {new_status.replace('_', ' ').title()}", xbmcgui.NOTIFICATION_INFO)
            xbmc.executebuiltin('Container.Refresh')
    
    elif selected_item in ["Add to Watchlist", "Remove from Watchlist"]:
        toggle_watchlist(anime_id, source, show_title)
        xbmc.executebuiltin('Container.Refresh')

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
