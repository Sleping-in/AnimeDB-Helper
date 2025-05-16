try:
    import xbmc
    import xbmcaddon
except ImportError:
    from resources.lib import xbmc, xbmcaddon

import time
import threading
import traceback

from resources.lib.auth import refresh_token, is_authenticated
from resources.lib.sync import run_monitor, log_sync_results, SyncManager
from resources.lib.history import prune_history

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Logging helper
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID} Service: {message}", level=level)

# Initialize SyncManager
sync_manager = SyncManager()

class AnimeDBMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.last_sync_time = 0
        self.last_token_refresh_time = 0
        self.last_history_prune_time = 0

    def onSettingsChanged(self):
        # Handle specific setting changes here
        if ADDON.getSettingBool("sync_enabled"):
            log("Sync is enabled")
        else:
            log("Sync is disabled")

    def check_tokens(self):
        current_time = time.time()
        if current_time - self.last_token_refresh_time < 86400:
            return

        services = []
        if ADDON.getSettingBool('anilist_enabled'):
            services.append('anilist')
        if ADDON.getSettingBool('mal_enabled'):
            services.append('mal')
        if ADDON.getSettingBool('trakt_enabled'):
            services.append('trakt')

        for service in services:
            try:
                if is_authenticated(service):
                    log(f"Refreshing {service} token")
                    if refresh_token(service):
                        log(f"Successfully refreshed {service} token")
                    else:
                        log(f"Failed to refresh {service} token", xbmc.LOGWARNING)
            except Exception:
                log(f"Error refreshing {service} token", xbmc.LOGERROR)
                log(traceback.format_exc(), xbmc.LOGERROR)

        self.last_token_refresh_time = current_time

    def check_sync(self):
        """Start a sync thread if the configured interval has elapsed."""
        try:
            if not ADDON.getSettingBool('sync_enabled'):
                return

            # sync_interval in hours; default to 6
            interval_hours = max(1, int(ADDON.getSetting('sync_interval') or 6))
            interval_secs = interval_hours * 3600
            current_time = time.time()

            if current_time - self.last_sync_time >= interval_secs:
                log(f"Starting scheduled sync (last sync: {time.ctime(self.last_sync_time)})")
                sync_manager.start_thread(target=self._run_sync, name="SyncThread")
                self.last_sync_time = current_time
        except Exception:
            log("Error in check_sync", xbmc.LOGERROR)
            log(traceback.format_exc(), xbmc.LOGERROR)

    def _run_sync(self):
        """Perform the actual sync in a background thread."""
        try:
            from resources.lib.sync import sync_all
            results = sync_all()

            if results:
                log("Sync completed successfully")
                log_sync_results(
                    results.get('watchlist', {}),
                    results.get('history', {})
                )
            else:
                log("Sync failed or nothing to do", xbmc.LOGWARNING)

        except Exception:
            log("Error in _run_sync", xbmc.LOGERROR)
            log(traceback.format_exc(), xbmc.LOGERROR)

    def check_history_prune(self):
        """Prune history once per day if enabled."""
        try:
            current_time = time.time()
            if current_time - self.last_history_prune_time < 86400:
                return

            if ADDON.getSettingBool('history_enabled'):
                log("Pruning watch history")
                prune_history()

            self.last_history_prune_time = current_time
        except Exception:
            log("Error in check_history_prune", xbmc.LOGERROR)
            log(traceback.format_exc(), xbmc.LOGERROR)

# Main service entry point
if __name__ == '__main__':
    log("Service started")
    try:
        monitor = AnimeDBMonitor()
        log("Starting sync monitor thread")
        sync_monitor = threading.Thread(target=run_monitor, name="SyncMonitor")
        sync_monitor.daemon = True
        sync_monitor.start()

        log("Entering main loop")
        while not monitor.abortRequested():
            monitor.check_tokens()
            monitor.check_sync()
            monitor.check_history_prune()
            # sleep up to 5 minutes, or break early on abort
            if monitor.waitForAbort(300):
                break

        log("Service stopping...")
        if sync_monitor.is_alive():
            log("Waiting for sync monitor to stop...")
            sync_monitor.join(timeout=30)
        log("Service stopped")

    except Exception:
        log("Fatal error in service", xbmc.LOGERROR)
        log(traceback.format_exc(), xbmc.LOGERROR)
        raise
    finally:
        sync_manager.cleanup()
