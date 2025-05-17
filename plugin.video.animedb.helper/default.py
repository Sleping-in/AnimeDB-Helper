import sys
try:
    import xbmcaddon
    import xbmcgui
    import xbmc
    import xbmcplugin
    import xbmcvfs
except ImportError:
    from resources.lib import xbmcaddon, xbmcgui, xbmc, xbmcplugin, xbmcvfs
from urllib.parse import parse_qs, urlencode
import json # Added for item_meta parsing

# Logging function
def log(message, level=xbmc.LOGINFO):
    if isinstance(message, list):
        message = " ".join(map(str,message))
    xbmc.log(f"{ADDON_ID} (default.py): {message}", level=level)

# UI Components
from resources.lib.ui import (
    home, list_anime, list_watchlist, list_genres, list_history, 
    list_continue_watching, list_upcoming, list_calendar, list_calendar_date,
    show_anime_details, set_skin_properties, list_genre,
    list_trending, list_seasonal, add_directory_item
)

# Search functionality
from resources.lib.search import (
    show_search_menu, show_search_input, show_search_history,
    show_advanced_search, perform_search, delete_search_history
)

# Library functionality
from resources.lib.library import (
    LIBRARY, show_library, show_continue_watching
)

# Player Management (Original and New)
try:
    from resources.lib.players import play_media_with_player_selection # New player system
except ImportError:
    def play_media_with_player_selection(*args, **kwargs):
        log(f"Failed to import play_media_with_player_selection", xbmc.LOGERROR)
        return False

# from resources.lib.episodes import list_episodes # Old episode listing

# New Episode and Season Management
from resources.lib.episodes_new import show_entrypoint, list_episodes_for_season

# API and Data Management
from resources.lib.api import AnimeDBAPI, clear_cache
from resources.lib.history import clear_history
from resources.lib.sync import sync_all, run_monitor, log_sync_results, SyncCancelled
from resources.lib.auth import authenticate, revoke_auth, is_authenticated, test_connection
from resources.lib.auth_tmdb import authenticate_tmdb
from resources.lib.watchlist import toggle_watchlist, sync_watchlist_to_services, is_in_watchlist
from resources.lib.recommendations import get_recommendations, get_similar_anime
from resources.lib.player_manager import reset_players, set_default_player, edit_player as edit_player_config, save_player, update_players
from resources.lib.tmdb_bridge import test_tmdb_connection

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

# Define handle globally for use in all plugin calls
try:
    handle = int(sys.argv[1])
except (IndexError, ValueError):
    handle = -1  # Fallback if not running as plugin

def update_auth_status():
    """Update authentication status in settings"""
    for service in ["anilist", "mal", "trakt"]:
        status_id = f"{service}_auth_status"
        if is_authenticated(service):
            ADDON.setSettingString(status_id, ADDON.getLocalizedString(31011))  # Authorized
        else:
            ADDON.setSettingString(status_id, ADDON.getLocalizedString(31010))  # Not authenticated

def show_settings_menu(handle_id):
    update_auth_status()
    ADDON.openSettings()
    if ADDON.getSettingBool("force_sync"):
        ADDON.setSettingBool("force_sync", False)
        xbmc.executebuiltin(f"RunPlugin(plugin://{ADDON_ID}/?action=sync)")

