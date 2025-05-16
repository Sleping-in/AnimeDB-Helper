import os
import sqlite3
import time
import xbmcaddon
import xbmcvfs
import xbmc

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

# Setup database path
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
DB_PATH = os.path.join(PROFILE, 'history.db')

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def get_conn():
    """
    Get a connection to the history database
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    # Create tables if they don't exist
    conn.execute('''
    CREATE TABLE IF NOT EXISTS history (
        anime_id TEXT,
        episode INTEGER,
        last_watch_time INTEGER,
        source TEXT,
        PRIMARY KEY(anime_id, episode, source)
    )
    ''')
    
    return conn

def record_watch(anime_id, episode, source='anilist'):
    """
    Record a watch event
    """
    if not ADDON.getSettingBool('history_enabled'):
        return False
    
    try:
        conn = get_conn()
        with conn:
            conn.execute(
                '''
                INSERT OR REPLACE INTO history (anime_id, episode, last_watch_time, source)
                VALUES (?, ?, ?, ?)
                ''',
                (anime_id, episode, int(time.time()), source)
            )
        conn.close()
        
        log(f"Recorded watch: {anime_id} episode {episode} from {source}")
        return True
    
    except Exception as e:
        log(f"Error recording watch: {e}", xbmc.LOGERROR)
        return False

def get_continue_watching(limit=25):
    """
    Get list of anime to continue watching
    """
    if not ADDON.getSettingBool('history_enabled'):
        return []
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT anime_id, MAX(episode) as ep, MAX(last_watch_time) as t, source
            FROM history
            GROUP BY anime_id, source
            ORDER BY t DESC
            LIMIT ?
            ''',
            (limit,)
        )
        results = cur.fetchall()
        conn.close()
        
        return [
            {
                'id': r[0],
                'episode': r[1],
                'last_watch_time': r[2],
                'source': r[3]
            } for r in results
        ]
    
    except Exception as e:
        log(f"Error getting continue watching: {e}", xbmc.LOGERROR)
        return []

def get_next_episode(limit=25):
    """
    Get list of next episodes to watch
    """
    if not ADDON.getSettingBool('history_enabled'):
        return []
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT anime_id, MAX(episode)+1 as next_ep, MAX(last_watch_time) as t, source
            FROM history
            GROUP BY anime_id, source
            ORDER BY t DESC
            LIMIT ?
            ''',
            (limit,)
        )
        results = cur.fetchall()
        conn.close()
        
        return [
            {
                'id': r[0],
                'episode': r[1],
                'last_watch_time': r[2],
                'source': r[3]
            } for r in results
        ]
    
    except Exception as e:
        log(f"Error getting next episodes: {e}", xbmc.LOGERROR)
        return []

def get_watch_history(limit=100):
    """
    Get watch history
    """
    if not ADDON.getSettingBool('history_enabled'):
        return []
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT anime_id, episode, last_watch_time, source
            FROM history
            ORDER BY last_watch_time DESC
            LIMIT ?
            ''',
            (limit,)
        )
        results = cur.fetchall()
        conn.close()
        
        return [
            {
                'id': r[0],
                'episode': r[1],
                'last_watch_time': r[2],
                'source': r[3]
            } for r in results
        ]
    
    except Exception as e:
        log(f"Error getting watch history: {e}", xbmc.LOGERROR)
        return []

def clear_history():
    """
    Clear watch history
    """
    try:
        conn = get_conn()
        with conn:
            conn.execute('DELETE FROM history')
        conn.close()
        
        log("Watch history cleared")
        return True
    
    except Exception as e:
        log(f"Error clearing history: {e}", xbmc.LOGERROR)
        return False

def prune_history(max_entries=None):
    """
    Prune watch history to the specified number of entries
    """
    if max_entries is None:
        max_entries = int(ADDON.getSetting('history_limit'))
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Get total count
        cur.execute('SELECT COUNT(*) FROM history')
        count = cur.fetchone()[0]
        
        if count > max_entries:
            # Get cutoff time
            cur.execute(
                '''
                SELECT last_watch_time
                FROM history
                ORDER BY last_watch_time DESC
                LIMIT 1 OFFSET ?
                ''',
                (max_entries,)
            )
            cutoff = cur.fetchone()[0]
            
            # Delete old entries
            with conn:
                conn.execute(
                    'DELETE FROM history WHERE last_watch_time < ?',
                    (cutoff,)
                )
            
            log(f"Pruned watch history to {max_entries} entries")
        
        conn.close()
        return True
    
    except Exception as e:
        log(f"Error pruning history: {e}", xbmc.LOGERROR)
        return False