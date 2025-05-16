import xbmcaddon

try:
    import xbmc
except ImportError:
    from . import xbmc
import traceback

def log(message, level=None):
    try:
        xbmc.log(str(message), level=level or getattr(xbmc, 'LOGDEBUG', None))
    except Exception:
        print(f"LOG: {message}")

class AddonSettings:
    def __init__(self):
        self._addon = xbmcaddon.Addon()
    
    def get_setting(self, setting_key, default=None):
        """Retrieve a setting value with comprehensive error handling"""
        try:
            # Retrieve raw setting value
            value = self._addon.getSetting(setting_key)
            
            # Handle empty string
            if not value:
                return default
            
            # Handle boolean settings
            if value.lower() in ['true', 'false']:
                return value.lower() == 'true'
            
            # Handle numeric settings
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    pass
            
            return value
        except Exception as e:
            log(f"Error retrieving setting '{setting_key}': {e}\n{traceback.format_exc()}", xbmc.LOGERROR)
            return default
    
    def set_setting(self, setting_key, value):
        """Set a setting value with error handling"""
        try:
            # Normalize boolean values
            if isinstance(value, bool):
                value = str(value).lower()
            
            # Convert to string and set
            self._addon.setSetting(setting_key, str(value))
            log(f"Setting '{setting_key}' set to '{value}'", xbmc.LOGDEBUG)
        except Exception as e:
            log(f"Error setting '{setting_key}' to '{value}': {e}\n{traceback.format_exc()}", xbmc.LOGERROR)
    
    # Comprehensive settings properties with sensible defaults
    @property
    def items_per_page(self):
        return self.get_setting('items_per_page', 20)
    
    @property
    def auto_mark_watched(self):
        return self.get_setting('auto_mark_watched', False)
    
    @property
    def always_show_player_selection(self):
        return self.get_setting('always_show_player_selection', False)
    
    @property
    def debug_mode(self):
        return self.get_setting('debug_mode', False)
    
    @property
    def default_player(self):
        return self.get_setting('default_player', '')

# Global settings instance
addon_settings = AddonSettings()

def get_setting(key, default=None):
    """Convenience function for getting settings"""
    return addon_settings.get_setting(key, default)

def set_setting(key, value):
    """Convenience function for setting settings"""
    addon_settings.set_setting(key, value)

# This module is unused in the main codebase and can be removed as per audit recommendations.
