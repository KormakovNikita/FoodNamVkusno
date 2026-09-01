from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter


def create_watermark_mask(size: tuple[int, int]) -> Image.Image:
    """Маска зоны логотипа povarenok (правый нижний угол)."""
    width, height = size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        [
            int(width * 0.60),
            int(height * 0.68),
            width + 4,
            height + 4,
        ],
        fill=255,
    )
    return mask.filter(ImageFilter.GaussianBlur(radius=5))


class WatermarkRemover(ABC):
    @abstractmethod
    def remove(self, image: Image.Image) -> Image.Image:
        raise NotImplementedError


class CropWatermarkRemover(WatermarkRemover):
    def remove(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        crop_right = int(width * 0.20)
        crop_bottom = int(height * 0.16)
        cropped = image.crop((0, 0, width - crop_right, height - crop_bottom))
        return cropped.resize((width, height), Image.Resampling.LANCZOS)


class OpenCVWatermarkRemover(WatermarkRemover):
    def remove(self, image: Image.Image) -> Image.Image:
        import cv2
        import numpy as np

        mask = create_watermark_mask(image.size)
        source = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        mask_array = np.array(mask)
        result = cv2.inpaint(source, mask_array, 10, cv2.INPAINT_NS)
        return Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))


class LamaWatermarkRemover(WatermarkRemover):
    """Локальная нейросеть LaMa (pip install torch simple-lama-inpainting)."""

    def __init__(self) -> None:
        try:
            from simple_lama_inpainting import SimpleLama
        except ImportError as error:
            raise RuntimeError(
                "Установите AI-зависимости: pip install torch simple-lama-inpainting"
            ) from error
        self._model = SimpleLama()

    def remove(self, image: Image.Image) -> Image.Image:
        mask = create_watermark_mask(image.size)
        return self._model(image.convert("RGB"), mask)


class ReplicateWatermarkRemover(WatermarkRemover):
    """Облачный LaMa через Replicate API (REPLICATE_API_TOKEN)."""

    def __init__(self, model: str | None = None) -> None:
        self.api_token = os.environ.get("REPLICATE_API_TOKEN", "")
        if not self.api_token:
            raise RuntimeError("Нужен REPLICATE_API_TOKEN для облачного AI")
        self.model = model or os.environ.get(
            "REPLICATE_LAMA_MODEL",
            "allenhooo/lama:8b3ca232e2159fcd070ade907ce8917892f80ed8c5d3a381d437c5d5b2fbfbdd",
        )

    @staticmethod
    def _image_to_data_uri(image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _request(self, payload: dict) -> dict:
        request = urllib.request.Request(
            "https://api.replicate.com/v1/predictions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))

    def remove(self, image: Image.Image) -> Image.Image:
        mask = create_watermark_mask(image.size)
        payload = {
            "version": self.model.split(":")[-1] if ":" in self.model else self.model,
            "input": {
                "image": self._image_to_data_uri(image.convert("RGB")),
                "mask": self._image_to_data_uri(mask),
            },
        }
        if "/" in self.model and ":" in self.model:
            owner, name_version = self.model.split("/", 1)
            name, version = name_version.split(":", 1)
            payload = {"version": version, "input": payload["input"]}

        result = self._request(payload)
        output = result.get("output")
        if not output:
            raise RuntimeError(f"Replicate error: {result.get('error', result)}")

        image_url = output[0] if isinstance(output, list) else output
        with urllib.request.urlopen(image_url, timeout=60) as response:
            return Image.open(io.BytesIO(response.read())).convert("RGB")


def create_watermark_remover(backend: str) -> WatermarkRemover:
    backend = backend.lower()
    if backend == "crop":
        return CropWatermarkRemover()
    if backend == "opencv":
        return OpenCVWatermarkRemover()
    if backend == "lama":
        return LamaWatermarkRemover()
    if backend == "replicate":
        return ReplicateWatermarkRemover()
    if backend == "ai":
        try:
            return LamaWatermarkRemover()
        except RuntimeError:
            return OpenCVWatermarkRemover()
    raise ValueError(f"Unknown watermark backend: {backend}")
