try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
except ImportError:
    from resources.lib import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs

import time
import threading
import json
from datetime import datetime

from resources.lib.api import AnimeDBAPI
from resources.lib.history import get_watch_history, record_watch
from resources.lib.watchlist import get_local_watchlist as get_watchlist_items

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

class SyncCancelled(Exception):
    pass

def sync_ratings(services, progress=None, progress_start=0, progress_range=20):
    """Sync ratings between services with progress tracking.

    Args:
        services (list): List of services to sync.
        progress: Progress dialog object.
        progress_start (int): Starting progress percentage.
        progress_range (int): Range of progress percentage to use.

    Returns:
        dict: Results of the sync operation.
    """
    results = {
        "total_items": 0,
        "synced_items": 0,
        "errors": [],
        "service_results": {}
    }

    if not services:
        return results

    for service in services:
        try:
            # Placeholder for actual rating sync logic
            log(f"Syncing ratings for {service}...", xbmc.LOGINFO)
            # Simulate some work
            time.sleep(1)
            results["synced_items"] += 1
        except Exception as e:
            log(f"Error syncing ratings for {service}: {e}", xbmc.LOGERROR)
            results["errors"].append({"service": service, "error": str(e)})

    if progress:
        progress.update(progress_start + progress_range, "Ratings Sync", "Ratings sync complete.")

    return results

def sync_all(progress_callback=None, cancel_flag=None):
    """Synchronize all enabled services with progress tracking and cancellation support.

    Args:
        progress_callback (function): Function to call with progress updates (message, percentage).
        cancel_flag (threading.Event): Threading event to check for cancellation.

    Returns:
        dict: Results of the sync operation.
    """
    def update_progress(message, percent):
        if progress_callback:
            progress_callback(message, percent)
    
    def is_cancelled():
        return cancel_flag.is_set() if cancel_flag else False
    
    # Get enabled services
    enabled_services = []
    if ADDON.getSettingBool("anilist_enabled"):
        enabled_services.append("anilist")
    if ADDON.getSettingBool("mal_enabled"):
        enabled_services.append("mal")
    if ADDON.getSettingBool("trakt_enabled"):
        enabled_services.append("trakt")
    
    # Get sync settings
    # This was the line causing the TypeError: `sync_ratings = ADDON.getSettingBool("sync_ratings")`
    # It overwrote the function `sync_ratings` with a boolean value.
    # We should use a different variable name for the setting.
    should_sync_ratings_setting = ADDON.getSettingBool("sync_ratings")
    
    if not enabled_services:
        log("No services enabled for sync", xbmc.LOGWARNING)
        return {"error": "No services enabled for sync"}
    
    results = {}
    total_steps = 0
    current_step = 0
    
    # Count total steps for progress
    if ADDON.getSettingBool("sync_watchlist"):
        total_steps += 1
    if ADDON.getSettingBool("sync_history"):
        total_steps += 1
    if should_sync_ratings_setting: # Use the new variable name here
        total_steps += 1
    
    if total_steps == 0:
        return {"error": "No sync operations enabled in settings"}
    
    try:
        # Sync watchlist if enabled
        if ADDON.getSettingBool("sync_watchlist"):
            if is_cancelled():
                raise SyncCancelled("Sync cancelled by user during watchlist sync.")
                
            update_progress("Syncing watchlist...", int((current_step / total_steps) * 100))
            results["watchlist"] = sync_watchlists(enabled_services)
            current_step += 1
        
        # Sync history if enabled
        if ADDON.getSettingBool("sync_history"):
            if is_cancelled():
                raise SyncCancelled("Sync cancelled by user during history sync.")
                
            update_progress("Syncing watch history...", int((current_step / total_steps) * 100))
            history_results = sync_history(enabled_services)
            results["history"] = history_results
            
            # If history sync returned an error, include it in results
            if isinstance(history_results, dict) and "error" in history_results:
                results["error"] = history_results["error"] # This might overwrite other errors
            
            current_step += 1
        
        # Sync ratings if enabled
        if should_sync_ratings_setting: # Use the new variable name here
            if is_cancelled():
                raise SyncCancelled("Sync cancelled by user during ratings sync.")
                
            update_progress("Syncing ratings...", int((current_step / total_steps) * 100))
            # Now this calls the function `sync_ratings`, not the boolean setting value.
            ratings_sync_result = sync_ratings(enabled_services) 
            results["ratings"] = ratings_sync_result
            if isinstance(ratings_sync_result, dict) and "error" in ratings_sync_result:
                if "error" not in results: # Avoid overwriting previous errors
                    results["error"] = ratings_sync_result["error"]
                else:
                    results["error"] += f"; Ratings: {ratings_sync_result.get('error', '')}"
            current_step += 1
        
        update_progress("Sync completed", 100)
        return results

    except SyncCancelled as sc:
        log(str(sc), xbmc.LOGINFO)
        return {"cancelled": True, "message": str(sc)}
    except Exception as e:
        log(f"Error during sync: {str(e)}", xbmc.LOGERROR)
        import traceback
        log(traceback.format_exc(), xbmc.LOGERROR)
        return {"error": str(e)}

