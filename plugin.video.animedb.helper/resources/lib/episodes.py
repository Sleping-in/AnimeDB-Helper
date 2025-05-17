import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import json
from urllib.parse import urlencode, parse_qsl
from typing import Dict, List, Optional, Any, Union, Tuple

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Import after ADDON is defined to avoid circular imports
from resources.lib.library import LIBRARY
from resources.lib.ui_utils import create_episode_list_item

def get_watched_episodes(anime_id: str, source: str) -> List[int]:
    """Get list of watched episode numbers for an anime."""
    try:
        anime = LIBRARY.get_anime_status(anime_id, source)
        if anime and 'watched_episodes' in anime:
            return anime['watched_episodes']
    except Exception as e:
        xbmc.log(f"Error getting watched episodes: {str(e)}", xbmc.LOGERROR)
    return []

def get_episode_progress(anime_id: str, source: str, episode_number: int) -> float:
    """Get progress for a specific episode."""
    try:
        return LIBRARY.get_episode_progress(anime_id, source, episode_number)
    except Exception as e:
        xbmc.log(f"Error getting episode progress: {str(e)}", xbmc.LOGERROR)
        return 0.0

def create_play_url(anime_id: str, source: str, episode: int, total_episodes: Optional[int] = None) -> str:
    """Create a play URL for an episode."""
    params = {
        'action': 'play',
        'anime_id': str(anime_id),
        'source': source,
        'episode': str(episode)
    }
    if total_episodes:
        params['total_episodes'] = str(total_episodes)
    return f'plugin://{ADDON_ID}/?{urlencode(params)}'

