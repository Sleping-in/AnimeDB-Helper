"""
players.py: Unified player management and external player integration for Kodi Omega anime plugin.

This module provides a flexible player system for launching internal and external players, handling resume support,
player selection dialogs, and player configuration. It is adapted from TMDB Helper's player system for local use.
All file I/O uses xbmcvfs for Kodi Omega compatibility.
"""
try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
except ImportError:
    from resources.lib import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs

import re
from urllib.parse import urlencode, quote_plus
import sys
import os
import traceback
import json # For item_meta_json in play route

# Logging function
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_PATH = ADDON.getAddonInfo("path")

def log(message, level=xbmc.LOGINFO):
    if isinstance(message, list):
        message = " ".join(map(str, message))
    xbmc.log(f"{ADDON_ID} (players.py): {message}", level=level)

# --- TMDB Helper Player System (adapted for local context) ---

class ListItem:
    """
    Wrapper for xbmcgui.ListItem with additional validation and convenience methods.
    """
    def __init__(self, label=None, label2=None, art=None, path=None, is_folder=False):
        if not isinstance(label, (str, type(None))):
            raise ValueError("label must be a string or None")
        if not isinstance(label2, (str, type(None))):
            raise ValueError("label2 must be a string or None")
        if not isinstance(art, (dict, type(None))):
            raise ValueError("art must be a dictionary or None")
        if not isinstance(path, (str, type(None))):
            raise ValueError("path must be a string or None")
        if not isinstance(is_folder, bool):
            raise ValueError("is_folder must be a boolean")

        self.label = label
        self.label2 = label2
        self.art = art if art is not None else {}
        self._path = path
        self._list_item = xbmcgui.ListItem(self.label or "")
        if self.label2:
            self._list_item.setLabel2(self.label2)
        if self.art:
            self._list_item.setArt(self.art)
        if self._path:
            self._list_item.setPath(self._path)
        self._list_item.setIsFolder(is_folder)
        self.properties = {}

    def get_listitem(self):
        return self._list_item

    def getPath(self):
        return self._path

    def setArt(self, art):
        self.art = art
        self._list_item.setArt(art)

    def getProperty(self, key):
        return self.properties.get(key, self._list_item.getProperty(key))

    def setProperty(self, key, value):
        self.properties[key] = str(value)
        return self._list_item.setProperty(key, str(value))

def get_localized_string(string_id):
    return ADDON.getLocalizedString(string_id)

def get_setting(key, setting_type="str"):
    if setting_type == "bool":
        return ADDON.getSettingBool(key)
    elif setting_type == "int":
        try:
            return int(ADDON.getSetting(key))
        except ValueError:
            return 0 # Or some other default
    return ADDON.getSetting(key)

def executebuiltin(cmd):
    xbmc.executebuiltin(cmd)

def boolean(val):
    if isinstance(val, bool):
        return val
    return str(val).lower() in ["true", "1", "yes"]

class PlayerHacks:
    """
    Utility methods for player workarounds and monitoring playback state.
    """
    @staticmethod
    def wait_for_player_hack(to_start=None, timeout=5, poll=0.25, stop_after=0):
        xbmc_monitor, xbmc_player = xbmc.Monitor(), xbmc.Player()
        while (
                not xbmc_monitor.abortRequested()
                and timeout > 0
                and (
                    (to_start and (not xbmc_player.isPlaying() or (isinstance(to_start, str) and not xbmc_player.getPlayingFile().endswith(to_start))))
                    or (not to_start and xbmc_player.isPlaying()))):
            xbmc_monitor.waitForAbort(poll)
            timeout -= poll
        if timeout > 0 and to_start and stop_after:
            xbmc_monitor.waitForAbort(stop_after)
            if xbmc_player.isPlaying() and xbmc_player.getPlayingFile().endswith(to_start):
                xbmc_player.stop()
        return timeout

    @staticmethod
    def update_listing_hack(folder_path=None, reset_focus=None):
        if not folder_path:
            return
        xbmc_monitor = xbmc.Monitor()
        xbmc_monitor.waitForAbort(0.1)
        container_folderpath = xbmc.getInfoLabel("Container.FolderPath")
        if container_folderpath == folder_path:
            return
        executebuiltin(f"Container.Update({folder_path},replace)")
        if not reset_focus:
            return
        timeout = 20
        while not xbmc_monitor.abortRequested() and xbmc.getInfoLabel("Container.FolderPath") != folder_path and timeout > 0:
            xbmc_monitor.waitForAbort(0.25)
            timeout -= 1
        if timeout > 0:
             executebuiltin(reset_focus)
             xbmc_monitor.waitForAbort(0.5)