def sync_watchlists(services, progress=None, progress_start=0, progress_range=40):
    """Sync watchlists between services with progress tracking.

    Args:
        services (list): List of services to sync.
        progress: Progress dialog object.
        progress_start (int): Starting progress percentage.
        progress_range (int): Range of progress percentage to use.

    Returns:
        dict: Results of the sync operation.
    """
    results = {
        "total_items": 0,
        "synced_items": 0,
        "errors": [],
        "service_results": {}
    }
    
    if not services:
        return results
    
    try:
        api = AnimeDBAPI()
        local_watchlist = get_watchlist_items()
        results["total_items"] = len(local_watchlist)
        
        # Update progress
        if progress:
            progress.update(
                progress_start,
                "Syncing Watchlists",
                f"Processing {len(local_watchlist)} watchlist items..."
            )
        
        # Process each service
        for i, service in enumerate(services):
            service_result = {
                "items_processed": 0,
                "items_added": 0,
                "items_removed": 0,
                "errors": []
            }
            
            try:
                # Get service watchlist
                if service == "anilist":
                    service_watchlist = api.anilist_watchlist()
                elif service == "mal":
                    service_watchlist = api.mal_watchlist()
                elif service == "trakt":
                    service_watchlist = api.trakt_watchlist()
                else:
                    continue
                
                # Process each item in local watchlist
                for j, item in enumerate(local_watchlist):
                    try:
                        # Update progress
                        if progress:
                            progress_pct = progress_start + int((i + j/len(local_watchlist)) * (progress_range/len(services)))
                            progress.update(
                                progress_pct,
                                f"Syncing to {service.upper()}",
                                f"Processing: {item.get('title', 'Unknown')}"
                            )
                        
                        # Here you would implement the actual sync logic
                        # For now, we"ll just count the items
                        service_result["items_processed"] += 1
                        
                    except Exception as e:
                        error_msg = f"Error processing {item.get('title', 'Unknown')}: {str(e)}"
                        log(error_msg, xbmc.LOGERROR)
                        service_result["errors"].append(error_msg)
                
                # Update results
                results["synced_items"] += service_result["items_processed"]
                results["service_results"][service] = service_result
                
            except Exception as e:
                error_msg = f"Error syncing {service} watchlist: {str(e)}"
                log(error_msg, xbmc.LOGERROR)
                results["errors"].append(error_msg)
                results["service_results"][service] = {"error": str(e)}
        
        return results
        
    except Exception as e:
        error_msg = f"Error in sync_watchlists: {str(e)}"
        log(error_msg, xbmc.LOGERROR)
        results["errors"].append(error_msg)
        return results

