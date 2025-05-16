import json
import xbmcgui
import xbmc
import xbmcaddon
import xbmcvfs
from urllib.parse import urlencode
import requests

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

# Players directory
PLAYERS_DIR = xbmcvfs.translatePath(PROFILE.rstrip('/') + '/players')
if not xbmcvfs.exists(PLAYERS_DIR):
    xbmcvfs.mkdirs(PLAYERS_DIR)

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def get_players():
    """Get all available players"""
    players = []
    
    if not xbmcvfs.exists(PLAYERS_DIR):
        return players
        
    _, files = xbmcvfs.listdir(PLAYERS_DIR)
    for file in files:
        if file.endswith('.json'):
            try:
                filepath = PLAYERS_DIR.rstrip('/') + '/' + file
                with xbmcvfs.File(filepath, 'r') as f:
                    player = json.loads(f.read().decode('utf-8'))
                    players.append(player)
            except Exception as e:
                log(f"Error loading player {file}: {e}", xbmc.LOGERROR)
    
    return players

def save_player(player):
    """Save player configuration"""
    try:
        filename = f"{player['name'].lower().replace(' ', '_')}.json"
        filepath = PLAYERS_DIR.rstrip('/') + '/' + filename
        
        with xbmcvfs.File(filepath, 'w') as f:
            f.write(json.dumps(player, indent=4).encode('utf-8'))
            
        return True
    except Exception as e:
        log(f"Error saving player: {e}", xbmc.LOGERROR)
        return False

def delete_player(player_name):
    """Delete a player configuration"""
    try:
        filename = f"{player_name.lower().replace(' ', '_')}.json"
        filepath = PLAYERS_DIR.rstrip('/') + '/' + filename
        
        if xbmcvfs.exists(filepath):
            xbmcvfs.delete(filepath)
            return True
    except Exception as e:
        log(f"Error deleting player: {e}", xbmc.LOGERROR)
    
    return False

def edit_player_dialog(player=None):
    """Show dialog to edit player configuration"""
    if player is None:
        player = {
            'name': '',
            'plugin_id': '',
            'command': 'plugin://{plugin_id}/?action=play&id={id}&episode={episode}',
            'fallback_command': '',
            'is_resolvable': True
        }
    
    # Show name dialog
    name = xbmcgui.Dialog().input('Player Name', defaultt=player.get('name', ''))
    if not name:
        return None
    
    # Show plugin ID dialog
    plugin_id = xbmcgui.Dialog().input('Plugin ID', defaultt=player.get('plugin_id', ''))
    
    # Show command dialog
    command = xbmcgui.Dialog().input('Command Template', defaultt=player.get('command', ''))
    
    # Show fallback command dialog
    fallback = xbmcgui.Dialog().input('Fallback Command (optional)', defaultt=player.get('fallback_command', ''))
    
    # Toggle resolvable
    is_resolvable = xbmcgui.Dialog().yesno('Is Resolvable', 'Can this player resolve to a playable URL?')
    
    return {
        'name': name,
        'plugin_id': plugin_id,
        'command': command,
        'fallback_command': fallback,
        'is_resolvable': is_resolvable
    }

# Alias for backward compatibility with imports in default.py
edit_player = edit_player_dialog

def import_player():
    """Import player configuration from file"""
    try:
        # Show file browser
        filepath = xbmcgui.Dialog().browse(1, 'Select Player Configuration', 'files', '.json')
        if not filepath or not isinstance(filepath, str) or not filepath.strip():
            return False
            
        with xbmcvfs.File(filepath, 'r') as f:
            player = json.loads(f.read().decode('utf-8'))
            
        # Save to players directory
        return save_player(player)
    except Exception as e:
        log(f"Error importing player: {e}", xbmc.LOGERROR)
        return False

def export_player(player_name):
    """Export player configuration to file"""
    try:
        players = get_players()
        player = next((p for p in players if p.get('name') == player_name), None)
        
        if not player:
            return False
            
        # Show save dialog
        save_path = xbmcgui.Dialog().browse(3, 'Save Player Configuration', 'files', '.json')
        if not save_path:
            return False
            
        # Ensure .json extension
        if not save_path.endswith('.json'):
            save_path += '.json'
            
        with xbmcvfs.File(save_path, 'w') as f:
            f.write(json.dumps(player, indent=4).encode('utf-8'))
            
        return True
    except Exception as e:
        log(f"Error exporting player: {e}", xbmc.LOGERROR)
        return False

def export_players():
    """Export all players to a single file"""
    try:
        players = get_players()
        if not players:
            xbmcgui.Dialog().notification('No Players', 'No players to export', xbmcgui.NOTIFICATION_WARNING)
            return False
            
        # Show save dialog
        save_path = xbmcgui.Dialog().browse(3, 'Export Players', 'files', '.json')
        if not save_path:
            return False
            
        # Ensure .json extension
        if not save_path.endswith('.json'):
            save_path += '.json'
            
        with xbmcvfs.File(save_path, 'w') as f:
            f.write(json.dumps(players, f, indent=4).encode('utf-8'))
            
        return True
    except Exception as e:
        log(f"Error exporting players: {e}", xbmc.LOGERROR)
        return False