class PlayerMethods:
    """
    Methods for player selection, dialog building, and command formatting.
    """
    def string_format_map(self, fmt_string):
        formatting_dict = {str(k): str(v) for k, v in self.item.items()}
        common_infolabels = {
            "ListItem.Title": self.item.get("title", ""),
            "ListItem.TVShowTitle": self.item.get("tvshowtitle", self.item.get("title", "")),
            "ListItem.Season": str(self.item.get("season", "")),
            "ListItem.Episode": str(self.item.get("episode", "")),
            "ListItem.Year": str(self.item.get("year", "")),
            "ListItem.Plot": self.item.get("plot", "")
        }
        formatting_dict.update(common_infolabels)
        try:
            return fmt_string.format_map(formatting_dict)
        except KeyError as e:
            log(f"KeyError during string_format_map for key {e} in string: {fmt_string}. Available keys: {formatting_dict.keys()}", xbmc.LOGWARNING)
            return fmt_string 
        except Exception as e:
            log(f"Error during string_format_map: {e} for string: {fmt_string}", xbmc.LOGERROR)
            return fmt_string

    def get_dialog_players(self):
        dialog_play_options = []
        dialog_search_options = []
        raw_players_with_keys = []

        for key, p_data in self.players.items(): 
            p_data["_file_key"] = key 
            raw_players_with_keys.append(p_data)

        def get_sort_key(p_json):
            return (p_json.get("priority", 1000), p_json.get("name", "").lower())
        
        sorted_raw_players = sorted(raw_players_with_keys, key=get_sort_key)

        for player_json_data in sorted_raw_players:
            if boolean(player_json_data.get("disabled", "false")):
                continue
            
            required_addons = player_json_data.get("plugin_dependencies", [])
            if isinstance(required_addons, str): 
                required_addons = [required_addons]
            
            all_deps_met = True
            for dep_addon_id in required_addons:
                if not xbmc.getCondVisibility(f"System.AddonIsEnabled({dep_addon_id})"):
                    all_deps_met = False
                    log(f"Player {player_json_data.get('name', 'Unknown')} skipped, missing dependency: {dep_addon_id}", xbmc.LOGDEBUG)
                    break
            if not all_deps_met:
                continue

            media_context_type = getattr(self, "tmdb_type", "tv")

            if media_context_type == "movie":
                if player_json_data.get("play_movie"): 
                    dialog_play_options.append(self.get_built_player(player_json_data, mode="play_movie"))
                if player_json_data.get("search_movie"):
                    dialog_search_options.append(self.get_built_player(player_json_data, mode="search_movie"))
            elif media_context_type == "tv": 
                if player_json_data.get("play_episode"):
                    dialog_play_options.append(self.get_built_player(player_json_data, mode="play_episode"))
                if player_json_data.get("search_episode"):
                    dialog_search_options.append(self.get_built_player(player_json_data, mode="search_episode"))
        
        return dialog_play_options + dialog_search_options

    def get_built_player(self, player_json_data, mode):
        player_file_key = player_json_data.get("_file_key", player_json_data.get("name", "unknown").lower().replace(" ", "_"))
        action_prefix = get_localized_string(32061) if mode in ["play_movie", "play_episode"] else get_localized_string(137)
        player_display_name = player_json_data.get("name", "Unknown Player")
        dialog_name = f"{action_prefix} {player_display_name}"
        is_folder = mode not in ["play_movie", "play_episode"]
        is_provider_flag = boolean(player_json_data.get("is_provider", "true")) if not is_folder else False
        icon_path = player_json_data.get("icon", "")
        if icon_path and not icon_path.startswith("special://") and not os.path.isabs(icon_path):
            if "." in icon_path and not os.path.sep in icon_path: 
                try:
                    icon_path = xbmcaddon.Addon(icon_path).getAddonInfo("icon")
                except Exception:
                    icon_path = ADDON.getAddonInfo("icon") 
            elif not xbmcvfs.exists(icon_path):
                 icon_path = ADDON.getAddonInfo("icon") 
        elif not icon_path: 
            plugin_id_for_icon = player_json_data.get("plugin_id")
            if plugin_id_for_icon:
                try:
                    icon_path = xbmcaddon.Addon(plugin_id_for_icon).getAddonInfo("icon")
                except Exception:
                    icon_path = ADDON.getAddonInfo("icon")
            else:
                icon_path = ADDON.getAddonInfo("icon")

        return {
            "file_key": player_file_key, 
            "mode": mode,
            "is_folder": is_folder,
            "is_provider": is_provider_flag, 
            "is_resolvable": boolean(player_json_data.get("is_resolvable", "true")),
            "requires_ids": player_json_data.get("requires_ids", {}),
            "make_playlist": boolean(player_json_data.get("make_playlist", "false")),
            "api_language": player_json_data.get("api_language"), 
            "language": player_json_data.get("language"), 
            "name": dialog_name, 
            "plugin_id": player_json_data.get("plugin_id"), 
            "plugin_icon": icon_path, 
            "fallback": player_json_data.get("fallback", {}).get(mode),
            "command": player_json_data.get(mode) or player_json_data.get("command"),
            "player_json_data": player_json_data 
        }