def sync_history(services, progress=None, progress_start=50, progress_range=40, anime_id=None, episode=None):
    """
    Sync watch history between services with progress tracking
    
    Args:
        services (list): List of services to sync
        progress: Progress dialog object
        progress_start (int): Starting progress percentage
        progress_range (int): Range of progress percentage to use
        anime_id (str, optional): Specific anime ID to sync
        episode (int, optional): Specific episode to sync
    
    Returns:
        dict: Results of the sync operation
    """
    results = {
        "total_items": 0,
        "synced_items": 0,
        "errors": [],
        "service_results": {}
    }
    
    if not services:
        return results
    
    try:
        # Get watch history from local database
        local_history = get_watch_history()
        
        # Filter for specific anime/episode if provided
        if anime_id is not None:
            if episode is not None:
                # Filter for specific episode
                local_history = [h for h in local_history 
                               if h.get("anime_id") == anime_id 
                               and h.get("episode") == episode]
            else:
                # Filter for all episodes of a specific anime
                local_history = [h for h in local_history 
                               if h.get("anime_id") == anime_id]
            
            if not local_history:
                log(f"No history found for anime_id: {anime_id}" + 
                    (f" episode: {episode}" if episode is not None else ""), 
                    xbmc.LOGWARNING)
                return {"success": False, "message": "No matching history found"}
        
        results["total_items"] = len(local_history)
        
        # Update progress
        if progress:
            progress.update(
                progress_start,
                "Syncing Watch History",
                f"Processing {len(local_history)} history items..."
            )
        
        # Process each service
        for i, service in enumerate(services):
            service_result = {
                "items_processed": 0,
                "items_synced": 0,
                "errors": []
            }
            
            try:
                # Process each item in history
                for j, item in enumerate(local_history):
                    try:
                        # Update progress
                        if progress:
                            # Ensure local_history is not empty to avoid division by zero
                            progress_denominator = len(local_history) if len(local_history) > 0 else 1
                            progress_pct = progress_start + int((i + j/progress_denominator) * (progress_range/len(services)))
                            progress.update(
                                progress_pct,
                                f"Syncing to {service.upper()}",
                                f"Processing: {item.get('title', 'Unknown')} - Episode {item.get('episode', '?')}"
                            )
                        
                        # Here you would implement the actual sync logic
                        # For now, we"ll just count the items
                        service_result["items_processed"] += 1
                        
                        # Simulate some items failing to sync
                        # if j % 10 == 0:  # Simulate 10% failure rate
                        #     raise Exception("Simulated sync error")
                            
                        service_result["items_synced"] += 1
                        
                    except Exception as e:
                        error_msg = f"Error processing {item.get('title', 'Unknown')}: {str(e)}"
                        log(error_msg, xbmc.LOGERROR)
                        service_result["errors"].append(error_msg)
                
                # Update results
                results["synced_items"] += service_result["items_synced"]
                results["service_results"][service] = service_result
                
            except Exception as e:
                error_msg = f"Error syncing {service} history: {str(e)}"
                log(error_msg, xbmc.LOGERROR)
                results["errors"].append(error_msg)
                results["service_results"][service] = {"error": str(e)}
        
        return results
        
    except Exception as e:
        error_msg = f"Error in sync_history: {str(e)}"
        log(error_msg, xbmc.LOGERROR)
        results["errors"].append(error_msg)
        return results

