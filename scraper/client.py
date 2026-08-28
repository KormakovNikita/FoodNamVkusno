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
    def __init__(self, delay: float = 2.0, timeout: float = 30.0, max_retries: int = 4) -> None:
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        retry = Retry(
            total=2,
            backoff_factor=1.0,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._last_request_at = 0.0
        self._lock = threading.Lock()
        self._warmed_up = False

    def warmup(self) -> None:
        if self._warmed_up:
            return
        self.get("/recipes/")
        self._warmed_up = True

    @staticmethod
    def _looks_blocked(html: str) -> bool:
        if len(html) < 100_000 and "recipe_new" not in html and "ingr_block" not in html:
            return True
        return False

    def _throttle(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self._last_request_at = time.monotonic()

    def get(self, path: str, params: Optional[dict] = None, referer: Optional[str] = None, retries: Optional[int] = None) -> str:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        headers = {"Referer": referer} if referer else None
        max_retries = self.max_retries if retries is None else retries

        last_response: Optional[requests.Response] = None
        for attempt in range(max_retries):
            self._throttle()
            response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            last_response = response
            if response.status_code in (403, 429):
                time.sleep(min(30, 3 * (attempt + 1)))
                continue
            response.raise_for_status()
            response.encoding = ENCODING
            html = response.text
            if self._looks_blocked(html):
                time.sleep(min(30, 3 * (attempt + 1)))
                continue
            return html

        if last_response is not None:
            last_response.raise_for_status()
        raise requests.HTTPError(f"Failed to fetch {url}")

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
            retries=2,
        )

    def get_category_page(self, fid: int, page: int = 1) -> str:
        params = {"fid": fid}
        if page > 1:
            params["page"] = page
        referer = f"{BASE_URL}/recipes/bytype/?fid={fid}"
        if page > 1:
            referer += f"&page={page - 1}"
        return self.get("/recipes/bytype/", params=params, referer=referer)
