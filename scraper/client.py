from __future__ import annotations

import random
import threading
import time
from typing import Optional

try:
    from curl_cffi import requests as http
    USE_CURL_CFFI = True
except ImportError:
    import requests as http
    USE_CURL_CFFI = False

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.russianfood.com"
ENCODING = "windows-1251"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class RussianFoodClient:
    def __init__(
        self,
        delay: float = 5.0,
        timeout: float = 30.0,
        max_retries: int = 3,
        cooldown_after: int = 5,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.cooldown_after = cooldown_after
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_blocks = 0

        if USE_CURL_CFFI:
            self.session = http.Session(impersonate="chrome")
        else:
            self.session = http.Session()
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

    @property
    def backend(self) -> str:
        return "curl_cffi" if USE_CURL_CFFI else "requests"

    def warmup(self) -> None:
        if self._warmed_up:
            return
        for _ in range(3):
            try:
                self.get("/recipes/")
                self._warmed_up = True
                return
            except Exception:
                time.sleep(10)

    @staticmethod
    def _looks_blocked(html: str) -> bool:
        if len(html) < 100_000 and "recipe_new" not in html and "ingr_block" not in html:
            return True
        return False

    def _register_block(self) -> None:
        self.consecutive_blocks += 1
        if self.consecutive_blocks >= self.cooldown_after:
            print(
                f"\n[!] {self.consecutive_blocks} блокировок подряд. "
                f"Пауза {int(self.cooldown_seconds // 60)} мин...\n"
            )
            time.sleep(self.cooldown_seconds)
            self.consecutive_blocks = 0
            self._warmed_up = False
            self.warmup()

    def _register_success(self) -> None:
        self.consecutive_blocks = 0

    def _throttle(self) -> None:
        jitter = random.uniform(0.5, 2.0)
        wait_for = self.delay + jitter
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < wait_for:
                time.sleep(wait_for - elapsed)
            self._last_request_at = time.monotonic()

    def get(
        self,
        path: str,
        params: Optional[dict] = None,
        referer: Optional[str] = None,
        retries: Optional[int] = None,
    ) -> str:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        headers = {"Referer": referer or f"{BASE_URL}/recipes/"}
        max_retries = self.max_retries if retries is None else retries

        last_response = None
        for attempt in range(max_retries):
            self._throttle()
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            last_response = response
            if response.status_code in (403, 429):
                self._register_block()
                time.sleep(min(120, 15 * (attempt + 1)))
                continue
            response.raise_for_status()
            response.encoding = ENCODING
            html = response.text
            if self._looks_blocked(html):
                self._register_block()
                time.sleep(min(120, 15 * (attempt + 1)))
                continue
            self._register_success()
            return html

        if last_response is not None:
            last_response.raise_for_status()
        raise http.HTTPError(f"Failed to fetch {url}")

    def get_recipe_page(self, recipe_id: int) -> str:
        return self.get(
            "/recipes/recipe.php",
            params={"rid": recipe_id},
            referer=f"{BASE_URL}/recipes/",
        )

    def get_category_page(self, fid: int, page: int = 1) -> str:
        params = {"fid": fid}
        if page > 1:
            params["page"] = page
        referer = f"{BASE_URL}/recipes/bytype/?fid={fid}"
        if page > 1:
            referer += f"&page={page - 1}"
        return self.get("/recipes/bytype/", params=params, referer=referer)
