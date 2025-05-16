try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
except ImportError:
    from resources.lib import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs

import os
import json
import time
import uuid
import base64
import requests
import webbrowser
from urllib.parse import urlencode

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))

# Auth data directory
AUTH_DIR = os.path.join(PROFILE, "auth")
os.makedirs(AUTH_DIR, exist_ok=True)

# Logging function
def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level=level)

def get_auth_file(service):
    """
    Get path to auth file for a service
    """
    return os.path.join(AUTH_DIR, f"{service}_auth.json")

def get_auth_data(service):
    """
    Get authentication data for a service
    """
    auth_file = get_auth_file(service)
    
    if os.path.exists(auth_file):
        try:
            with open(auth_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            log(f"Corrupted auth data for {service}. Resetting auth data.", xbmc.LOGWARNING)
            os.remove(auth_file)
        except Exception as e:
            log(f"Error reading auth data for {service}: {e}", xbmc.LOGWARNING)
    
    return {}

def save_auth_data(service, data):
    """
    Save authentication data for a service
    """
    auth_file = get_auth_file(service)
    
    try:
        with open(auth_file, "w") as f:
            json.dump(data, f)
        
        return True
    except Exception as e:
        log(f"Error saving auth data for {service}: {e}", xbmc.LOGERROR)
        return False

def is_authenticated(service):
    """
    Check if authenticated with a service
    """
    auth_data = get_auth_data(service)
    
    if not auth_data:
        return False
    
    # Check if token exists
    if service == "anilist":
        return bool(auth_data.get("access_token"))
    elif service == "mal":
        return bool(auth_data.get("access_token"))
    elif service == "trakt":
        return bool(auth_data.get("access_token"))
    
    return False

def get_token(service):
    """
    Get access token for a service
    """
    auth_data = get_auth_data(service)
    
    if not auth_data:
        return ""
    
    return auth_data.get("access_token", "")

def get_refresh_token(service):
    """
    Get refresh token for a service
    """
    auth_data = get_auth_data(service)
    
    if not auth_data:
        return ""
    
    return auth_data.get("refresh_token", "")

def is_token_expired(service):
    """
    Check if token is expired
    """
    auth_data = get_auth_data(service)
    
    if not auth_data:
        return True # No auth data means effectively expired for API calls
    
    # AniList tokens are long-lived (1 year) and don't support refresh.
    # Consider it expired if it's older than, say, 11 months to prompt re-auth proactively,
    # or simply rely on API calls failing with 401.
    # For now, let's assume it expires as per its `expires_at` for consistency, 
    # but refresh will fail and lead to re-auth prompt elsewhere.
    expires_at = auth_data.get("expires_at", 0)
    
    # Add a buffer of 5 minutes
    return time.time() > (expires_at - 300)

def refresh_token(service):
    """
    Refresh token for a service
    """
    auth_data = get_auth_data(service)
    
    if not auth_data or not auth_data.get("refresh_token"):
        log(f"No refresh token found for {service} or not authenticated.", xbmc.LOGINFO)
        return False
    
    refresh_token_val = auth_data.get("refresh_token")
    
    if service == "anilist":
        # AniList API v2 does not support refresh tokens as per documentation (https://docs.anilist.co/guide/auth/)
        log("AniList does not support token refresh. User needs to re-authenticate.", xbmc.LOGINFO)
        # To force re-authentication, we can clear the existing token or simply return False.
        # Clearing token here might be too aggressive if called from multiple places.
        # The API call wrapper should handle the 401 and prompt re-auth.
        return False 
    elif service == "mal":
        return refresh_mal_token(refresh_token_val)
    elif service == "trakt":
        return refresh_trakt_token(refresh_token_val)
    
    return False

# AniList refresh token function is effectively disabled above.
# The original refresh_anilist_token function is kept below for reference but should not be called directly.
# def refresh_anilist_token(refresh_token_val):
#     """
#     Refresh AniList token (NOTE: AniList v2 docs state refresh tokens are not supported)
#     """
#     client_id = ADDON.getSetting("anilist_client_id")
#     client_secret = ADDON.getSetting("anilist_client_secret")
    
#     if not client_id or not client_secret or not refresh_token_val:
#         log("AniList client ID, secret, or refresh token missing for refresh.", xbmc.LOGWARNING)
#         return False
    
#     try:
#         resp = requests.post(
#             "https://anilist.co/api/v2/oauth/token",
#             json={
#                 "grant_type": "refresh_token",
#                 "client_id": client_id,
#                 "client_secret": client_secret,
#                 "refresh_token": refresh_token_val
#             },
#             timeout=10
#         )
        
#         resp.raise_for_status()
#         data = resp.json()
        
#         expires_at = time.time() + data.get("expires_in", 31536000) # Default 1 year
        
#         auth_data = {
#             "access_token": data.get("access_token"),
#             "refresh_token": data.get("refresh_token", refresh_token_val), # Persist old if new not provided
#             "expires_at": expires_at
#         }
        
#         save_auth_data("anilist", auth_data)
#         log("Attempted to refresh AniList token (though not officially supported).")
#         return True
    
#     except Exception as e:
#         log(f"Error refreshing AniList token: {e}", xbmc.LOGERROR)
#         # If refresh fails (e.g. 400 Bad Request if refresh_token is invalid or not supported)
#         # it might be good to clear the invalid refresh token to prevent repeated failed attempts.
#         # current_auth = get_auth_data("anilist")
#         # if "refresh_token" in current_auth:
#         #     del current_auth["refresh_token"]
#         #     save_auth_data("anilist", current_auth)
#         return False

def refresh_mal_token(refresh_token_val):
    """
    Refresh MyAnimeList token
    """
    client_id = ADDON.getSetting("mal_client_id")
    client_secret = ADDON.getSetting("mal_client_secret")
    
    if not client_id or not client_secret or not refresh_token_val:
        log("MAL client ID, secret, or refresh token missing for refresh.", xbmc.LOGWARNING)
        return False
    
    try:
        resp = requests.post(
            "https://myanimelist.net/v1/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token_val
            },
            timeout=10
        )
        
        resp.raise_for_status()
        data = resp.json()
        
        expires_at = time.time() + data.get("expires_in", 3600) # Default 1 hour
        
        auth_data = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token", refresh_token_val),
            "expires_at": expires_at
        }
        
        save_auth_data("mal", auth_data)
        log("Refreshed MAL token")
        return True
    
    except Exception as e:
        log(f"Error refreshing MAL token: {e}", xbmc.LOGERROR)
        return False

