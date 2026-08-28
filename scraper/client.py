from __future__ import annotations

import threading
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.russianfood.com"
ENCODING = "windows-1251"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class RussianFoodClient:
    def __init__(self, delay: float = 1.0, timeout: float = 30.0, max_retries: int = 8) -> None:
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._last_request_at = 0.0
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self._last_request_at = time.monotonic()

    def get(self, path: str, params: Optional[dict] = None, referer: Optional[str] = None) -> str:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        headers = {"Referer": referer or f"{BASE_URL}/recipes/"}

        for attempt in range(self.max_retries):
            self._throttle()
            response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            if response.status_code == 403:
                wait = min(60, 2 ** attempt)
                time.sleep(wait)
                continue
            if response.status_code == 429:
                time.sleep(min(120, 5 * (attempt + 1)))
                continue
            response.raise_for_status()
            response.encoding = ENCODING
            return response.text

        response.raise_for_status()
        response.encoding = ENCODING
        return response.text

    def get_recipe_page(self, recipe_id: int) -> str:
        return self.get(
            "/recipes/recipe.php",
            params={"rid": recipe_id},
            referer=f"{BASE_URL}/recipes/",
        )

    def get_print_page(self, recipe_id: int) -> str:
        return self.get(
            "/recipes/recipe_prn.php",
            params={"rid": recipe_id},
            referer=f"{BASE_URL}/recipes/recipe.php?rid={recipe_id}",
        )

    def get_category_page(self, fid: int, page: int = 1) -> str:
        params = {"fid": fid}
        if page > 1:
            params["page"] = page
        referer = f"{BASE_URL}/recipes/bytype/?fid={fid}"
        if page > 1:
            referer += f"&page={page - 1}"
        return self.get("/recipes/bytype/", params=params, referer=referer)
