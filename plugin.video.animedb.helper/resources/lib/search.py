"""
search.py: Search functionality for AnimeDB Helper

This module provides the UI and logic for searching anime across multiple sources.
"""
import xbmc
import xbmcgui
import xbmcplugin
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode

from resources.lib.api import AnimeDBAPI
from resources.lib.ui import add_directory_item, ADDON, ADDON_ID

# Get API instance
API = AnimeDBAPI()

def show_search_menu(handle: int) -> None:
    """Show the search menu with options for new search, history, and filters."""
    # Add search option
    add_directory_item(
        handle,
        ADDON.getLocalizedString(32001),  # New Search
        {'action': 'search_input'},
        'search.png'
    )
    
    # Add search history
    history = get_search_history()
    if history:
        add_directory_item(
            handle,
            ADDON.getLocalizedString(32002),  # Search History
            {'action': 'search_history'},
            'history.png'
        )
    
    # Add advanced search
    add_directory_item(
        handle,
        ADDON.getLocalizedString(32003),  # Advanced Search
        {'action': 'search_advanced'},
        'settings.png'
    )
    
    xbmcplugin.endOfDirectory(handle)

def show_search_input(handle: int) -> None:
    """Show the search input dialog and process the search."""
    keyboard = xbmc.Keyboard('', ADDON.getLocalizedString(32004))  # Enter search query
    keyboard.doModal()
    
    if not keyboard.isConfirmed() or not keyboard.getText():
        xbmcplugin.endOfDirectory(handle)
        return
    
    query = keyboard.getText().strip()
    if not query:
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Save to search history
    save_to_search_history(query)
    
    # Perform search
    perform_search(handle, query)

def show_search_history(handle: int) -> None:
    """Show the search history with options to select or delete items."""
    history = get_search_history()
    if not history:
        xbmcgui.Dialog().notification(
            ADDON.getLocalizedString(32005),  # No History
            ADDON.getLocalizedString(32006),  # No search history found
            xbmcgui.NOTIFICATION_INFO
        )
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Add clear history option
    add_directory_item(
        handle,
        f'[COLOR red]{ADDON.getLocalizedString(32007)}[/COLOR]',  # Clear History
        {'action': 'clear_search_history'},
        'clear.png'
    )
    
    # Add history items
    for i, query in enumerate(history):
        add_directory_item(
            handle,
            query,
            {'action': 'search', 'query': query},
            'search_history.png',
            context_menu=[
                (ADDON.getLocalizedString(32008), f'RunPlugin(plugin://{ADDON_ID}/?action=delete_search_history&index={i}')]  # Remove
            )
    
    xbmcplugin.endOfDirectory(handle)

def show_advanced_search(handle: int) -> None:
    """Show the advanced search dialog with filters."""
    # This would show a dialog with multiple fields for advanced search
    # For now, we'll just show the regular search
    show_search_input(handle)

def perform_search(handle: int, query: str, filters: Optional[Dict[str, Any]] = None, page: int = 1) -> None:
    """Perform a search and display the results."""
    if not query:
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Show busy dialog
    dialog = xbmcgui.DialogProgressBG()
    dialog.create(ADDON.getLocalizedString(32009), f'{ADDON.getLocalizedString(32010)}: {query}')  # Searching for
    
    try:
        # Get filters
        media_type = filters.get('media_type') if filters else None
        status = filters.get('status') if filters else None
        year = int(filters.get('year')) if filters and filters.get('year') else None
        genres = filters.get('genres', []) if filters else []
        sort = filters.get('sort') if filters else 'SEARCH_MATCH'
        
        # Perform search
        results = API.search_anime(
            query=query,
            page=page,
            per_page=20,
            media_type=media_type,
            status=status,
            year=year,
            genres=genres,
            sort=sort
        )
        
        # Update progress
        dialog.update(50, message=ADDON.getLocalizedString(32011))  # Processing results
        
        # Display results
        if not results:
            xbmcgui.Dialog().notification(
                ADDON.getLocalizedString(32012),  # No Results
                ADDON.getLocalizedString(32013),  # No results found for
                xbmcgui.NOTIFICATION_INFO
            )
            xbmcplugin.endOfDirectory(handle)
            return
        
        # Add results to directory
        from resources.lib.ui import list_anime
        list_anime(handle, results, title=f'Search: {query}')
        
    except Exception as e:
        xbmcgui.Dialog().notification(
            ADDON.getLocalizedString(32014),  # Search Error
            str(e),
            xbmcgui.NOTIFICATION_ERROR
        )
        xbmcplugin.endOfDirectory(handle)
    finally:
        dialog.close()

def get_search_history() -> List[str]:
    """Get the search history from settings."""
    import json
    history_json = ADDON.getSetting('search_history')
    if not history_json:
        return []
    try:
        return json.loads(history_json)
    except (ValueError, TypeError):
        return []

def save_to_search_history(query: str) -> None:
    """Save a search query to the history."""
    import json
    history = get_search_history()
    
    # Remove if already exists
    if query in history:
        history.remove(query)
    
    # Add to beginning
    history.insert(0, query)
    
    # Limit history size
    history = history[:20]
    
    # Save
    ADDON.setSetting('search_history', json.dumps(history))

def delete_search_history(index: int = None) -> None:
    """Delete a search history item or clear all history."""
    history = get_search_history()
    
    if index is not None and 0 <= index < len(history):
        # Delete specific item
        del history[index]
        ADDON.setSetting('search_history', json.dumps(history))
    elif xbmcgui.Dialog().yesno(
        ADDON.getLocalizedString(32015),  # Confirm
        ADDON.getLocalizedString(32016)   # Clear all search history?
    ):
        # Clear all history
        ADDON.setSetting('search_history', '[]')
    
    # Refresh
    xbmc.executebuiltin('Container.Refresh')

def clear_search_history() -> None:
    """Clear all search history."""
    delete_search_history()
