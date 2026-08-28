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
    "Mozilla/5.0 (compatible; RussianFoodRecipeScraper/1.0; +https://github.com/)"
)


class RussianFoodClient:
    def __init__(self, delay: float = 0.35, timeout: float = 30.0) -> None:
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        )
        retry = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
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

    def get(self, path: str, params: Optional[dict] = None) -> str:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        self._throttle()
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = ENCODING
        return response.text

    def get_recipe_page(self, recipe_id: int) -> str:
        return self.get("/recipes/recipe.php", params={"rid": recipe_id})

    def get_print_page(self, recipe_id: int) -> str:
        return self.get("/recipes/recipe_prn.php", params={"rid": recipe_id})

    def get_category_page(self, fid: int, page: int = 1) -> str:
        params = {"fid": fid}
        if page > 1:
            params["page"] = page
        return self.get("/recipes/bytype/", params=params)
