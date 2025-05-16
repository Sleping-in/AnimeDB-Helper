"""Centralized authentication utilities to break cyclic imports."""

def refresh_token(service, token=None):
    """
    Centralized token refresh mechanism.
    
    Args:
        service (str): The service to refresh token for
        token (dict, optional): Existing token data
    
    Returns:
        dict: Refreshed token data
    """
    from resources.lib import auth  # Local import to avoid circular dependency
    
    if service == 'anilist':
        return auth.refresh_anilist_token(token)
    if service == 'mal':
        return auth.refresh_mal_token(token)
    if service == 'trakt':
        return auth.refresh_trakt_token(token)
    
    raise ValueError(f"Unsupported service: {service}")