def router(paramstring):
    params = parse_qs(paramstring[1:])
    action = params.get("action", ["home"])[0]
    current_handle = int(sys.argv[1]) # Always use current handle from sys.argv[1]

    log(f"[ROUTER] Action: \'{action}\', Params: {params}")

    if action == "home":
        home(current_handle)
    elif action == "show_entry": # New entry point for shows (leads to seasons or episodes)
        anime_id = params.get("anime_id", [None])[0]
        source = params.get("source", ["anilist"])[0]
        title = params.get("title", [None])[0]
        if anime_id:
            show_entrypoint(current_handle, anime_id, source, title)
        else:
            log("show_entry: Missing anime_id", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31001), xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(current_handle)

    elif action == "list_episodes_for_season": # Lists episodes for a specific season
        anime_id = params.get("anime_id", [None])[0]
        source = params.get("source", ["anilist"])[0]
        season_number = params.get("season_number", [None])[0]
        tmdb_id = params.get("tmdb_id", [None])[0]
        # show_title = params.get("show_title", [None])[0] # Not strictly needed by function if anime_id is there
        if anime_id and season_number is not None:
            # The list_episodes_for_season function in episodes_new.py needs to be checked for its exact signature
            # It expects: handle, anime_id, source, season_number, show_details_anilist=None, tmdb_id=None
            # We might need to fetch show_details_anilist first or pass None
            list_episodes_for_season(current_handle, anime_id, source, int(season_number), tmdb_id=tmdb_id)
        else:
            log("list_episodes_for_season: Missing anime_id or season_number", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31002), xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(current_handle)

    elif action == "play_item_route":
        # Extract parameters
        anime_id = params.get("anime_id", [None])[0]
        source = params.get("source", ["anilist"])[0]
        episode = params.get("episode", [None])[0]
        url = params.get("url", [None])[0]
        total_episodes = params.get("total_episodes", [None])[0]
        
        if not all([anime_id, episode, url]):
            log(f"play_item_route: Missing required parameters. anime_id: {anime_id}, episode: {episode}, url: {url}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                "Playback Error",
                "Missing required parameters for playback",
                xbmcgui.NOTIFICATION_ERROR
            )
            return
            
        try:
            # Use our new player to handle playback with progress tracking
            from resources.lib.player import play_episode
            
            # Convert to appropriate types
            episode_num = int(episode)
            total_eps = int(total_episodes) if total_episodes and total_episodes.isdigit() else None
            
            # Start playback with progress tracking
            play_episode(
                anime_id=anime_id,
                source=source,
                episode=episode_num,
                url=url,
                total_episodes=total_eps
            )
            
            # Update the "Continue Watching" section
            xbmc.executebuiltin('Container.Refresh')
            
        except Exception as e:
            log(f"Error in play_item_route: {str(e)}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                "Playback Error",
                f"Failed to start playback: {str(e)}",
                xbmcgui.NOTIFICATION_ERROR
            )
        return

    # Old list_episodes - to be deprecated or used as a fallback if show_entrypoint is not used.
    # For now, let's assume new anime listings will point to "show_entry".
    # If some parts of UI still call "list_episodes", it will use the old system.
    elif action == "list_episodes": 
        log("Router: Received old 'list_episodes' action. Consider updating call to 'show_entry'.")
        from resources.lib.episodes import list_episodes as old_list_episodes # Import old one specifically
        anime_id = params.get("id", [""])[0]
        source = params.get("source", ["anilist"])[0]
        title = params.get("title", [None])[0]
        old_list_episodes(current_handle, anime_id, source, title)

    # Library actions
    elif action == "library":
        show_library(current_handle)
    elif action == "library_status":
        status = params.get("status", [None])[0]
        show_library(current_handle, status)
    elif action == "continue_watching":
        show_continue_watching(current_handle)
    elif action == "add_to_library":
        anime_id = params.get("anime_id", [None])[0]
        source = params.get("source", ["anilist"])[0]
        status = params.get("status", ["PLANNING"])[0]
        if anime_id:
            LIBRARY.add_to_library(anime_id, source, status)
            xbmc.executebuiltin('Container.Refresh')
    elif action == "remove_from_library":
        anime_id = params.get("id", [None])[0]
        source = params.get("source", ["anilist"])[0]
        if anime_id:
            LIBRARY.remove_from_library(anime_id, source)
            xbmc.executebuiltin('Container.Refresh')
    elif action == "update_status":
        anime_id = params.get("id", [None])[0]
        source = params.get("source", ["anilist"])[0]
        status = params.get("status", [None])[0]
        if anime_id and status:
            LIBRARY.add_to_library(anime_id, source, status)
            xbmc.executebuiltin('Container.Refresh()')
    elif action == "watchlist":
        from resources.lib.watchlist import list_watchlist
        list_watchlist(current_handle)
    elif action == "last_watched":
        from resources.lib.ui import list_last_watched
        list_last_watched(current_handle)
    elif action == "trending":
        page = int(params.get("page", [1])[0])
        source = params.get("source", [None])[0]
        list_trending(current_handle, page=page, source=source)
    elif action == "seasonal":
        page = int(params.get("page", [1])[0])
        year = params.get("year", [None])[0]
        if year:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None
        season = params.get("season", [None])[0]
        source = params.get("source", [None])[0]
        list_seasonal(current_handle, year=year, season=season, page=page, source=source)
                
    elif action == "genres":
        list_genres(current_handle)
    elif action == "list_genre": # Specific genre listing
        genre_name = params.get("genre", [""])[0]
        page = params.get("page", [1])[0]
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        list_genre(current_handle, genre_name, page)
    # elif action == "genre": # This seems like a duplicate of list_genre or for a different purpose
    #     genre_name = params.get("genre", [""])[0]
    #     list_anime(current_handle, AnimeDBAPI().get_by_genre(genre_name), title=f"Genre: {genre_name}")
    # Search actions
    elif action == "search_menu":
        show_search_menu(current_handle)
    elif action == "search_input":
        show_search_input(current_handle)
    elif action == "search_history":
        show_search_history(current_handle)
    elif action == "search_advanced":
        show_advanced_search(current_handle)
    elif action == "clear_search_history":
        delete_search_history()
        xbmc.executebuiltin('Container.Refresh')
    elif action == "delete_search_history":
        try:
            index = int(params.get("index", [0])[0])
            delete_search_history(index)
        except (ValueError, IndexError):
            pass
        xbmc.executebuiltin('Container.Refresh')
    elif action == "search":
        query = params.get("query", [None])[0]
        media_type = params.get("media_type", [None])[0]
        status = params.get("status", [None])[0]
        year = params.get("year", [None])[0]
        genres = params.get("genres", [None])[0]
        sort = params.get("sort", ["SEARCH_MATCH"])[0]
        page = int(params.get("page", [1])[0])
        
        # Prepare filters
        filters = {}
        if media_type:
            filters["media_type"] = media_type
        if status:
            filters["status"] = status
        if year:
            try:
                filters["year"] = int(year)
            except (ValueError, TypeError):
                pass
        if genres:
            filters["genres"] = genres.split(',')
        if sort:
            filters["sort"] = sort
            
        perform_search(current_handle, query, filters if filters else None, page)
    elif action == "list_genre":
        genre = params.get("genre", [""])[0]
        page = params.get("page", [1])[0]
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        search(current_handle, query, media_type, status, year, genre, page)
    elif action == "history":
        list_history(current_handle)
    elif action == "continue_watching":
        list_continue_watching(current_handle)
    elif action == "recommendations":
        list_anime(current_handle, get_recommendations(), title="Recommended Anime")
    elif action == "similar":
        anime_id = params.get("id", [""])[0]
        list_anime(current_handle, get_similar_anime(anime_id), title="Similar Anime")
    elif action == "upcoming":
        list_upcoming(current_handle)
    elif action == "seasonal":
        list_anime(current_handle, AnimeDBAPI().seasonal(), title="Seasonal Anime")
    elif action == "calendar":
        list_calendar(current_handle)
    elif action == "calendar_date":
        date_str = params.get("date", [""])[0]
        list_calendar_date(current_handle, date_str)
    elif action == "settings":
        show_settings_menu(current_handle)
    elif action == "auth_tmdb":
        authenticate_tmdb()
    elif action == "test_connection":
        service = params.get("service", [""])[0]
        if service == "tmdb":
            ok, msg = test_tmdb_connection()
            xbmcgui.Dialog().notification("TMDB", msg, xbmcgui.NOTIFICATION_INFO if ok else xbmcgui.NOTIFICATION_ERROR)
        elif service in ["anilist", "mal", "trakt"]:
            ok, msg = test_connection(service)
            xbmcgui.Dialog().notification(service.upper(), msg, xbmcgui.NOTIFICATION_INFO if ok else xbmcgui.NOTIFICATION_ERROR)
        else:
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31005)}: {service}", xbmcgui.NOTIFICATION_ERROR)
    elif action == "clear_cache":
        if xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31006)):
            try:
                if clear_cache():
                    xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31007), xbmcgui.NOTIFICATION_INFO)
            except Exception as e:
                log(f"Error clearing cache: {e}", xbmc.LOGERROR)
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31008)}: {e}", xbmcgui.NOTIFICATION_ERROR)
    elif action == "clear_history":
        if xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31009)):
            try:
                if clear_history():
                    xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31010), xbmcgui.NOTIFICATION_INFO)
            except Exception as e:
                log(f"Error clearing history: {e}", xbmc.LOGERROR)
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31011)}: {e}", xbmcgui.NOTIFICATION_ERROR)
    elif action == "sync":
        import threading
        progress = xbmcgui.DialogProgress()
        progress.create(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(30902))
        cancel_flag = threading.Event()
        sync_results_container = [None] # Use a list to pass by reference
        
        def progress_callback(msg, pct):
            if progress:
                progress.update(pct, message=msg)
        
        sync_thread_obj = threading.Thread(
            target=lambda: sync_results_container.__setitem__(
                0, 
                sync_all(
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag
                )
            )
        )
        
        sync_thread_obj.start()
        cancelled_by_user = False
        
        while sync_thread_obj.is_alive():
            xbmc.sleep(100)
            if progress.iscanceled():
                if xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(30905)):
                    cancel_flag.set()
                    cancelled_by_user = True
                    break
                else:
                    progress.update(
                        progress.getPercent() if hasattr(progress, 'getPercent') else 
                        (progress.get_position()[0] if isinstance(progress.get_position(), list) else progress.get_position()),
                        message=ADDON.getLocalizedString(30906)
                    )
        
        sync_thread_obj.join(timeout=5)
        progress.close()
        sync_results = sync_results_container[0]
        
        if cancelled_by_user:
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31003), xbmcgui.NOTIFICATION_WARNING)
        elif isinstance(sync_results, dict) and "error" in sync_results:
            log(f"Sync failed: {sync_results['error']}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31004)}: {sync_results['error']}", xbmcgui.NOTIFICATION_ERROR)
        elif sync_results is None: # Can happen if sync_all returns None on error/cancel
            log(f"Sync did not return results, possibly cancelled or error within sync_all.", xbmc.LOGWARNING)
            if not cancelled_by_user: # If not cancelled by user, assume error
                 xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31004), xbmcgui.NOTIFICATION_ERROR)
        else:
            log("Sync completed successfully")
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31002), xbmcgui.NOTIFICATION_INFO)
            log_sync_results(sync_results.get("watchlist", {}), sync_results.get("history", {}))

    elif action == "create_player":
        player_data = edit_player_config() # From player_manager
        if player_data:
            if save_player(player_data):
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31012)} {player_data.get('name')}", xbmcgui.NOTIFICATION_INFO)
    elif action == "configure_players": # Likely for managing players
        from resources.lib.player_manager import manage_players_dialog
        manage_players_dialog()
    elif action == "set_defaultplayer":
        media_type = params.get("media_type", [""])[0]
        if media_type in ["movie", "tv"]:
            set_default_player(media_type)
            xbmcgui.Dialog().ok(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31014)} {media_type}.")
        else:
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31015), xbmcgui.NOTIFICATION_ERROR)
    elif action == "update_players":
        url = ADDON.getSetting("players_url")
        if url:
            if update_players(url):
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31016), xbmcgui.NOTIFICATION_INFO)
            else:
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31017), xbmcgui.NOTIFICATION_ERROR)
        else:
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31018), xbmcgui.NOTIFICATION_ERROR)

    elif action == "toggle_watchlist":
        anime_id = params.get("id", [""])[0]
        source = params.get("source", ["anilist"])[0]
        if anime_id:
            if toggle_watchlist(anime_id, source):
                status = "added to" if is_in_watchlist(anime_id, source) else "removed from"
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31019)} {status} {ADDON.getLocalizedString(31020)}", xbmcgui.NOTIFICATION_INFO)
        else:
            log("toggle_watchlist: Missing anime_id", xbmc.LOGERROR)

    elif action == "sync_watchlist":
        try:
            if sync_watchlist_to_services():
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31021), xbmcgui.NOTIFICATION_INFO)
            else:
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31022), xbmcgui.NOTIFICATION_ERROR)
        except Exception as e:
            log(f"Error syncing watchlist: {e}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31023)}: {e}", xbmcgui.NOTIFICATION_ERROR)

    elif action in ["auth_anilist", "auth_mal", "auth_trakt"]:
        service_name = action.split("_")[1]
        revoke = params.get("revoke", ["0"])[0] == "1"
        
        if revoke:
            if xbmcgui.Dialog().yesno(f"Revoke {service_name.upper()}", f"Are you sure you want to revoke {service_name.upper()} authorization?"):
                if revoke_auth(service_name):
                    xbmcgui.Dialog().notification(f"{service_name.upper()} {ADDON.getLocalizedString(31024)}", ADDON.getLocalizedString(31025), xbmcgui.NOTIFICATION_INFO)
                    update_auth_status()
                else:
                    xbmcgui.Dialog().notification(f"{service_name.upper()} {ADDON.getLocalizedString(31024)}", ADDON.getLocalizedString(31026), xbmcgui.NOTIFICATION_ERROR)
        else:
            success, message = authenticate(service_name)
            if success:
                update_auth_status()
            else:
                xbmcgui.Dialog().ok(f"{service_name.upper()} {ADDON.getLocalizedString(31027)}", message)
    else:
        log(f"Unknown action: {action}", xbmc.LOGWARNING)
        home(current_handle) # Fallback to home

if __name__ == "__main__":
    # Check if running as script or plugin
    if len(sys.argv) > 1 and sys.argv[0] == ADDON_ID:
        # Running as script with arguments
        if len(sys.argv) > 1:
            script_action = sys.argv[1]
            if script_action == "set_defaultplayer" and len(sys.argv) > 2:
                media_type = sys.argv[2]
                set_default_player(media_type)
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), f"{ADDON.getLocalizedString(31014)} {media_type}", xbmcgui.NOTIFICATION_INFO)
            elif script_action == "update_players":
                url = ADDON.getSetting("players_url")
                if url:
                    if update_players(url):
                        xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31016), xbmcgui.NOTIFICATION_INFO)
                    else:
                        xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31017), xbmcgui.NOTIFICATION_ERROR)
                else:
                    xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31018), xbmcgui.NOTIFICATION_ERROR)
            elif script_action == "configure_players":
                reset_players()
                xbmcgui.Dialog().notification(ADDON.getLocalizedString(30900), ADDON.getLocalizedString(31013), xbmcgui.NOTIFICATION_INFO)
            else:
                log(f"Unknown script action: {script_action}", xbmc.LOGWARNING)
    else:
        # Running as plugin
        router(sys.argv[2] if len(sys.argv) > 2 else "")
