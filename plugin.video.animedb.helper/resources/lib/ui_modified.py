import sys
import xbmcplugin
import xbmcgui
import xbmc
import xbmcaddon
from urllib.parse import urlencode, parse_qs

from resources.lib.api import AnimeDBAPI
from resources.lib.fanart import fetch_art

from resources.lib.history import get_watch_history, get_continue_watching
from resources.lib.recommendations import get_recommendations, get_similar_anime
from resources.lib.upcoming import get_upcoming, get_calendar
from resources.lib.watchlist import get_local_watchlist, is_in_watchlist, toggle_watchlist

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Create API instance
API = AnimeDBAPI()

try:
    from .ui import set_view_mode
except ImportError:
    def set_view_mode(content_type):
        pass

def list_anime(handle, anime_list, title=None):
    """
    Show a list of anime with Arctic Fuse 2 optimizations
    """
    # Set content type
    xbmcplugin.setContent(handle, 'tvshows')
    
    # Set category
    if title:
        xbmcplugin.setPluginCategory(handle, title)
    
    for anime in anime_list:
        title = anime.get('title', '')
        anime_id = anime.get('id', '')
        source = anime.get('source', 'anilist')
        
        # Get artwork with higher resolution
        art = fetch_art(anime_id, source)  # Always fetch art to get highest quality
        
        # Override with any specific artwork from the anime data
        if 'poster' in anime and anime['poster']:
            art['poster'] = anime['poster']
            
        if 'banner' in anime and anime['banner']:
            art['fanart'] = anime['banner']
            art['banner'] = anime['banner']
            art['landscape'] = anime['banner']
        
        # Create list item
        li = xbmcgui.ListItem(title)
        
        # Set info
        info = {
            'title': title,
            'mediatype': 'tvshow',
        }
        
        # Add plot if available and enabled
        if ADDON.getSettingBool('show_plot') and 'description' in anime:
            info['plot'] = anime.get('description', '')
        
        # Add score if available and enabled
        if ADDON.getSettingBool('show_score') and 'score' in anime:
            info['rating'] = anime.get('score', 0) / 10.0  # Convert to 0-10 scale
        
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
        
        # Set artwork
        li.setArt({
            'poster': art.get('poster', ''),
            'fanart': art.get('fanart', ''),
            'banner': art.get('banner', ''),
            'clearlogo': art.get('clearlogo', ''),
            'landscape': art.get('landscape', ''),
            'thumb': art.get('poster', '')
        })
        
        # Set URL for details view (default action)
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
            f"RunPlugin(plugin://{ADDON_ID}/?action=play&id={anime_id}&source={source}&episode=1)"
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

# [Rest of the file remains the same...]
