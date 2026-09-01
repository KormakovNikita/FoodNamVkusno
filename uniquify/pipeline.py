from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from tqdm import tqdm

from uniquify.image_processor import ImageProcessor
from uniquify.text_rewriter import create_rewriter


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_processed_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    processed: set[int] = set()
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                continue
            processed.add(record["id"])
    return processed


def iter_recipes(input_path: Path) -> Iterable[dict[str, Any]]:
    if input_path.suffix == ".jsonl":
        with input_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("error"):
                    continue
                yield record
        return

    records = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(records, list):
        for record in records:
            if not record.get("error"):
                yield record


class UniquifyPipeline:
    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        images_dir: Path,
        progress_path: Path,
        site_name: str = "FoodNamVkusno",
        text_mode: str = "offline",
        rewrite_text: bool = True,
        rewrite_images: bool = True,
        force_images: bool = False,
        main_image_only: bool = False,
    ) -> None:
        self.input_path = input_path
        self.output_path = output_path
        self.images_dir = images_dir
        self.progress_path = progress_path
        self.site_name = site_name
        self.text_mode = text_mode
        self.rewrite_text = rewrite_text
        self.rewrite_images = rewrite_images
        self.force_images = force_images
        self.main_image_only = main_image_only
        self.rewriter = create_rewriter(text_mode, site_name=site_name)
        self.image_processor = ImageProcessor(images_dir) if rewrite_images else None

    def process_one(self, recipe: dict[str, Any]) -> dict[str, Any]:
        result = dict(recipe)
        if self.rewrite_text:
            result = self.rewriter.rewrite_recipe(result)
        if self.rewrite_images and self.image_processor is not None:
            result = self.image_processor.process_recipe_images(
                result,
                force=self.force_images,
                main_only=self.main_image_only,
            )
        result["uniquified"] = True
        return result

    def run(self, limit: Optional[int] = None) -> dict[str, Any]:
        processed_ids = load_processed_ids(self.output_path)
        pending = [recipe for recipe in iter_recipes(self.input_path) if recipe["id"] not in processed_ids]
        if limit is not None:
            pending = pending[:limit]

        success_count = 0
        error_count = 0

        for recipe in tqdm(pending, desc="Уникализация"):
            try:
                result = self.process_one(recipe)
                append_jsonl(self.output_path, result)
                success_count += 1
            except Exception as error:
                append_jsonl(
                    self.output_path,
                    {"id": recipe.get("id"), "error": str(error), "title": recipe.get("title", "")},
                )
                error_count += 1
            save_json(
                self.progress_path,
                {
                    "processed_total": len(load_processed_ids(self.output_path)),
                    "last_success_count": success_count,
                    "last_error_count": error_count,
                    "text_mode": self.text_mode,
                    "rewrite_text": self.rewrite_text,
                    "rewrite_images": self.rewrite_images,
                },
            )

        return {
            "processed_total": len(load_processed_ids(self.output_path)),
            "last_success_count": success_count,
            "last_error_count": error_count,
            "output": str(self.output_path),
            "images_dir": str(self.images_dir),
        }
