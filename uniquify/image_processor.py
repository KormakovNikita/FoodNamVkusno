from __future__ import annotations

import hashlib
import io
import random
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:
    Image = None  # type: ignore

try:
    from curl_cffi import requests as http
    USE_CURL = True
except ImportError:
    import requests as http
    USE_CURL = False


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class ImageProcessor:
    def __init__(self, output_dir: Path, quality_range: tuple[int, int] = (84, 91)) -> None:
        if Image is None:
            raise RuntimeError("Установите Pillow: pip install Pillow")
        self.output_dir = output_dir
        self.quality_range = quality_range
        self.session = http.Session(impersonate="chrome") if USE_CURL else http.Session()
        if not USE_CURL:
            self.session.headers.update({"User-Agent": USER_AGENT})

    def _seed(self, recipe_id: int, url: str, kind: str) -> random.Random:
        key = f"{recipe_id}:{kind}:{url}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    def download(self, url: str, timeout: float = 30.0) -> Optional[bytes]:
        if not url or not url.startswith("http"):
            return None
        try:
            response = self.session.get(url, timeout=timeout, headers={"Referer": "https://www.povarenok.ru/"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                return None
            return response.content
        except Exception:
            return None

    def transform(self, image_bytes: bytes, recipe_id: int, url: str, kind: str) -> bytes:
        rng = self._seed(recipe_id, url, kind)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        width, height = image.size
        crop_pct = rng.uniform(0.015, 0.045)
        left = int(width * rng.uniform(0, crop_pct))
        top = int(height * rng.uniform(0, crop_pct))
        right = width - int(width * rng.uniform(0, crop_pct))
        bottom = height - int(height * rng.uniform(0, crop_pct))
        if right - left > 80 and bottom - top > 80:
            image = image.crop((left, top, right, bottom))

        angle = rng.uniform(-1.8, 1.8)
        if abs(angle) > 0.2:
            image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))

        scale = rng.uniform(0.96, 0.99)
        new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
        image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)

        image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.94, 1.06))
        image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.94, 1.06))
        image = ImageEnhance.Color(image).enhance(rng.uniform(0.93, 1.07))
        image = ImageEnhance.Sharpness(image).enhance(rng.uniform(0.92, 1.08))

        if rng.random() > 0.5:
            image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.5)))

        output = io.BytesIO()
        quality = rng.randint(*self.quality_range)
        image.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
        return output.getvalue()

    def _local_path(self, recipe_id: int, kind: str, url: str) -> Path:
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        filename = f"{kind}_{hashlib.md5(url.encode()).hexdigest()[:10]}.jpg"
        return self.output_dir / str(recipe_id) / filename

    def process_url(self, recipe_id: int, url: str, kind: str, force: bool = False) -> Optional[str]:
        if not url:
            return None
        local_path = self._local_path(recipe_id, kind, url)
        if local_path.exists() and not force:
            return str(local_path.as_posix())

        raw = self.download(url)
        if not raw:
            return None

        transformed = self.transform(raw, recipe_id, url, kind)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(transformed)
        return str(local_path.as_posix())

    def process_recipe_images(self, recipe: dict, force: bool = False, main_only: bool = False) -> dict:
        recipe_id = recipe["id"]
        updated = dict(recipe)

        if recipe.get("image_url"):
            local = self.process_url(recipe_id, recipe["image_url"], "main", force=force)
            if local:
                updated["image_url_original"] = recipe["image_url"]
                updated["image_url"] = local

        if main_only:
            return updated

        steps = []
        for step in recipe.get("steps", []):
            step_copy = dict(step)
            if step.get("image_url"):
                local = self.process_url(recipe_id, step["image_url"], f"step_{step.get('number', 0)}", force=force)
                if local:
                    step_copy["image_url_original"] = step["image_url"]
                    step_copy["image_url"] = local
            steps.append(step_copy)
        updated["steps"] = steps
        return updated
