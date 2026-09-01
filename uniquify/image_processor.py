from __future__ import annotations

import hashlib
import io
import random
from pathlib import Path
from typing import Optional

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
    def __init__(
        self,
        output_dir: Path,
        quality_range: tuple[int, int] = (84, 91),
        fast_mode: bool = False,
        timeout: float = 20.0,
        strip_watermark: bool = True,
        watermark_backend: str = "crop",
        media_url_prefix: str = "media/recipes",
    ) -> None:
        if Image is None:
            raise RuntimeError("Установите Pillow: pip install Pillow")
        self.output_dir = output_dir
        self.quality_range = quality_range
        self.fast_mode = fast_mode
        self.timeout = timeout
        self.strip_watermark = strip_watermark
        self.watermark_backend = watermark_backend
        self.media_url_prefix = media_url_prefix.rstrip("/")
        self._watermark_remover = None
        if strip_watermark and watermark_backend != "crop":
            from uniquify.ai_watermark import create_watermark_remover

            self._watermark_remover = create_watermark_remover(watermark_backend)
        self.session = http.Session(impersonate="chrome") if USE_CURL else http.Session()
        if not USE_CURL:
            self.session.headers.update({"User-Agent": USER_AGENT})

    @staticmethod
    def is_remote_url(url: str) -> bool:
        return bool(url) and url.startswith(("http://", "https://", "//"))

    def _strip_watermark(self, image: Image.Image) -> Image.Image:
        """Убирает логотип povarenok.ru в правом нижнем углу."""
        width, height = image.size
        # Логотип: ~20% ширины справа, ~16% высоты снизу
        crop_right = int(width * 0.20)
        crop_bottom = int(height * 0.16)
        cropped = image.crop((0, 0, width - crop_right, height - crop_bottom))
        return cropped.resize((width, height), Image.Resampling.LANCZOS)

    def _seed(self, recipe_id: int, url: str, kind: str) -> random.Random:
        key = f"{recipe_id}:{kind}:{url}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    def download(self, url: str, timeout: float | None = None) -> Optional[bytes]:
        if not url or not url.startswith("http"):
            return None
        try:
            response = self.session.get(
                url,
                timeout=timeout or self.timeout,
                headers={"Referer": "https://www.povarenok.ru/"},
            )
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

        if self.strip_watermark:
            if self._watermark_remover is not None:
                image = self._watermark_remover.remove(image)
            else:
                image = self._strip_watermark(image)

        width, height = image.size
        resample = Image.Resampling.BILINEAR if self.fast_mode else Image.Resampling.LANCZOS

        crop_pct = rng.uniform(0.01, 0.03 if self.fast_mode else 0.045)
        left = int(width * rng.uniform(0, crop_pct))
        top = int(height * rng.uniform(0, crop_pct))
        right = width - int(width * rng.uniform(0, crop_pct))
        bottom = height - int(height * rng.uniform(0, crop_pct))
        if right - left > 80 and bottom - top > 80:
            image = image.crop((left, top, right, bottom))

        if not self.fast_mode:
            angle = rng.uniform(-1.8, 1.8)
            if abs(angle) > 0.2:
                image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))

        scale = rng.uniform(0.97, 0.99 if self.fast_mode else 0.99)
        new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(new_size, resample)
        image = ImageOps.fit(image, (width, height), method=resample)

        image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.96, 1.04))
        image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.96, 1.04))
        if not self.fast_mode:
            image = ImageEnhance.Color(image).enhance(rng.uniform(0.93, 1.07))
            image = ImageEnhance.Sharpness(image).enhance(rng.uniform(0.92, 1.08))
            if rng.random() > 0.5:
                image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.5)))

        output = io.BytesIO()
        quality = rng.randint(*self.quality_range)
        save_kwargs = {"format": "JPEG", "quality": quality}
        if not self.fast_mode:
            save_kwargs["optimize"] = True
            save_kwargs["progressive"] = True
        image.save(output, **save_kwargs)
        return output.getvalue()

    def _local_path(self, recipe_id: int, kind: str) -> Path:
        filename = "main.jpg" if kind == "main" else f"{kind}.jpg"
        return self.output_dir / str(recipe_id) / filename

    def _public_url(self, recipe_id: int, kind: str) -> str:
        filename = "main.jpg" if kind == "main" else f"{kind}.jpg"
        return f"/{self.media_url_prefix}/{recipe_id}/{filename}"

    def process_url(self, recipe_id: int, url: str, kind: str, force: bool = False) -> Optional[str]:
        if not url:
            return None
        if not self.is_remote_url(url):
            local_path = Path(url.lstrip("/"))
            if local_path.exists():
                return url
            disk_path = self._local_path(recipe_id, kind)
            if disk_path.exists():
                return self._public_url(recipe_id, kind)
            return None

        local_path = self._local_path(recipe_id, kind)
        if local_path.exists() and not force:
            return self._public_url(recipe_id, kind)

        raw = self.download(url)
        if not raw:
            return None

        transformed = self.transform(raw, recipe_id, url, kind)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(transformed)
        return self._public_url(recipe_id, kind)

    def process_recipe_images(self, recipe: dict, force: bool = False, main_only: bool = False) -> dict:
        recipe_id = recipe["id"]
        updated = dict(recipe)

        if recipe.get("image_url"):
            source_url = recipe.get("image_url_original") or recipe["image_url"]
            if self.is_remote_url(recipe["image_url"]) or force:
                local = self.process_url(recipe_id, source_url if self.is_remote_url(source_url) else recipe["image_url"], "main", force=force)
                if local:
                    if self.is_remote_url(recipe["image_url"]):
                        updated["image_url_original"] = recipe["image_url"]
                    updated["image_url"] = local

        if main_only:
            return updated

        steps = []
        for step in recipe.get("steps", []):
            step_copy = dict(step)
            if step.get("image_url"):
                source_url = step.get("image_url_original") or step["image_url"]
                if self.is_remote_url(step["image_url"]) or force:
                    local = self.process_url(
                        recipe_id,
                        source_url if self.is_remote_url(source_url) else step["image_url"],
                        f"step_{step.get('number', 0)}",
                        force=force,
                    )
                    if local:
                        if self.is_remote_url(step["image_url"]):
                            step_copy["image_url_original"] = step["image_url"]
                        step_copy["image_url"] = local
            steps.append(step_copy)
        updated["steps"] = steps
        return updated