def refresh_trakt_token(refresh_token_val):
    """
    Refresh Trakt token
    """
    client_id = ADDON.getSetting("trakt_client_id")
    client_secret = ADDON.getSetting("trakt_client_secret")
    
    if not client_id or not client_secret or not refresh_token_val:
        log("Trakt client ID, secret, or refresh token missing for refresh.", xbmc.LOGWARNING)
        return False
    
    try:
        resp = requests.post(
            "https://api.trakt.tv/oauth/token",
            json={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token_val,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"
            },
            headers={
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        resp.raise_for_status()
        data = resp.json()
        
        expires_at = time.time() + data.get("expires_in", 7776000)  # Default to 90 days
        
        auth_data = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token", refresh_token_val),
            "expires_at": expires_at
        }
        
        save_auth_data("trakt", auth_data)
        log("Refreshed Trakt token")
        return True
    
    except Exception as e:
        log(f"Error refreshing Trakt token: {e}", xbmc.LOGERROR)
        return False

def authenticate(service):
    """
    Authenticate with a service
    """
    if service == "anilist":
        return authenticate_anilist()
    elif service == "mal":
        return authenticate_mal()
    elif service == "trakt":
        return authenticate_trakt()
    return (False, f"Unknown service: {service}")

def authenticate_anilist():
    """
    Authenticate with AniList
    """
    client_id = ADDON.getSetting("anilist_client_id")
    if not client_id:
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(30200), # Auth Error Title
            ADDON.getLocalizedString(30201)  # AniList Client ID not set
        )
        return (False, "AniList Client ID not set")

    state = str(uuid.uuid4())
    auth_url = "https://anilist.co/api/v2/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "response_type": "code", # Using PIN flow, so code is exchanged for token
        "redirect_uri": "https://anilist.co/api/v2/oauth/pin", # Standard PIN redirect
        "state": state
    })
    
    xbmcgui.Dialog().ok(
        ADDON.getLocalizedString(30202), # AniList Auth Title
        ADDON.getLocalizedString(30203)  # AniList PIN instructions
    )
    webbrowser.open(auth_url)
    pin = xbmcgui.Dialog().input(ADDON.getLocalizedString(30204)) # Enter AniList PIN
    if not pin:
        return (False, "AniList PIN not entered")

    # AniList uses Client Secret for PIN exchange according to some unofficial guides for server-side PIN flow.
    # The official docs are more focused on redirect flow for client_secret usage.
    # However, if it's a public client (like a Kodi addon often is), client_secret might not be used or required for PIN flow.
    # Let's assume client_secret is needed as per original code, but be mindful if this causes issues.
    client_secret = ADDON.getSetting("anilist_client_secret")
    if not client_secret: # Assuming client_secret is required for this PIN flow
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(30200), # Auth Error Title
            ADDON.getLocalizedString(30205)  # AniList Client Secret not set
        )
        return (False, "AniList Client Secret not set for PIN exchange")

    try:
        resp = requests.post(
            "https://anilist.co/api/v2/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret, # Sending client_secret
                "redirect_uri": "https://anilist.co/api/v2/oauth/pin",
                "code": pin # This is the PIN from the user
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        expires_at = time.time() + data.get("expires_in", 31536000) # AniList tokens are 1 year
        auth_data = {
            "access_token": data.get("access_token"),
            # AniList v2 docs state no refresh_token. If one is sent, store it, but don't rely on it.
            "refresh_token": data.get("refresh_token"), 
            "expires_at": expires_at
        }
        save_auth_data("anilist", auth_data)
        log("Authenticated with AniList")
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30206), ADDON.getLocalizedString(30207)) # Auth Success, AniList Success
        return (True, "Successfully authenticated with AniList")
    except Exception as e:
        log(f"Error authenticating with AniList: {e}. Response: {resp.text if 'resp' in locals() else 'N/A'}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(30200), # Auth Error Title
            f"{ADDON.getLocalizedString(30208)} {str(e)}" # Failed AniList Auth
        )
        return (False, f"Failed to authenticate with AniList: {str(e)}")

