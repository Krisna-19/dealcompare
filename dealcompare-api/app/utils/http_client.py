import random
import time
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# 🔁 FREE PROXIES (ROTATE)
PROXIES = [
    None,  # direct request first
    # You can add free proxies here later
    # "http://123.45.67.89:8080",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-IN,en;q=0.9",
}

def get_session():
    session = requests.Session()

    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

def fetch_url(url: str, timeout=8):
    session = get_session()
    proxy = random.choice(PROXIES)

    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        response = session.get(
            url,
            headers=HEADERS,
            proxies=proxies,
            timeout=timeout
        )
        if response.status_code == 200:
            return response.text
    except requests.exceptions.RequestException:
        return None

    return None
