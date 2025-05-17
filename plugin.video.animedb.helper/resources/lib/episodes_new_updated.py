try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
except ImportError:
    from resources.lib import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs

from urllib.parse import urlencode, parse_qs
import sys
import traceback
import json
import requests

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

def get_localized_string(string_id):
    return ADDON.getLocalizedString(string_id)

def log(message, level=xbmc.LOGINFO):
    if isinstance(message, list):
        message = " ".join(map(str, message))
    xbmc.log(f"{ADDON_ID} (episodes_new.py): {message}", level=level)

# --- API Imports ---
from resources.lib.api import AnimeDBAPI
from resources.lib.tmdb_bridge import get_tmdb_api, find_tmdb_id

def show_entrypoint(handle, anime_id, source, title=None):
    log(f"show_entrypoint: anime_id={anime_id}, source={source}, title={title}")
    # Get API instances
    api = AnimeDBAPI() 
    tmdb_api = get_tmdb_api()

    try:
        show_details_anilist = api.anime_details(anime_id, source)
        if not show_details_anilist:
            xbmcgui.Dialog().notification(get_localized_string(30001), get_localized_string(30002), xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(handle)
            return

        show_title_for_tmdb = show_details_anilist.get("title", title)
        show_year = show_details_anilist.get("season_year")
        tmdb_id = find_tmdb_id(show_title_for_tmdb)
        tmdb_show_details = None
        if (tmdb_id and tmdb_api):
            try:
                tmdb_show_details = tmdb_api.get_tv_details(tmdb_id)
            except Exception as e:
                log(f"Error fetching TMDB show details for tmdb_id {tmdb_id}: {e}", xbmc.LOGERROR)
                log(traceback.format_exc(), xbmc.LOGERROR)
                tmdb_show_details = {}

        # Proceed with available details
        if not tmdb_show_details:
            log("Proceeding with AniList details only.", xbmc.LOGWARNING)

        # Decide whether to show seasons list or direct episode list
        if tmdb_show_details and tmdb_show_details.get("seasons"):
            # Filter out seasons with episode_count 0 unless they are specials with a name
            valid_tmdb_seasons = [s for s in tmdb_show_details.get("seasons", []) if s.get("episode_count", 0) > 0 or (s.get("season_number") == 0 and s.get("name"))]
            if len(valid_tmdb_seasons) > 1 or (len(valid_tmdb_seasons) == 1 and valid_tmdb_seasons[0].get("season_number") != 1):
                log(f"Multiple or non-standard single season found for {show_title_for_tmdb}. Listing seasons.")
                list_show_seasons(handle, anime_id, source, show_details_anilist, tmdb_show_details)
                return # Important: list_show_seasons calls endOfDirectory

        # If not listing seasons, list episodes for the (assumed single or default) season.
        log(f"Single season or no TMDB multi-season info for {show_title_for_tmdb}. Listing episodes.")
        default_season_number = 1 # Default to season 1
        if tmdb_show_details and tmdb_show_details.get("seasons") and len(valid_tmdb_seasons) == 1:
            default_season_number = valid_tmdb_seasons[0].get("season_number", 1)
        
        list_episodes_for_season(handle, anime_id, source, default_season_number, show_details_anilist, tmdb_id, tmdb_show_details)

    except Exception as e:
        log(f"Unhandled error in show_entrypoint: {e}", xbmc.LOGERROR)
        log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(get_localized_string(30001), str(e), xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle)

def list_show_seasons(handle, anime_id, source, show_details_anilist, tmdb_show_details):
    log(f"list_show_seasons for: {show_details_anilist.get('title')}")
    xbmcplugin.setContent(handle, "seasons")
    plugin_category_title = show_details_anilist.get("title", get_localized_string(30007))
    xbmcplugin.setPluginCategory(handle, plugin_category_title)

    tmdb_seasons = tmdb_show_details.get("seasons", [])
    if not tmdb_seasons:
        xbmcgui.Dialog().notification(
            get_localized_string(30003), 
            get_localized_string(30004), 
            xbmcgui.NOTIFICATION_INFO
        )
        xbmcplugin.endOfDirectory(handle)
        return

    # Sort seasons by season number
    tmdb_seasons.sort(key=lambda x: x.get("season_number", 0))

    for season in tmdb_seasons:
        season_number = season.get("season_number", 0)
        episode_count = season.get("episode_count", 0)
        
        # Skip season if it has no episodes and it's not a special
        if episode_count == 0 and season_number != 0:
            continue

        # Skip specials (season 0) if they have no name
        if season_number == 0 and not season.get("name"):
            continue

        # Set season title
        if season_number == 0:
            season_name = season.get("name", get_localized_string(30013))  # Specials
        else:
            season_name = get_localized_string(30008).format(number=season_number)  # Season X
        
        # Set art
        poster_path = season.get("poster_path")
        fanart_path = tmdb_show_details.get("backdrop_path")
        
        # Create list item
        li = xbmcgui.ListItem(season_name)
        
        # Set art
        art = {}
        if poster_path:
            art["thumb"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
            art["poster"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
        if fanart_path:
            art["fanart"] = f"https://image.tmdb.org/t/p/original{fanart_path}"
        
        li.setArt(art)
        
        # Set info
        info = {
            "title": season_name,
            "tvshowtitle": show_details_anilist.get("title", ""),
            "plot": season.get("overview", ""),
            "season": season_number,
            "episode": episode_count,
            "mediatype": "season"
        }
        
        if season.get("air_date"):
            info["premiered"] = season.get("air_date")
        
        li.setInfo("video", info)
        
        # Create URL
        url_params = {
            "action": "list_episodes_for_season",
            "anime_id": anime_id,
            "source": source,
            "season_number": str(season_number),
            "tmdb_id": str(tmdb_show_details.get("id", "")),
            "title": show_details_anilist.get("title", "")
        }
        
        url = f"{sys.argv[0]}?{urlencode(url_params)}"
        
        # Add directory item
        xbmcplugin.addDirectoryItem(
            handle=handle,
            url=url,
            listitem=li,
            isFolder=True
        )
    
    xbmcplugin.endOfDirectory(handle)

def list_episodes_for_season(handle, anime_id, source, season_number, show_details_anilist=None, tmdb_id=None, tmdb_show_details_parent=None):
    log(f"list_episodes_for_season: anime_id={anime_id}, S{season_number}, tmdb_id={tmdb_id}")
    
    # Ensure season_number is int
    try:
        season_number = int(season_number)
    except ValueError:
        log(f"Invalid season_number format: {season_number}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(get_localized_string(30001), f"Invalid season number: {season_number}", xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle)
        return

    api = AnimeDBAPI()
    tmdb_api = get_tmdb_api()

    try:
        if not show_details_anilist:
            show_details_anilist = api.anime_details(anime_id, source)
            if not show_details_anilist:
                xbmcgui.Dialog().notification(get_localized_string(30001), get_localized_string(30005), xbmcgui.NOTIFICATION_ERROR)
                xbmcplugin.endOfDirectory(handle)
                return

        show_title_for_display = show_details_anilist.get("title", get_localized_string(30012))
        xbmcplugin.setContent(handle, "episodes")
        season_display_name_for_category = get_localized_string(30008).format(number=season_number)
        if season_number == 0: 
            season_display_name_for_category = get_localized_string(30013)  # Specials
        xbmcplugin.setPluginCategory(handle, f"{show_title_for_display} - {season_display_name_for_category}")

        tmdb_season_episodes = []
        tmdb_season_meta = None
        
        if tmdb_id and tmdb_api:
            try:
                # Get season details from TMDB
                url = f'{tmdb_api.BASE_URL}/tv/{tmdb_id}/season/{season_number}'
                params = {'api_key': tmdb_api.api_key}
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                tmdb_season_meta = resp.json()
                
                if tmdb_season_meta and tmdb_season_meta.get("episodes"):
                    tmdb_season_episodes = tmdb_season_meta.get("episodes")
            except Exception as e:
                log(f"Error fetching TMDB season details for {tmdb_id}, S{season_number}: {e}", xbmc.LOGERROR)
                log(traceback.format_exc(), xbmc.LOGERROR)
                # Continue with AniList fallback
        
        # Determine fanart: use parent show fanart if available
        show_fanart = ""
        if tmdb_show_details_parent and tmdb_show_details_parent.get("backdrop_path") and tmdb_api:
            show_fanart = f"https://image.tmdb.org/t/p/original{tmdb_show_details_parent.get('backdrop_path')}"
        elif show_details_anilist.get("banner"):
            show_fanart = show_details_anilist.get("banner")

        if not tmdb_season_episodes:
            log(f"No TMDB episode data for {show_title_for_display} S{season_number}. Falling back to AniList.")
            # AniList fallback - get episodes from AniList
            anilist_episodes = api.anilist_episodes(anime_id)
            
            if not anilist_episodes:
                xbmcgui.Dialog().notification(
                    get_localized_string(30003), 
                    get_localized_string(30006).format(season_number=season_number), 
                    xbmcgui.NOTIFICATION_INFO
                )
                xbmcplugin.endOfDirectory(handle)
                return
            
            # For AniList, we'll use a simple approach to map episodes to seasons
            episodes_per_season = 12  # Typical anime season length
            
            # Filter episodes for the requested season
            if season_number == 0:
                # For specials (season 0), we'll include any episode marked as a special
                filtered_episodes = [ep for ep in anilist_episodes if "special" in ep.get("title", "").lower()]
            else:
                # For regular seasons, we'll use a simple calculation based on episode numbers
                start_ep = (season_number - 1) * episodes_per_season + 1
                end_ep = season_number * episodes_per_season
                filtered_episodes = [ep for ep in anilist_episodes if start_ep <= ep.get("number", 0) <= end_ep]
            
            # Add episodes to the list
            for episode in filtered_episodes:
                episode_number = episode.get("number", 0)
                episode_title = episode.get("title", f"Episode {episode_number}")
                
                li = xbmcgui.ListItem(f"{episode_number}. {episode_title}")
                
                # Set art
                thumb = episode.get("thumbnail", "")
                art_data = {"thumb": thumb, "fanart": show_fanart}
                li.setArt(art_data)
                
                # Set info
                info_tag = li.getVideoInfoTag()
                info_tag.setTitle(episode_title)
                info_tag.setTvShowTitle(show_title_for_display)
                info_tag.setSeason(season_number)
                info_tag.setEpisode(episode_number)
                info_tag.setPlot(episode.get("description", ""))
                info_tag.setMediaType("episode")
                
                if episode.get("air_date"):
                    # Convert timestamp to date string
                    from datetime import datetime
                    air_date = datetime.fromtimestamp(episode.get("air_date")).strftime("%Y-%m-%d")
                    info_tag.setPremiered(air_date)
                
                if episode.get("duration"):
                    info_tag.setDuration(episode.get("duration") * 60)  # Convert minutes to seconds
                
                # Create URL for playback using the new player
                url_params = {
                    "action": "play_item_route",
                    "anime_id": str(anime_id),
                    "source": source,
                    "episode": str(episode_number),
                    "total_episodes": str(show_details_anilist.get("episodes", 0)),
                    "title": show_title_for_display,
                    "episode_title": episode_title,
                    # Use a placeholder URL - in a real implementation, this would be the actual video URL
                    "url": f"plugin://{ADDON_ID}/play/anime/{anime_id}/{episode_number}"
                }
                
                url = f"{sys.argv[0]}?{urlencode(url_params)}"
                xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=False)
        else:
            # Use TMDB episode data
            for episode in tmdb_season_episodes:
                episode_number = episode.get("episode_number", 0)
                episode_title = episode.get("name", f"Episode {episode_number}")
                
                li = xbmcgui.ListItem(f"{episode_number}. {episode_title}")
                
                # Set art
                still_path = episode.get("still_path")
                thumb = f"https://image.tmdb.org/t/p/w500{still_path}" if still_path else ""
                art_data = {"thumb": thumb, "fanart": show_fanart}
                li.setArt(art_data)
                
                # Set info
                info_tag = li.getVideoInfoTag()
                info_tag.setTitle(episode_title)
                info_tag.setTvShowTitle(show_title_for_display)
                info_tag.setSeason(season_number)
                info_tag.setEpisode(episode_number)
                info_tag.setPlot(episode.get("overview", ""))
                info_tag.setMediaType("episode")
                
                if episode.get("air_date"):
                    info_tag.setPremiered(episode.get("air_date"))
                
                if episode.get("runtime"):
                    info_tag.setDuration(episode.get("runtime") * 60)  # Convert minutes to seconds
                
                # Create URL for playback using the new player
                url_params = {
                    "action": "play_item_route",
                    "anime_id": str(anime_id),
                    "source": source,
                    "episode": str(episode_number),
                    "total_episodes": str(tmdb_show_details_parent.get("number_of_episodes", 0) if tmdb_show_details_parent else 0),
                    "title": show_title_for_display,
                    "episode_title": episode_title,
                    # Use a placeholder URL - in a real implementation, this would be the actual video URL
                    "url": f"plugin://{ADDON_ID}/play/anime/{anime_id}/{episode_number}"
                }
                
                url = f"{sys.argv[0]}?{urlencode(url_params)}"
                xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=False)
        
        # Add sort methods
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_DATEADDED)
        
        xbmcplugin.endOfDirectory(handle)
    
    except Exception as e:
        log(f"Unhandled error in list_episodes_for_season: {e}", xbmc.LOGERROR)
        log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(get_localized_string(30001), str(e), xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle)
