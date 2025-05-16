import requests

class TMDBAPI:
    BASE_URL = 'https://api.themoviedb.org/3'
    IMAGE_BASE = 'https://image.tmdb.org/t/p/original'

    def __init__(self, api_key):
        self.api_key = api_key

    def search_tv(self, query):
        """Search for TV shows by name (returns list of results)"""
        import xbmc
        url = f'{self.BASE_URL}/search/tv'
        params = {'api_key': self.api_key, 'query': query}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            xbmc.log(f"TMDB search_tv error: {resp.status_code} {resp.text}", xbmc.LOGERROR)
        resp.raise_for_status()
        return resp.json().get('results', [])

    def get_tv_details(self, tmdb_id):
        """Get TV show details by TMDB ID"""
        import xbmc
        url = f'{self.BASE_URL}/tv/{tmdb_id}'
        params = {'api_key': self.api_key}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            xbmc.log(f"TMDB get_tv_details error: {resp.status_code} {resp.text}", xbmc.LOGERROR)
        resp.raise_for_status()
        return resp.json()

    def get_episodes(self, tmdb_id, season_number):
        """Get all episodes for a given season"""
        import xbmc
        url = f'{self.BASE_URL}/tv/{tmdb_id}/season/{season_number}'
        params = {'api_key': self.api_key}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            xbmc.log(f"TMDB get_episodes error: {resp.status_code} {resp.text}", xbmc.LOGERROR)
        resp.raise_for_status()
        return resp.json().get('episodes', [])

    def get_episode_image(self, still_path):
        if still_path:
            return f'{self.IMAGE_BASE}{still_path}'
        return ''
