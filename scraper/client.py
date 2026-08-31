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

BASE_URL = "https://www.povarenok.ru"
ENCODING = "windows-1251"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class PovarenokClient:
    def __init__(
        self,
        delay: float = 1.5,
        timeout: float = 90.0,
        max_retries: int = 6,
        cooldown_after: int = 8,
        cooldown_seconds: float = 120.0,
    ) -> None:
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.cooldown_after = cooldown_after
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_errors = 0

        if USE_CURL_CFFI:
            self.session = http.Session(impersonate="chrome")
        else:
            self.session = http.Session()
            self.session.headers.update({"User-Agent": USER_AGENT})

        self._last_request_at = 0.0
        self._lock = threading.Lock()
        self._warmed_up = False

    @property
    def backend(self) -> str:
        return "curl_cffi" if USE_CURL_CFFI else "requests"

    def warmup(self) -> None:
        if self._warmed_up:
            return
        for attempt in range(3):
            try:
                self.get("/recipes/", count_errors=False)
                self._warmed_up = True
                return
            except Exception as error:
                print(f"[!] Прогрев не удался ({attempt + 1}/3): {error}")
                time.sleep(15 * (attempt + 1))
        print("[!] Прогрев не удался — сайт может временно ограничивать запросы. Подождите 30–60 мин.")

    def _reset_session(self) -> None:
        if USE_CURL_CFFI:
            self.session = http.Session(impersonate="chrome")
        else:
            self.session = http.Session()
            self.session.headers.update({"User-Agent": USER_AGENT})
        self._warmed_up = False

    def _register_error(self, reason: str = "") -> None:
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.cooldown_after:
            detail = f" ({reason})" if reason else ""
            print(f"\n[!] Много ошибок подряд{detail}. Пауза {int(self.cooldown_seconds)} сек...\n")
            time.sleep(self.cooldown_seconds)
            self.consecutive_errors = 0
            self._reset_session()
            self.warmup()

    def _register_success(self) -> None:
        self.consecutive_errors = 0

    def _throttle(self) -> None:
        wait_for = self.delay + random.uniform(0.3, 1.0)
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < wait_for:
                time.sleep(wait_for - elapsed)
            self._last_request_at = time.monotonic()

    @staticmethod
    def _is_timeout_error(error: Exception) -> bool:
        message = str(error).lower()
        return "timed out" in message or "timeout" in message or "curl: (28)" in message

    def get(self, path: str, params: Optional[dict] = None, referer: Optional[str] = None, *, count_errors: bool = True) -> str:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        headers = {"Referer": referer or f"{BASE_URL}/recipes/"}
        last_error: Exception | None = None
        last_status: int | None = None

        for attempt in range(self.max_retries):
            try:
                self._throttle()
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code in (403, 429):
                    last_status = response.status_code
                    time.sleep(min(90, 15 * (attempt + 1)))
                    continue
                response.raise_for_status()
                response.encoding = ENCODING
                self._register_success()
                return response.text
            except Exception as error:
                last_error = error
                wait = min(90, 10 * (attempt + 1))
                if self._is_timeout_error(error):
                    wait = min(120, 20 * (attempt + 1))
                time.sleep(wait)

        if count_errors:
            if last_status in (403, 429):
                self._register_error(f"HTTP {last_status}")
            elif last_error is not None:
                self._register_error(type(last_error).__name__)
            else:
                self._register_error("unknown")

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to fetch {url}")

    def get_recipe_page(self, recipe_id: int) -> str:
        return self.get(f"/recipes/show/{recipe_id}/", referer=f"{BASE_URL}/recipes/")

    def check_recipe_exists(self, recipe_id: int) -> bool:
        url = f"{BASE_URL}/recipes/show/{recipe_id}/"
        headers = {"Referer": f"{BASE_URL}/recipes/"}
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                self._throttle()
                response = self.session.get(url, headers=headers, timeout=self.timeout)
                if response.status_code == 404:
                    self._register_success()
                    return False
                if response.status_code in (403, 429):
                    time.sleep(min(90, 15 * (attempt + 1)))
                    continue
                response.raise_for_status()
                response.encoding = ENCODING
                self._register_success()
                return "schema.org/Recipe" in response.text
            except Exception as error:
                last_error = error
                wait = min(90, 10 * (attempt + 1))
                if self._is_timeout_error(error):
                    wait = min(120, 20 * (attempt + 1))
                time.sleep(wait)

        if last_error is not None:
            self._register_error(type(last_error).__name__)
            raise last_error
        self._register_error("HTTP error")
        raise RuntimeError(f"Failed to check recipe {recipe_id}")

    def get_category_page(self, category_id: int, page: int = 1) -> str:
        if page <= 1:
            path = f"/recipes/category/{category_id}/"
            referer = f"{BASE_URL}/recipes/cat/"
        else:
            # Страницы 2+ отдаются через AJAX (обычные URL возвращают дубликаты).
            path = f"/recipes/category/{category_id}/~{page}/?mode=load"
            referer = f"{BASE_URL}/recipes/category/{category_id}/"
        return self.get(path, referer=referer)

    def get_catalog_page(self) -> str:
        return self.get("/recipes/cat/", referer=f"{BASE_URL}/recipes/")

    def get_fresh_page(self, page: int = 1) -> str:
        if page <= 1:
            return self.get("/recipes/", referer=BASE_URL)
        # Страницы 2+ отдаются через AJAX (обычные URL возвращают дубликаты).
        return self.get(f"/recipes/~{page}/?mode=load", referer=f"{BASE_URL}/recipes/")