# Legacy player management functions removed. File retained for compatibility only.
    """Show player management dialog"""
    while True:
        players = get_players()
        player_names = [p['name'] for p in players]
        default_player = get_default_player()
        
        # Add action items
        player_names.extend(['Add New Player', 'Import Player', 'Set Default Player', 'Back'])
        
        # Show selection dialog
        selected = xbmcgui.Dialog().select('Manage Players', player_names)
        
        if selected < 0:
            break
            
        selected_item = player_names[selected]
        
        # Handle Set Default Player
        if selected_item == 'Set Default Player':
            if not players:
                xbmcgui.Dialog().ok('No Players', 'No players available to set as default.')
                continue
                
            # Create list with current default marked
            player_list = []
            for i, player in enumerate(players):
                prefix = '[DEFAULT] ' if player['name'] == default_player else ''
                player_list.append(f"{prefix}{player['name']}")
                
            # Show selection dialog
            idx = xbmcgui.Dialog().select('Set Default Player', player_list)
            if idx >= 0:
                set_default_player(players[idx]['name'])
                xbmcgui.Dialog().notification(
                    'Default Player Set',
                    f"{players[idx]['name']} is now the default player",
                    xbmcgui.NOTIFICATION_INFO
                )
            continue
        
        if selected_item == 'Add New Player':
            player = edit_player_dialog()
            if player:
                save_player(player)
                xbmcgui.Dialog().notification('Success', 'Player added successfully', xbmcgui.NOTIFICATION_INFO)
                
        elif selected_item == 'Import Player':
            if import_player():
                xbmcgui.Dialog().notification('Success', 'Player imported successfully', xbmcgui.NOTIFICATION_INFO)
            else:
                xbmcgui.Dialog().notification('Error', 'Failed to import player', xbmcgui.NOTIFICATION_ERROR)
                
        elif selected_item == 'Back':
            break
            
        else:
            # Player selected, show options
            player_name = player_names[selected]
            player = next((p for p in players if p['name'] == player_name), None)
            
            if not player:
                continue
                
            # Show player options
            options = ['Edit', 'Export', 'Delete', 'Back']
            option = xbmcgui.Dialog().select(f'Player: {player_name}', options)
            
            if option == 0:  # Edit
                updated_player = edit_player_dialog(player)
                if updated_player:
                    # Delete old player file
                    delete_player(player_name)
                    # Save updated player
                    save_player(updated_player)
                    xbmcgui.Dialog().notification('Success', 'Player updated successfully', xbmcgui.NOTIFICATION_INFO)
                    
            elif option == 1:  # Export
                if export_player(player_name):
                    xbmcgui.Dialog().notification('Success', 'Player exported successfully', xbmcgui.NOTIFICATION_INFO)
                else:
                    xbmcgui.Dialog().notification('Error', 'Failed to export player', xbmcgui.NOTIFICATION_ERROR)
                    
            elif option == 2:  # Delete
                if xbmcgui.Dialog().yesno('Confirm Delete', f'Delete player: {player_name}?'):
                    if delete_player(player_name):
                        xbmcgui.Dialog().notification('Success', 'Player deleted', xbmcgui.NOTIFICATION_INFO)
                    else:
                        xbmcgui.Dialog().notification('Error', 'Failed to delete player', xbmcgui.NOTIFICATION_ERROR)

def get_default_player():
    """Get the default player from settings"""
    addon = xbmcaddon.Addon()
    return addon.getSettingString('default_player')

def set_default_player(player_name):
    """Set the default player in settings"""
    addon = xbmcaddon.Addon()
    addon.setSettingString('default_player', player_name)
    return True

def reset_players():
    """Reset players to default configuration"""
    try:
        # Get all current players
        players = get_players()
        
        # Confirm with user
        if not xbmcgui.Dialog().yesno('Reset Players', 'This will delete all custom players and restore defaults. Continue?'):
            return False
            
        # Delete all player files
        for player in players:
            delete_player(player.get('name'))
        
        # Create default players
        default_players = [
            {
                'name': 'Default Player',
                'plugin_id': 'plugin.video.example',
                'command': 'plugin://{plugin_id}/?action=play&id={id}&episode={episode}',
                'fallback_command': '',
                'is_resolvable': True
            }
        ]
        
        # Save default players
        for player in default_players:
            save_player(player)
        
        # Set default player
        if default_players:
            set_default_player(default_players[0]['name'])
            
        return True
    except Exception as e:
        log(f"Error resetting players: {e}", xbmc.LOGERROR)
        return False

def manage_players_dialog():
    # Placeholder for a real player management dialog
    import xbmcgui
    xbmcgui.Dialog().ok("Manage Players", "Player management UI is not yet implemented.")

# Define a stub for update_players if missing
if 'update_players' not in globals():
    def update_players(url):
        import xbmcgui
        import xbmcvfs
        import json
        try:
            if not url:
                xbmcgui.Dialog().notification('Players', 'No URL provided for update.', xbmcgui.NOTIFICATION_ERROR)
                return False
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            players_data = response.json()
            if not isinstance(players_data, list):
                xbmcgui.Dialog().notification('Players', 'Invalid player data format.', xbmcgui.NOTIFICATION_ERROR)
                return False
            # Save each player config
            for player in players_data:
                filename = f"{player['name'].lower().replace(' ', '_')}.json"
                filepath = PLAYERS_DIR.rstrip('/') + '/' + filename
                with xbmcvfs.File(filepath, 'w') as f:
                    f.write(json.dumps(player, indent=4).encode('utf-8'))
            xbmcgui.Dialog().notification('Players', 'Players updated successfully.', xbmcgui.NOTIFICATION_INFO)
            return True
        except Exception as e:
            xbmcgui.Dialog().notification('Players', f'Update failed: {e}', xbmcgui.NOTIFICATION_ERROR)
            return False
