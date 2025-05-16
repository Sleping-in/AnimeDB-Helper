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
import json # For item_meta_json in play route
import requests

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

# --- Localization --- 
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
        # Consider a show to be multi-season if TMDB provides more than one season entry (excluding specials or based on config)
        # For simplicity, if tmdb_show_details and its seasons list exists and has more than one item, show seasons.
        # Or, if only one season exists but it is not season 1 (e.g. only season 2 listed), still go to season view.
        # A common case is shows with only "Season 1". These could arguably go direct to episodes.
        # Let's refine: go to seasons view if tmdb_show_details.seasons has more than 1 entry OR the single entry is not S1.
        # However, an anime might just be one season (e.g. 12 eps). AniList `episodes` might be total.
        # If TMDB has season info, use it. If not, fallback to flat list from AniList details.

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
        # This case should ideally be handled by show_entrypoint logic before calling this function
        xbmcgui.Dialog().notification(get_localized_string(30003), get_localized_string(30004), xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.endOfDirectory(handle)
        return

    # Filter and sort seasons (e.g., specials first, then by season number)
    # TMDB often includes season 0 for specials.
    sorted_seasons = sorted([s for s in tmdb_seasons if s.get("episode_count",0) > 0 or (s.get("season_number") == 0 and s.get("name"))],
                            key=lambda s: (s.get("season_number", 9999)))

    for season_data in sorted_seasons:
        season_number = season_data.get("season_number")
        season_name_from_tmdb = season_data.get("name")
        # Use TMDB name if available and not generic, otherwise format like "Season X"
        season_display_name = season_name_from_tmdb if season_name_from_tmdb and not season_name_from_tmdb.lower().startswith("season ") else get_localized_string(30008).format(number=season_number)
        if season_number == 0 and season_name_from_tmdb: # For specials, prefer TMDB name if specific
            season_display_name = season_name_from_tmdb
        elif season_number == 0: # Generic specials name
            season_display_name = get_localized_string(30013)

        if season_number is None: continue # Should not happen with filtered seasons

        li = xbmcgui.ListItem(season_display_name)
        
        poster_path = season_data.get("poster_path")
        tmdb_api = get_tmdb_api()
        season_poster = tmdb_api.IMAGE_BASE + poster_path if tmdb_api and poster_path else show_details_anilist.get("poster", "")
        show_fanart = tmdb_api.IMAGE_BASE + tmdb_show_details.get("backdrop_path") if tmdb_api and tmdb_show_details.get("backdrop_path") else show_details_anilist.get("banner", "")
        
        art_data = {"poster": season_poster, "fanart": show_fanart, "banner": show_fanart, "thumb": season_poster}
        li.setArt(art_data)

        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(season_display_name)
        info_tag.setTvShowTitle(show_details_anilist.get("title", ""))
        info_tag.setSeason(season_number)
        info_tag.setPlot(season_data.get("overview", show_details_anilist.get("description", "")))
        info_tag.setMediaType("season")
        if season_data.get("air_date"):
            info_tag.setPremiered(season_data.get("air_date"))
        if show_details_anilist.get("season_year"):
             info_tag.setYear(int(show_details_anilist.get("season_year")))
        if season_data.get("episode_count") is not None:
            li.setProperty("TotalEpisodes", str(season_data.get("episode_count")))

        url_params = {
            "action": "list_episodes_for_season",
            "anime_id": anime_id,
            "source": source,
            "season_number": str(season_number),
            "show_title": show_details_anilist.get("title", ""), # Pass for category context
            "tmdb_id": tmdb_show_details.get("id", "")
        }
        url = f"{sys.argv[0]}?{urlencode(url_params)}"
        xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=True)
    
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_SEASON)
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
        if season_number == 0: season_display_name_for_category = get_localized_string(30013) # Specials
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
                # Do not fail here, might fallback to anilist if logic allows
        
        # Determine fanart: use parent show fanart if available
        show_fanart = ""
        if tmdb_show_details_parent and tmdb_show_details_parent.get("backdrop_path") and tmdb_api:
            show_fanart = tmdb_api.IMAGE_BASE + tmdb_show_details_parent.get("backdrop_path")
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
            
            # For AniList, we need to map episodes to seasons if we're showing a specific season
            # This is a simplistic approach - in a real implementation, you might need more sophisticated mapping
            # For now, let's assume:
            # - Season 1: Episodes 1-12/13
            # - Season 2: Episodes 13/14-24/26
            # - Season 3: Episodes 25/27-36/39
            # - And so on...
            # - Season 0 (specials): Any episodes marked as specials or OVAs
            
            episodes_per_season = 12  # Typical anime season length
            
            # Filter episodes for the requested season
            if season_number == 0:
                # For specials (season 0), we might need special logic
                # This is just a placeholder - in reality, you'd need to identify specials
                filtered_episodes = [ep for ep in anilist_episodes if "special" in ep.get("title", "").lower()]
            else:
                # Regular seasons
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
                
                # Create URL for playback
                item_meta = {
                    "tmdb_id": tmdb_id,
                    "tmdb_type": "tv",
                    "anilist_id": anime_id,
                    "source": source,
                    "season": season_number,
                    "episode": episode_number,
                    "title": show_title_for_display,
                    "ep_title": episode_title
                }
                
                url_params = {
                    "action": "play_item_route",
                    "item_meta_json": json.dumps(item_meta)
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
                thumb = tmdb_api.IMAGE_BASE + still_path if tmdb_api and still_path else ""
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
                
                # Create URL for playback
                item_meta = {
                    "tmdb_id": tmdb_id,
                    "tmdb_type": "tv",
                    "anilist_id": anime_id,
                    "source": source,
                    "season": season_number,
                    "episode": episode_number,
                    "title": show_title_for_display,
                    "ep_title": episode_title
                }
                
                url_params = {
                    "action": "play_item_route",
                    "item_meta_json": json.dumps(item_meta)
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