def authenticate_mal():
    """
    Authenticate with MyAnimeList using PKCE
    """
    client_id = ADDON.getSetting("mal_client_id")
    if not client_id:
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30200), ADDON.getLocalizedString(30209)) # MAL Client ID not set
        return (False, "MyAnimeList Client ID not set")

    code_verifier = base64.urlsafe_b64encode(os.urandom(43)).decode("utf-8").rstrip("=") # Min 43 chars for PKCE
    # For PKCE S256, code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
    # However, MAL docs state 'plain' is an option. If using 'plain', challenge = verifier.
    # The original code used 'plain' and set challenge = verifier. This is acceptable if MAL supports it.
    code_challenge = code_verifier 
    state = str(uuid.uuid4())

    auth_url = "https://myanimelist.net/v1/oauth2/authorize?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "plain", # Explicitly stating plain
        "state": state,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob" # Using OOB for manual code entry
    })
    
    xbmcgui.Dialog().ok(
        ADDON.getLocalizedString(30210), # MAL Auth Title
        ADDON.getLocalizedString(30211) # MAL Code instructions
    )
    webbrowser.open(auth_url)
    auth_code = xbmcgui.Dialog().input(ADDON.getLocalizedString(30212)) # Enter MAL Auth Code
    if not auth_code:
        return (False, "MyAnimeList authorization code not entered")

    # MAL requires client_secret for public clients if not using PKCE or if PKCE is optional.
    # The original code included client_secret. Let's assume it's needed or accepted.
    client_secret = ADDON.getSetting("mal_client_secret") # Optional for public clients with PKCE, but good to have if API allows

    payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": auth_code,
        "code_verifier": code_verifier,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"
    }
    if client_secret: # Add client_secret if available
        payload["client_secret"] = client_secret

    try:
        resp = requests.post(
            "https://myanimelist.net/v1/oauth2/token",
            data=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        expires_at = time.time() + data.get("expires_in", 3600)
        auth_data = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_at": expires_at
        }
        save_auth_data("mal", auth_data)
        log("Authenticated with MyAnimeList")
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30206), ADDON.getLocalizedString(30213)) # Auth Success, MAL Success
        return (True, "Successfully authenticated with MyAnimeList")
    except Exception as e:
        log(f"Error authenticating with MyAnimeList: {e}. Response: {resp.text if 'resp' in locals() else 'N/A'}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(30200), 
            f"{ADDON.getLocalizedString(30214)} {str(e)}" # Failed MAL Auth
        )
        return (False, f"Failed to authenticate with MyAnimeList: {str(e)}")

def authenticate_trakt():
    """
    Authenticate with Trakt
    """
    client_id = ADDON.getSetting("trakt_client_id")
    if not client_id:
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30200), ADDON.getLocalizedString(30215)) # Trakt Client ID not set
        return (False, "Trakt Client ID not set")

    state = str(uuid.uuid4())
    auth_url = "https://trakt.tv/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "response_type": "code",
        "state": state
    })
    
    xbmcgui.Dialog().ok(
        ADDON.getLocalizedString(30216), # Trakt Auth Title
        ADDON.getLocalizedString(30217)  # Trakt PIN instructions
    )
    webbrowser.open(auth_url)
    pin = xbmcgui.Dialog().input(ADDON.getLocalizedString(30218)) # Enter Trakt PIN
    if not pin:
        return (False, "Trakt PIN not entered")

    client_secret = ADDON.getSetting("trakt_client_secret")
    if not client_secret:
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30200), ADDON.getLocalizedString(30219)) # Trakt Client Secret not set
        return (False, "Trakt Client Secret not set")

    try:
        resp = requests.post(
            "https://api.trakt.tv/oauth/token",
            json={
                "code": pin,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "authorization_code"
            },
            headers={
                "Content-Type": "application/json"
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        expires_at = time.time() + data.get("expires_in", 7776000)  # Default to 90 days
        auth_data = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_at": expires_at
        }
        save_auth_data("trakt", auth_data)
        log("Authenticated with Trakt")
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30206), ADDON.getLocalizedString(30220)) # Auth Success, Trakt Success
        return (True, "Successfully authenticated with Trakt")
    except Exception as e:
        log(f"Error authenticating with Trakt: {e}. Response: {resp.text if 'resp' in locals() else 'N/A'}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(30200), 
            f"{ADDON.getLocalizedString(30221)} {str(e)}" # Failed Trakt Auth
        )
        return (False, f"Failed to authenticate with Trakt: {str(e)}")