def list_episodes(handle: int, anime_id: str, source: str = 'anilist', title: Optional[str] = None) -> None:
    """
    List all episodes for an anime with progress tracking and improved display.
    
    Args:
        handle: Kodi window handle
        anime_id: ID of the anime
        source: Source service (anilist, mal, etc.)
        title: Optional title for the listing
    """
    xbmc.log(f"list_episodes called with anime_id={anime_id}, source={source}, title={title}", xbmc.LOGINFO)
    
    # Validate anime_id
    if not anime_id or not str(anime_id).isdigit():
        xbmcgui.Dialog().notification(
            "Error",
            "Invalid or missing anime ID",
            xbmcgui.NOTIFICATION_ERROR
        )
        if isinstance(handle, int) and handle >= 0:
            xbmcplugin.endOfDirectory(handle)
        return
    
    # Get watched episodes and progress
    watched_episodes = get_watched_episodes(anime_id, source)
    
    # Try TMDB integration first
    from resources.lib.tmdb_bridge import get_tmdb_episodes

    # Set content type and properties
    xbmcplugin.setContent(handle, 'episodes')
    
    # Set category
    display_title = title or f"Anime ID: {anime_id}"
    xbmcplugin.setPluginCategory(handle, f"Episodes: {display_title}")
    
    # Get anime details
    api = AnimeDBAPI()
    details = api.anime_details(anime_id, source)
    xbmc.log(f"Anime details fetched: {details}", xbmc.LOGINFO)
    
    if not details:
        xbmcgui.Dialog().notification(
            "Error",
            "Failed to get anime details",
            xbmcgui.NOTIFICATION_ERROR
        )
        if isinstance(handle, int) and handle >= 0:
            xbmcplugin.endOfDirectory(handle)
        return
    
    # Get total episodes from details if available
    total_episodes = details.get('episodes') or 0
    
    # Get total episodes
    total_episodes = details.get('episodes', 0)
    
    if total_episodes is None:
        total_episodes = 0
    if total_episodes <= 0:
        xbmcgui.Dialog().notification(
            "No Episodes",
            "This anime has no episodes available",
            xbmcgui.NOTIFICATION_WARNING
        )
        if isinstance(handle, int) and handle >= 0:
            xbmcplugin.endOfDirectory(handle)
        return
    
    # Get the base URL for episode thumbnails if available
    base_thumb_url = details.get('thumbnail_url', '')
    if base_thumb_url and '{episode}' in base_thumb_url:
        has_episode_thumbs = True
    else:
        has_episode_thumbs = False
    
    # Try to get TMDB episodes if enabled
    tmdb_episodes = get_tmdb_episodes(details.get('title', ''), season=1)
    tmdb_episode_map = {ep['episode_number']: ep for ep in tmdb_episodes if ep.get('episode_number')}
    from resources.lib.tmdb_bridge import get_tmdb_api, find_tmdb_id
    tmdb_api = get_tmdb_api()
    tmdb_meta = None
    if tmdb_api:
        tmdb_id = find_tmdb_id(details.get('title', ''))
        if tmdb_id:
            try:
                tmdb_meta = tmdb_api.get_tv_details(tmdb_id)
            except Exception:
                tmdb_meta = None
    # Fetch episode details from AniList (thumbnails, titles, summaries)
    episode_details = []
    if source == 'anilist':
        episode_details = api.anilist_episodes(anime_id)
    episode_map = {ep['number']: ep for ep in episode_details if ep.get('number')}
    # Create a list item for each episode
    for episode_num in range(1, total_episodes + 1):
        # Prefer TMDB episode data if available
        tmdb_ep = tmdb_episode_map.get(episode_num)
        if tmdb_ep:
            episode_title = tmdb_ep.get('name') or f"Episode {episode_num}"
            episode_plot = tmdb_ep.get('overview') or (tmdb_meta and tmdb_meta.get('overview')) or details.get('description', '')
            episode_thumb = ''
            if tmdb_ep.get('still_path'):
                from resources.lib.tmdb import TMDBAPI
                episode_thumb = TMDBAPI.IMAGE_BASE + tmdb_ep['still_path']
            elif tmdb_meta and tmdb_meta.get('poster_path'):
                episode_thumb = tmdb_api.IMAGE_BASE + tmdb_meta['poster_path']
            else:
                episode_thumb = details.get('poster', '') or details.get('banner', '')
            air_date = tmdb_ep.get('air_date')
            duration = tmdb_ep.get('runtime')
        else:
            ep = episode_map.get(episode_num, {})
            episode_title = ep.get('title') or f"Episode {episode_num}"
            episode_plot = ep.get('description') or (tmdb_meta and tmdb_meta.get('overview')) or details.get('description', '')
            episode_thumb = ep.get('thumbnail') or (tmdb_meta and tmdb_meta.get('poster_path') and tmdb_api.IMAGE_BASE + tmdb_meta['poster_path']) or details.get('poster', '') or details.get('banner', '')
            air_date = None
            if ep.get('air_date'):
                try:
                    from datetime import datetime
                    air_date = datetime.utcfromtimestamp(ep['air_date']).strftime('%Y-%m-%d')
                except Exception:
                    air_date = None
            duration = ep.get('duration')
        li = xbmcgui.ListItem(episode_title)
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(episode_title)
        info_tag.setTvShowTitle(tmdb_meta['name'] if tmdb_meta and tmdb_meta.get('name') else details.get('title', ''))
        info_tag.setEpisode(episode_num)
        info_tag.setSeason(1)
        info_tag.setPlot(episode_plot)
        if air_date:
            info_tag.setPremiered(air_date)
        if duration:
            info_tag.setDuration(duration)
        if tmdb_meta and tmdb_meta.get('genres'):
            info_tag.setGenres([g['name'] for g in tmdb_meta['genres']])
        else:
            info_tag.setGenres(details.get('genres', []))
            
        # Set additional properties for better Kodi integration
        li.setProperty('IsPlayable', 'true')
        li.setProperty('TotalEpisodes', str(total_episodes))
        
        # Create URL for playback with all necessary parameters
        url = create_play_url(
            anime_id=anime_id,
            source=source,
            episode=ep_num,
            total_episodes=total_episodes
        )
        
        # Create context menu items
        context_items = [
            (ADDON.getLocalizedString(30010),  # Mark as Watched
             f'RunPlugin(plugin://{ADDON_ID}/?action=mark_watched&anime_id={anime_id}&source={source}&episode={ep_num}'),
            (ADDON.getLocalizedString(30011),  # Mark as Unwatched
             f'RunPlugin(plugin://{ADDON_ID}/?action=mark_unwatched&anime_id={anime_id}&source={source}&episode={ep_num}'),
            (ADDON.getLocalizedString(30012),  # Refresh Episodes
             f'RunPlugin(plugin://{ADDON_ID}/?action=refresh_episodes&anime_id={anime_id}&source={source}'),
            (ADDON.getLocalizedString(30013),  # Add/Remove from Watchlist
             f'RunPlugin(plugin://{ADDON_ID}/?action=toggle_watchlist&id={anime_id}&source={source}')
        ]
        
        li.addContextMenuItems(context_items)
        
        # Add to directory with progress tracking
        xbmcplugin.addDirectoryItem(
            handle=handle,
            url=url,
            listitem=li,
            isFolder=False,
            totalItems=len(episodes)
        )
        
        # Set the resume point if partially watched
        if 0 < progress < 1:
            li.setProperty('ResumeTime', str(int(progress * 100)))
            li.setProperty('TotalTime', '100')  # 100% as base
    
    # Add sort methods
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_TITLE)
    
    # Set view mode for episodes
    xbmcplugin.setContent(handle, 'episodes')
    xbmc.executebuiltin('Container.SetViewMode(504)')
    
    # End of directory
    xbmcplugin.endOfDirectory(handle, cacheToDisc=True)
