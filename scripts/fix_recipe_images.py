#!/usr/bin/env python3
"""Перекачать и обработать фото: AI-удаление водяного знака povarenok."""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tqdm import tqdm

from uniquify.image_processor import ImageProcessor

_worker_state = threading.local()


def load_recipes(path: Path) -> list[dict]:
    recipes = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                continue
            recipes.append(record)
    return recipes


def needs_image_fix(recipe: dict) -> bool:
    if ImageProcessor.is_remote_url(recipe.get("image_url", "")):
        return True
    for step in recipe.get("steps", []):
        if ImageProcessor.is_remote_url(step.get("image_url", "")):
            return True
    return False


def _init_worker(images_dir: Path, fast_images: bool, watermark_backend: str) -> None:
    _worker_state.processor = ImageProcessor(
        images_dir,
        fast_mode=fast_images,
        strip_watermark=True,
        watermark_backend=watermark_backend,
    )


def _process_one(recipe: dict, main_only: bool) -> dict:
    processor: ImageProcessor = _worker_state.processor
    return processor.process_recipe_images(dict(recipe), force=True, main_only=main_only)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-обработка фото: убрать водяной знак povarenok")
    parser.add_argument("--input", type=Path, default=Path("data/recipes_unique.jsonl"))
    parser.add_argument("--output", type=Path, default=None, help="По умолчанию перезаписывает input")
    parser.add_argument("--images-dir", type=Path, default=Path("data/images"))
    parser.add_argument("--workers", type=int, default=None, help="Для AI (lama) лучше 1–2, для opencv — 8–12")
    parser.add_argument("--fast-images", action="store_true")
    parser.add_argument("--main-image-only", action="store_true", help="Только главное фото")
    parser.add_argument("--force", action="store_true", help="Перегенерировать даже локальные фото")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--ai-backend",
        choices=["ai", "lama", "opencv", "replicate", "crop"],
        default="ai",
        help="ai = LaMa локально (или opencv fallback), replicate = облако Replicate",
    )
    args = parser.parse_args()

    if args.workers is None:
        args.workers = 1 if args.ai_backend in {"ai", "lama", "replicate"} else 8

    if not args.input.exists():
        raise SystemExit(f"Файл не найден: {args.input}")

    output_path = args.output or args.input
    recipes = load_recipes(args.input)
    if args.limit:
        recipes = recipes[: args.limit]

    fix_ids = {r["id"] for r in recipes if args.force or needs_image_fix(r)}
    print(f"Всего рецептов: {len(recipes)}, обработать фото: {len(fix_ids)}")
    print(f"AI backend: {args.ai_backend}, workers: {args.workers}")

    if not fix_ids:
        print("Все фото уже локальные. Используйте --force для перегенерации.")
        if not args.force:
            return

    if args.force:
        fix_ids = {r["id"] for r in recipes}
        if args.limit:
            fix_ids = {r["id"] for r in recipes[: args.limit]}

    updated_by_id: dict[int, dict] = {}
    errors = 0

    pending = [r for r in recipes if r["id"] in fix_ids]
    with ThreadPoolExecutor(
        max_workers=args.workers,
        initializer=_init_worker,
        initargs=(args.images_dir, args.fast_images, args.ai_backend),
    ) as executor:
        futures = {executor.submit(_process_one, recipe, args.main_image_only): recipe["id"] for recipe in pending}
        for future in tqdm(as_completed(futures), total=len(pending), desc="AI фото"):
            recipe_id = futures[future]
            try:
                updated_by_id[recipe_id] = future.result()
            except Exception as error:
                errors += 1
                tqdm.write(f"[!] ID {recipe_id}: {error}")

    temp_path = output_path.with_suffix(".tmp.jsonl")
    with temp_path.open("w", encoding="utf-8") as file:
        for recipe in recipes:
            record = updated_by_id.get(recipe["id"], recipe)
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    temp_path.replace(output_path)
    fixed = sum(1 for r in updated_by_id.values() if not ImageProcessor.is_remote_url(r.get("image_url", "")))
    print(
        {
            "updated": len(updated_by_id),
            "local_images": fixed,
            "errors": errors,
            "output": str(output_path),
            "images_dir": str(args.images_dir),
            "ai_backend": args.ai_backend,
        }
    )


if __name__ == "__main__":
    main()