def update_watch_status(anime_id, episode, status="completed", progress=100, source="anilist", title="", image="", episode_count=0, sync_services=True):
    """
    Update watch status for an anime episode and sync with services
    
    Args:
        anime_id (str): ID of the anime
        episode (int): Episode number
        status (str): Watch status (e.g., "completed", "watching")
        progress (int): Watch progress percentage (0-100)
        source (str): Source of the anime (anilist, mal, etc.)
        title (str): Title of the anime
        image (str): URL of the anime image
        episode_count (int): Total number of episodes
        sync_services (bool): Whether to sync with external services
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Record the watch in local history
        from resources.lib.history import record_watch
        record_watch(
            anime_id=anime_id,
            title=title,
            episode=episode,
            progress=progress,
            status=status,
            image=image,
            source=source,
            episode_count=episode_count
        )
        
        log(f"Updated watch status for {title} episode {episode}: {status} ({progress}%)")
        
        # Sync with external services if enabled
        if sync_services and ADDON.getSettingBool("sync_enabled") and ADDON.getSettingBool("sync_history"):
            services_to_sync_with = [] # Renamed to avoid conflict
            if ADDON.getSettingBool("anilist_enabled") and source != "anilist":
                services_to_sync_with.append("anilist")
            if ADDON.getSettingBool("mal_enabled") and source != "mal":
                services_to_sync_with.append("mal")
            if ADDON.getSettingBool("trakt_enabled") and source != "trakt":
                services_to_sync_with.append("trakt")
            
            if services_to_sync_with:
                log(f"Syncing watch status with services: {', '.join(services_to_sync_with)}")
                try:
                    # Sync the specific anime/episode that was just updated
                    sync_results = sync_history(
                        services=services_to_sync_with,
                        anime_id=anime_id,
                        episode=episode,
                        progress=None
                    )
                    
                    if "error" in sync_results:
                        log(f"Error syncing watch status: {sync_results.get('error')}", xbmc.LOGERROR)
                    else:
                        log(f"Successfully synced watch status with {len(services_to_sync_with)} services")
                except Exception as e:
                    log(f"Error during watch status sync: {str(e)}", xbmc.LOGERROR)
        
        return True
        
    except Exception as e:
        log(f"Error updating watch status: {str(e)}", xbmc.LOGERROR)
        return False

def log_sync_results(watchlist_results, history_results):
    """
    Log the results of a sync operation
    
    Args:
        watchlist_results (dict): Results from watchlist sync
        history_results (dict): Results from history sync
    """
    try:
        # Log watchlist results
        log("=" * 50)
        log("SYNC RESULTS")
        log("-" * 50)
        
        if watchlist_results:
            log(f"WATCHLIST SYNC: {watchlist_results.get('synced_items', 0)}/{watchlist_results.get('total_items', 0)} items synced")
            for service, result in watchlist_results.get("service_results", {}).items():
                log(f"  {service.upper()}: Processed {result.get('items_processed', 0)}, Added {result.get('items_added', 0)}, Removed {result.get('items_removed', 0)}")
                if result.get("errors"):
                    for err in result["errors"]:
                        log(f"    ERROR: {err}", xbmc.LOGWARNING)
            if watchlist_results.get("errors"):
                for err in watchlist_results["errors"]:
                    log(f"  OVERALL WATCHLIST ERROR: {err}", xbmc.LOGERROR)
        else:
            log("WATCHLIST SYNC: No results or not performed.")

        log("-" * 50)
        # Log history results
        if history_results:
            log(f"HISTORY SYNC: {history_results.get('synced_items', 0)}/{history_results.get('total_items', 0)} items synced")
            for service, result in history_results.get("service_results", {}).items():
                log(f"  {service.upper()}: Processed {result.get('items_processed', 0)}, Synced {result.get('items_synced', 0)}")
                if result.get("errors"):
                    for err in result["errors"]:
                        log(f"    ERROR: {err}", xbmc.LOGWARNING)
            if history_results.get("errors"):
                for err in history_results["errors"]:
                    log(f"  OVERALL HISTORY ERROR: {err}", xbmc.LOGERROR)
        else:
            log("HISTORY SYNC: No results or not performed.")
            
        log("=" * 50)

    except Exception as e:
        log(f"Error logging sync results: {str(e)}", xbmc.LOGERROR)

class SyncManager:
    def __init__(self):
        self.threads = []

    def start_thread(self, target, name, *args, **kwargs):
        thread = threading.Thread(target=target, name=name, args=args, kwargs=kwargs)
        thread.start()
        self.threads.append(thread)

    def cleanup(self):
        for thread in self.threads:
            thread.join()
        self.threads.clear()

# Example usage of SyncManager
sync_manager = SyncManager()

def run_monitor():
    """Run the sync monitor in a separate thread."""
    def monitor_loop():
        while not xbmc.abortRequested:
            try:
                if ADDON.getSettingBool("sync_enabled") and ADDON.getSettingBool("sync_on_idle"):
                    # Check if Kodi is idle (this is a placeholder, actual idle detection is complex)
                    # For now, we just sync based on interval if sync_on_idle is true
                    # A more robust idle check would involve Kodi JSON-RPC calls or specific conditions
                    log("Idle sync check (currently interval based if enabled)")
                    # Perform sync based on interval
                    sync_interval_hours = ADDON.getSettingInt("sync_interval")
                    last_sync_time_str = ADDON.getSetting("last_sync_time")
                    
                    if last_sync_time_str:
                        last_sync_time = datetime.fromisoformat(last_sync_time_str)
                        if (datetime.now() - last_sync_time).total_seconds() > sync_interval_hours * 3600:
                            log("Sync interval reached, starting sync...")
                            sync_all() # No progress dialog for background sync
                            ADDON.setSetting("last_sync_time", datetime.now().isoformat())
                    else:
                        # First time sync or setting cleared
                        log("No last sync time found, syncing now...")
                        sync_all()
                        ADDON.setSetting("last_sync_time", datetime.now().isoformat())
                
                # Sleep for a reasonable interval before checking again
                # This interval should be configurable or a sensible default
                # For now, let's use a fixed interval (e.g., 15 minutes)
                monitor_interval_seconds = 15 * 60 
                for _ in range(monitor_interval_seconds):
                    if xbmc.abortRequested:
                        break
                    time.sleep(1)
            except Exception as e:
                log(f"Error in sync monitor loop: {str(e)}", xbmc.LOGERROR)
                # Sleep for a bit longer on error to avoid rapid error loops
                for _ in range(300): # 5 minutes
                    if xbmc.abortRequested:
                        break
                    time.sleep(1)
            if xbmc.abortRequested:
                break
        log("Sync monitor loop aborted.")

    if ADDON.getSettingBool("sync_enabled") and ADDON.getSettingBool("sync_on_idle"):
        log("Starting sync monitor thread...")
        sync_manager.start_thread(target=monitor_loop, name="MonitorThread")
    else:
        log("Sync monitor not started (disabled in settings).")

# Example of how to call sync_all with progress and cancellation
# This would typically be called from default.py when a user triggers a manual sync
if __name__ == "__main__":
    # This is just for testing the sync module directly
    # In a real scenario, this would be invoked by the plugin router
    
    # Mock ADDON settings for testing
    class MockAddon:
        def getSettingBool(self, setting_id):
            if setting_id == "sync_ratings": return True
            if setting_id == "sync_watchlist": return True
            if setting_id == "sync_history": return True
            if setting_id == "anilist_enabled": return True
            return False
        def getAddonInfo(self, info_id):
            return "plugin.video.animedb.helper.test"
    
    ADDON = MockAddon() # Override the global ADDON for testing
    
    log("Testing sync_all...")
    progress_dialog = xbmcgui.DialogProgress()
    progress_dialog.create("Sync Test", "Starting sync...")
    cancel_event = threading.Event()
    
    def test_progress_callback(message, percent):
        log(f"Progress: {percent}% - {message}")
        if progress_dialog.iscanceled():
            cancel_event.set()
        progress_dialog.update(percent, message)
    
    sync_results = sync_all(progress_callback=test_progress_callback, cancel_flag=cancel_event)
    progress_dialog.close()
    log(f"Sync results: {json.dumps(sync_results, indent=2)}")

    try:
        # ...existing code...
        pass
    finally:
        sync_manager.cleanup()

