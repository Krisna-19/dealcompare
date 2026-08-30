import random

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from app.core.config import get_settings


def get_headers():
    settings = get_settings()
    return {
        "User-Agent": settings.http_user_agent or settings.user_agent,
        "Accept-Language": settings.http_accept_language,
    }


def get_session():
    session = requests.Session()

    settings = get_settings()
    retry = Retry(
        total=settings.http_max_retries,
        backoff_factor=settings.http_backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def fetch_url(url: str, timeout=None):
    settings = get_settings()
    if timeout is None:
        timeout = settings.http_timeout_seconds

    session = get_session()
    proxy = random.choice(settings.http_proxies_list)

    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        response = session.get(
            url,
            headers=get_headers(),
            proxies=proxies,
            timeout=timeout
        )
        if response.status_code == 200:
            return response.text
    except requests.exceptions.RequestException:
        return None

    return None
