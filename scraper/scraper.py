from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from scraper.client import RussianFoodClient
from scraper.parser import (
    append_jsonl,
    load_json,
    load_scraped_ids,
    parse_recipe,
    save_json,
)


def _scrape_one(client: RussianFoodClient, recipe_id: int) -> dict | None:
    url = f"https://www.russianfood.com/recipes/recipe.php?rid={recipe_id}"
    try:
        try:
            html = client.get_print_page(recipe_id)
            recipe = parse_recipe(html, recipe_id, source="print")
            if recipe and recipe.ingredients:
                return recipe.to_dict()
        except Exception:
            pass

        html = client.get_recipe_page(recipe_id)
        recipe = parse_recipe(html, recipe_id, source="page")
        if recipe:
            return recipe.to_dict()
        return {"id": recipe_id, "error": "empty recipe page", "url": url}
    except Exception as error:
        return {"id": recipe_id, "error": str(error), "url": url}


def scrape_recipes(
    client: RussianFoodClient,
    ids_path: Path,
    output_path: Path,
    progress_path: Path,
    workers: int = 6,
    limit: int | None = None,
) -> dict:
    recipe_ids = load_json(ids_path, [])
    scraped_ids = load_scraped_ids(output_path)
    pending = [recipe_id for recipe_id in recipe_ids if recipe_id not in scraped_ids]
    if limit is not None:
        pending = pending[:limit]

    success_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scrape_one, client, recipe_id): recipe_id for recipe_id in pending}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Рецепты"):
            recipe_id = futures[future]
            result = future.result()
            if result is None:
                error_count += 1
                continue
            if "error" in result:
                append_jsonl(output_path, result)
                error_count += 1
                continue
            append_jsonl(output_path, result)
            success_count += 1

    progress = {
        "total_ids": len(recipe_ids),
        "scraped_ids": len(load_scraped_ids(output_path)),
        "last_success_count": success_count,
        "last_error_count": error_count,
    }
    save_json(progress_path, progress)
    return progress
