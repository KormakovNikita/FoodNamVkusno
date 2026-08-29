from __future__ import annotations

import json
from pathlib import Path


def show_status(data_dir: Path = Path("data")) -> dict:
    stats = {
        "categories": 0,
        "recipe_ids": 0,
        "previews": 0,
        "recipes_ok": 0,
        "recipes_failed": 0,
        "failed_categories": 0,
    }

    categories_path = data_dir / "categories.json"
    ids_path = data_dir / "recipe_ids.json"
    previews_path = data_dir / "recipe_previews.json"
    recipes_path = data_dir / "recipes.jsonl"
    failed_recipes_path = data_dir / "failed_recipes.jsonl"
    failed_categories_path = data_dir / "failed_categories.json"

    if categories_path.exists():
        stats["categories"] = len(json.load(categories_path.open(encoding="utf-8")))
    if ids_path.exists():
        stats["recipe_ids"] = len(json.load(ids_path.open(encoding="utf-8")))
    if previews_path.exists():
        stats["previews"] = len(json.load(previews_path.open(encoding="utf-8")))
    if recipes_path.exists():
        stats["recipes_ok"] = sum(
            1
            for line in recipes_path.open(encoding="utf-8")
            if line.strip() and "error" not in json.loads(line)
        )
    if failed_recipes_path.exists():
        stats["recipes_failed"] = sum(1 for line in failed_recipes_path.open(encoding="utf-8") if line.strip())
    elif recipes_path.exists():
        stats["recipes_failed"] = sum(
            1
            for line in recipes_path.open(encoding="utf-8")
            if line.strip() and "error" in json.loads(line)
        )
    if failed_categories_path.exists():
        stats["failed_categories"] = len(json.load(failed_categories_path.open(encoding="utf-8")))

    remaining = max(0, stats["recipe_ids"] - stats["recipes_ok"])
    print("=== Статус парсинга ===")
    print(f"Категорий:           {stats['categories']}")
    print(f"ID рецептов:         {stats['recipe_ids']}")
    print(f"Превью:              {stats['previews']}")
    print(f"Скачано рецептов:    {stats['recipes_ok']}")
    print(f"Ошибок (403 и др.):  {stats['recipes_failed']}")
    print(f"Категорий с ошибкой: {stats['failed_categories']}")
    print(f"Осталось скачать:    {remaining}")
    return stats
