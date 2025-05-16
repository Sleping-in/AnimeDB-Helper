import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
from urllib.parse import urlencode

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

def list_episodes(handle, anime_id, source='anilist', title=None):
    import xbmc
    xbmc.log(f"list_episodes called with anime_id={anime_id}, source={source}, title={title}", xbmc.LOGWARNING)
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
    # Try TMDB integration first
    from resources.lib.tmdb_bridge import get_tmdb_episodes

    """
    List all episodes for an anime with improved display and direct playback
    """
    from resources.lib.api import AnimeDBAPI
    
    # Set content type
    xbmcplugin.setContent(handle, 'episodes')
    
    # Set category
    if title:
        xbmcplugin.setPluginCategory(handle, f"Episodes: {title}")
    
    # Get anime details
    api = AnimeDBAPI()
    details = api.anime_details(anime_id, source)
    xbmc.log(f"Anime details fetched: {details}", xbmc.LOGWARNING)
    
    if not details:
        xbmcgui.Dialog().notification(
            "Error",
            "Failed to get anime details",
            xbmcgui.NOTIFICATION_ERROR
        )
        if isinstance(handle, int) and handle >= 0:
            xbmcplugin.endOfDirectory(handle)
        return
    
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
        if tmdb_meta and tmdb_meta.get('vote_average'):
            info_tag.setRating(tmdb_meta['vote_average'])
        else:
            info_tag.setRating(details.get('score', 0) / 10.0)
        info_tag.setYear(details.get('season_year'))
        info_tag.setMediaType('episode')
        # Set artwork - prefer episode thumbnail if available, fallback to poster/banner
        art = {
            'poster': (tmdb_meta and tmdb_meta.get('poster_path') and tmdb_api.IMAGE_BASE + tmdb_meta['poster_path']) or details.get('poster', ''),
            'fanart': (tmdb_meta and tmdb_meta.get('backdrop_path') and tmdb_api.IMAGE_BASE + tmdb_meta['backdrop_path']) or details.get('banner', details.get('poster', '')),
            'banner': (tmdb_meta and tmdb_meta.get('backdrop_path') and tmdb_api.IMAGE_BASE + tmdb_meta['backdrop_path']) or details.get('banner', ''),
            'thumb': episode_thumb
        }
        li.setArt(art)

        
        # Set additional properties for better Kodi integration
        li.setProperty('IsPlayable', 'true')
        li.setProperty('TotalEpisodes', str(total_episodes))
        
        # Create context menu items
        context_menu = []
        
        # Add to watchlist option
        context_menu.append((
            "Add/Remove to Watchlist",
            f"RunPlugin(plugin://{ADDON_ID}/?action=toggle_watchlist&id={anime_id}&source={source})"
        ))
        
        # Mark as watched/unwatched
        context_menu.append((
            "Mark as Watched",
            f"RunPlugin(plugin://{ADDON_ID}/?action=mark_watched&id={anime_id}&episode={episode_num}&source={source})"
        ))
        
        li.addContextMenuItems(context_menu)
        
        # Set URL for direct playback
        url = f"plugin://{ADDON_ID}/?action=play&id={anime_id}&source={source}&episode={episode_num}"
        
        # Add to directory as a playable item
        xbmcplugin.addDirectoryItem(
            handle=handle,
            url=url,
            listitem=li,
            isFolder=False,
            totalItems=total_episodes
        )
    
    # Add sort methods
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_TITLE)
    
    # Set view mode for episodes
    xbmcplugin.setContent(handle, 'episodes')
    xbmc.executebuiltin('Container.SetViewMode(504)')
    
    # End of directory
    xbmcplugin.endOfDirectory(handle, cacheToDisc=True)
