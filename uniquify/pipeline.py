from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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


_write_lock = threading.Lock()
_worker_state = threading.local()


@dataclass
class PipelineConfig:
    images_dir: Path
    site_name: str
    text_mode: str
    rewrite_text: bool
    rewrite_images: bool
    force_images: bool
    main_image_only: bool
    fast_images: bool
    image_timeout: float


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with _write_lock:
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


def _init_worker(config: PipelineConfig) -> None:
    _worker_state.config = config
    _worker_state.rewriter = create_rewriter(config.text_mode, site_name=config.site_name) if config.rewrite_text else None
    _worker_state.image_processor = (
        ImageProcessor(config.images_dir, fast_mode=config.fast_images, timeout=config.image_timeout)
        if config.rewrite_images
        else None
    )


def _process_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    config: PipelineConfig = _worker_state.config
    result = dict(recipe)

    if config.rewrite_text and _worker_state.rewriter is not None:
        result = _worker_state.rewriter.rewrite_recipe(result)

    if config.rewrite_images and _worker_state.image_processor is not None:
        result = _worker_state.image_processor.process_recipe_images(
            result,
            force=config.force_images,
            main_only=config.main_image_only,
        )

    result["uniquified"] = True
    return result


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
        fast_images: bool = False,
        image_timeout: float = 20.0,
        workers: int = 1,
        save_every: int = 25,
    ) -> None:
        self.input_path = input_path
        self.output_path = output_path
        self.progress_path = progress_path
        self.workers = max(1, workers)
        self.save_every = max(1, save_every)
        self.config = PipelineConfig(
            images_dir=images_dir,
            site_name=site_name,
            text_mode=text_mode,
            rewrite_text=rewrite_text,
            rewrite_images=rewrite_images,
            force_images=force_images,
            main_image_only=main_image_only,
            fast_images=fast_images,
            image_timeout=image_timeout,
        )

    def _save_progress(self, processed_total: int, success_count: int, error_count: int) -> None:
        save_json(
            self.progress_path,
            {
                "processed_total": processed_total,
                "last_success_count": success_count,
                "last_error_count": error_count,
                "text_mode": self.config.text_mode,
                "rewrite_text": self.config.rewrite_text,
                "rewrite_images": self.config.rewrite_images,
                "workers": self.workers,
                "fast_images": self.config.fast_images,
            },
        )

    def run(self, limit: Optional[int] = None) -> dict[str, Any]:
        processed_ids = load_processed_ids(self.output_path)
        pending = [recipe for recipe in iter_recipes(self.input_path) if recipe["id"] not in processed_ids]
        if limit is not None:
            pending = pending[:limit]

        success_count = 0
        error_count = 0
        processed_total = len(processed_ids)

        if self.workers == 1:
            _init_worker(self.config)
            iterator = tqdm(pending, desc="Уникализация")
            for index, recipe in enumerate(iterator, start=1):
                try:
                    result = _process_recipe(recipe)
                    append_jsonl(self.output_path, result)
                    success_count += 1
                    processed_total += 1
                except Exception as error:
                    append_jsonl(
                        self.output_path,
                        {"id": recipe.get("id"), "error": str(error), "title": recipe.get("title", "")},
                    )
                    error_count += 1
                    processed_total += 1
                if index % self.save_every == 0:
                    self._save_progress(processed_total, success_count, error_count)
        else:
            mode_parts = []
            if self.config.rewrite_text:
                mode_parts.append(f"текст={self.config.text_mode}")
            if self.config.rewrite_images:
                mode_parts.append("фото" + (" fast" if self.config.fast_images else ""))
            print(f"Параллельно: {self.workers} потоков ({', '.join(mode_parts) or 'обработка'})")

            with ThreadPoolExecutor(
                max_workers=self.workers,
                initializer=_init_worker,
                initargs=(self.config,),
            ) as executor:
                futures = {executor.submit(_process_recipe, recipe): recipe for recipe in pending}
                for index, future in enumerate(tqdm(as_completed(futures), total=len(pending), desc="Уникализация"), start=1):
                    recipe = futures[future]
                    try:
                        result = future.result()
                        append_jsonl(self.output_path, result)
                        success_count += 1
                    except Exception as error:
                        append_jsonl(
                            self.output_path,
                            {"id": recipe.get("id"), "error": str(error), "title": recipe.get("title", "")},
                        )
                        error_count += 1
                    processed_total = len(processed_ids) + index
                    if index % self.save_every == 0:
                        self._save_progress(processed_total, success_count, error_count)

        self._save_progress(len(load_processed_ids(self.output_path)), success_count, error_count)

        return {
            "processed_total": len(load_processed_ids(self.output_path)),
            "last_success_count": success_count,
            "last_error_count": error_count,
            "output": str(self.output_path),
            "images_dir": str(self.config.images_dir),
            "workers": self.workers,
        }