class PlayerDetails:
    """
    Methods for extracting and caching item metadata for playback.
    """
    def get_item_details(self):
        if not hasattr(self, "_item_details_cache"):
            self._item_details_cache = {
                "title": getattr(self, "title", "Unknown Title"),
                "year": getattr(self, "year", ""),
                "season": getattr(self, "season", ""),
                "episode": getattr(self, "episode", ""),
                "tvshowtitle": getattr(self, "tvshowtitle", ""),
                "plot": getattr(self, "plot", ""),
                "id": getattr(self, "anime_id", ""),
                "anilist_id": getattr(self, "anilist_id", ""),
                "tmdb_id": getattr(self, "tmdb_id", ""),
                "imdb_id": getattr(self, "imdb_id", ""),
                "tvdb_id": getattr(self, "tvdb_id", ""),
                "episode_absolute": getattr(self, "episode_absolute", ""),
                "path": getattr(self, "path_for_player", "") 
            }
        return self._item_details_cache

    def set_detailed_item(self, item_meta=None):
        try:
            default_item = {
                "title": "", "year": "", "season": "", "episode": "", "tvshowtitle": "",
                "plot": "", "id": "", "anilist_id": "", "tmdb_id": "", "imdb_id": "", "tvdb_id": "",
                "episode_absolute": "", "path": ""
            }
            
            if item_meta:
                self._item = {**default_item, **item_meta} 
            else:
                self._item = default_item.copy()
                self._item.update({
                    "tmdb_id": getattr(self, "tmdb_id", None),
                    "imdb_id": getattr(self, "imdb_id", None),
                    "tvdb_id": getattr(self, "tvdb_id", None),
                    "title": getattr(self, "title", None),
                    "year": getattr(self, "year", None),
                    "season": getattr(self, "season", None),
                    "episode": getattr(self, "episode", None),
                    "tvshowtitle": getattr(self, "tvshowtitle", None),
                    "plot": getattr(self, "plot", None)
                })
        except Exception as e:
            log(f"Error in set_detailed_item: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)
            self._item = {}

class PlayerProperties:
    """
    Properties for accessing player configuration and item metadata.
    """
    @property
    def players(self):
        if not hasattr(self, "_players_cache"):
            try:
                from resources.lib.player_manager import get_players 
                player_list = get_players() 
                loaded_players_dict = {}
                
                if not player_list:
                    log("No players found in player_list. Using fallback.", xbmc.LOGWARNING)
                
                for player_data in player_list:
                    try:
                        player_name = player_data.get("name")
                        if not player_name:
                            log(f"Skipping player with missing name: {player_data}", xbmc.LOGWARNING)
                            continue
                        
                        key = player_data.get("id", player_name.lower().replace(" ", "_").replace("-", "_"))
                        loaded_players_dict[key] = player_data
                    except Exception as player_error:
                        log(f"Error processing player data: {player_error}", xbmc.LOGERROR)
                
                if not loaded_players_dict:
                    log("No custom players found. Using Kodi Default Player as fallback.", xbmc.LOGWARNING)
                    loaded_players_dict = { 
                        "kodi_default": {
                            "id": "kodi_default", 
                            "name": "Kodi Default Player", 
                            "plugin_id": "default",
                            "play_episode": "PlayerControl(Play)", 
                            "play_movie": "PlayerControl(Play)", 
                            "is_resolvable": True, 
                            "priority": 9999 
                        }
                    }
                
                self._players_cache = loaded_players_dict
            except ImportError:
                log("Failed to import player_manager or get_players. Player functionality will be limited.", xbmc.LOGERROR)
                self._players_cache = {}
            except Exception as e:
                log(f"Unexpected error in players method: {e}", xbmc.LOGERROR)
                log(traceback.format_exc(), xbmc.LOGERROR)
                self._players_cache = {}
        return self._players_cache

    @property
    def item(self):
        try:
            if not hasattr(self, "_item"):
                self.set_detailed_item() 
            return self._item
        except Exception as e:
            log(f"Error in item property: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)
            return {}

class Players(PlayerProperties, PlayerDetails, PlayerMethods, PlayerHacks):
    """
    Main player controller class. Handles player selection, launching, resume support, and integration with history.
    """
    def __init__(self, item_meta, tmdb_type="tv", selected_player_key=None, selected_mode=None, **kwargs):
        try:
            self.tmdb_type = tmdb_type
            self.anime_id = item_meta.get("id", item_meta.get("anilist_id"))
            self.title = item_meta.get("title", item_meta.get("ep_title", "Unknown Title")) 
            self.year = item_meta.get("year", "")
            self.season = item_meta.get("season", "")
            self.episode = item_meta.get("episode", "")
        except Exception as e:
            log(f"Error initializing Players: {e}")
            self.tvshowtitle = item_meta.get("tvshowtitle", item_meta.get("title", "")) 
            self.plot = item_meta.get("plot", "")
            self.anilist_id = item_meta.get("anilist_id", self.anime_id)
            self.tmdb_id = item_meta.get("tmdb_id", "")
            self.imdb_id = item_meta.get("imdb_id", "")
            self.tvdb_id = item_meta.get("tvdb_id", "")
            self.episode_absolute = item_meta.get("episode_absolute", "")
            self.path_for_player = item_meta.get("path", "") 
        try:
            # Validate and set additional metadata
            self.tvdb_id = item_meta.get("tvdb_id", "")
            self.episode_absolute = item_meta.get("episode_absolute", "")
            self.path_for_player = item_meta.get("path", "")
        except Exception as e:
            log(f"Error setting additional metadata: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)

        self.set_detailed_item(item_meta) 
        
        self.selected_player_key = selected_player_key
        self.selected_mode = selected_mode
        self.handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1
        self.plugin_url = sys.argv[0] if len(sys.argv) > 0 else ""
        self.action_log = []

    def _get_player_config_by_key(self, player_key):
        return self.players.get(player_key)

    def choose_player(self):
        dialog = xbmcgui.Dialog()
        player_options = self.get_dialog_players()

        if not player_options:
            dialog.notification(get_localized_string(30003), get_localized_string(30004), xbmcgui.NOTIFICATION_INFO)
            return None

        options_list = [p.get("name") for p in player_options]
        selection = dialog.select(get_localized_string(32060), options_list)

        if selection == -1:
            return None  

        chosen_player_config = player_options[selection]
        log(f"User selected player: {chosen_player_config.get('name', 'Unknown')}, mode: {chosen_player_config.get('mode', 'Unknown')}")
        return chosen_player_config

    def play_item(self, chosen_player_config=None):
        if not chosen_player_config:
            always_select = ADDON.getSettingBool("always_select_player")
            
            if always_select:
                chosen_player_config = self.choose_player()
            else:
                default_player_setting_id = ""
                mode_to_use = ""
                if self.tmdb_type == "movie":
                    default_player_setting_id = "default_player_movies"
                    mode_to_use = "play_movie"
                elif self.tmdb_type == "tv": 
                    default_player_setting_id = "default_player_episodes"
                    mode_to_use = "play_episode"
                
                default_player_key = ADDON.getSetting(default_player_setting_id) if default_player_setting_id else None
                
                if default_player_key:
                    default_player_json_data = self._get_player_config_by_key(default_player_key) 
                    if default_player_json_data and default_player_json_data.get(mode_to_use):
                        chosen_player_config = self.get_built_player(default_player_json_data, mode=mode_to_use)
                        log(f"Using default player: {chosen_player_config.get('name', 'Unknown')}")

    def play(self):
        import xbmcplugin
        import xbmcgui
        import xbmc
        import sys
        handle = int(sys.argv[1]) if len(sys.argv) > 1 else -1
        li = xbmcgui.ListItem(self.item_meta.get('ep_title', self.item_meta.get('title', '')))

        # --- Resume support ---
        # Try to get resume time from history (if available)
        try:
            from resources.lib.history import get_watch_history
            anime_id = self.item_meta.get('id')
            episode = self.item_meta.get('episode')
            resume_time = None
            if anime_id and episode:
                history = get_watch_history(limit=100)
                for entry in history:
                    if entry['id'] == anime_id and str(entry['episode']) == str(episode):
                        resume_time = entry.get('resume_time') or 0
                        break
            if resume_time and resume_time > 0:
                li.setProperty('StartOffset', str(resume_time))
        except Exception as e:
            log(f"Resume support error: {e}", xbmc.LOGWARNING)

        # --- External player logic ---
        chosen_player = None
        if hasattr(self, 'choose_player'):
            chosen_player = self.choose_player()
        if chosen_player and chosen_player.get('plugin_id') and chosen_player['plugin_id'] != 'default':
            # Launch external player via plugin URL
            plugin_url = chosen_player.get('command')
            if plugin_url:
                plugin_url = plugin_url.format(**self.item_meta)
                xbmc.executebuiltin(f'RunPlugin({plugin_url})')
                return
        # Fallback to Kodi internal player
        xbmcplugin.setResolvedUrl(handle, True, li)

def play_media_with_player_selection(item_meta):
    # Integrate with Players class for actual playback
    from resources.lib.players import Players
    players = Players(item_meta)
    players.play()