def revoke_auth(service):
    """
    Revoke authentication with a service
    """
    # Additionally, attempt to revoke token on the server side if API supports it.
    # For now, just deleting local token.
    auth_data = get_auth_data(service)
    token_to_revoke = auth_data.get("access_token")

    auth_file = get_auth_file(service)
    revoked_locally = False
    if os.path.exists(auth_file):
        try:
            os.remove(auth_file)
            log(f"Revoked local authentication for {service}")
            revoked_locally = True
        except Exception as e:
            log(f"Error revoking local authentication for {service}: {e}", xbmc.LOGERROR)
            # Continue to attempt server-side revocation if applicable
    
    # Server-side revocation (example for Trakt, others might differ or not support)
    if service == "trakt" and token_to_revoke and ADDON.getSetting("trakt_client_id") and ADDON.getSetting("trakt_client_secret"):
        try:
            requests.post(
                "https://api.trakt.tv/oauth/revoke",
                json={
                    "token": token_to_revoke,
                    "client_id": ADDON.getSetting("trakt_client_id"),
                    "client_secret": ADDON.getSetting("trakt_client_secret")
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            ).raise_for_status()
            log(f"Successfully revoked Trakt token on server.")
        except Exception as e:
            log(f"Failed to revoke Trakt token on server: {e}", xbmc.LOGWARNING)
    # Add similar server-side revocation for MAL and AniList if their APIs support it and it's deemed necessary.
    # MAL: POST to https://myanimelist.net/v1/oauth2/revoke with token and client_id/client_secret (check docs)
    # AniList: No explicit revoke endpoint found in quick review of docs; relies on token expiry or user revoking via site.

    return revoked_locally # For now, success is based on local removal.

def test_connection(service):
    """
    Test connection to a service by fetching a small piece of user-specific data.
    Returns (bool: success, str: message)
    """
    if not is_authenticated(service):
        return False, ADDON.getLocalizedString(30222) # Not Authenticated

    from resources.lib.api import AnimeDBAPI # Avoid circular import at top level
    api_client = AnimeDBAPI()

    try:
        if service == "anilist":
            # Fetch viewer's profile as a simple test
            query = "query { Viewer { id name } }"
            response = api_client._anilist_query(query)
            if response and response.get("data", {}).get("Viewer"):
                return True, f"{ADDON.getLocalizedString(30223)} {response['data']['Viewer']['name']}" # Connected as ...
            else:
                error_detail = response.get("errors", [{}])[0].get("message", "Unknown AniList error") if response else "No response"
                return False, f"{ADDON.getLocalizedString(30224)} {error_detail}" # AniList Connection Failed
        
        elif service == "mal":
            # Fetch user's own profile information
            resp = api_client._mal_request(f"{api_client.MAL_API}/users/@me?fields=name")
            if resp and resp.status_code == 200:
                user_data = resp.json()
                return True, f"{ADDON.getLocalizedString(30223)} {user_data.get('name', 'Unknown User')}"
            else:
                error_detail = resp.json().get("message", "Unknown MAL error") if resp and resp.content else "No response or non-JSON error"
                return False, f"{ADDON.getLocalizedString(30225)} {error_detail}" # MAL Connection Failed

        elif service == "trakt":
            # Fetch user settings
            resp = api_client._trakt_request(f"{api_client.TRAKT_API}/users/settings")
            if resp and resp.status_code == 200:
                user_data = resp.json()
                return True, f"{ADDON.getLocalizedString(30223)} {user_data.get('user',{}).get('username', 'Unknown User')}"
            else:
                error_detail = resp.json().get("error_description", "Unknown Trakt error") if resp and resp.content else "No response or non-JSON error"
                return False, f"{ADDON.getLocalizedString(30226)} {error_detail}" # Trakt Connection Failed
        
        else: # Added else for unknown service, correctly indented
            return False, ADDON.getLocalizedString(30227) # Unknown service for test

    except Exception as e:
        log(f"Error testing {service} connection: {e}", xbmc.LOGERROR)
        return False, f"{ADDON.getLocalizedString(30228)} {str(e)}" # Connection Test Error

