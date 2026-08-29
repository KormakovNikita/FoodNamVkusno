from __future__ import annotations

import json
from pathlib import Path

from tqdm import tqdm

from scraper.client import PovarenokClient
from scraper.parser import (
    append_jsonl,
    load_json,
    load_scraped_ids,
    parse_recipe,
    save_json,
)


def _scrape_one(client: PovarenokClient, recipe_id: int) -> dict:
    url = f"https://www.povarenok.ru/recipes/show/{recipe_id}/"
    try:
        html = client.get_recipe_page(recipe_id)
        recipe = parse_recipe(html, recipe_id)
        if recipe:
            return recipe.to_dict()
        return {"id": recipe_id, "error": "empty recipe page", "url": url}
    except Exception as error:
        return {"id": recipe_id, "error": str(error), "url": url}


def scrape_recipes(
    client: PovarenokClient,
    ids_path: Path,
    output_path: Path,
    failed_path: Path,
    progress_path: Path,
    limit: int | None = None,
) -> dict:
    recipe_ids = load_json(ids_path, [])
    scraped_ids = load_scraped_ids(output_path)
    pending = [recipe_id for recipe_id in recipe_ids if recipe_id not in scraped_ids]
    if limit is not None:
        pending = pending[:limit]

    success_count = 0
    error_count = 0

    for recipe_id in tqdm(pending, desc="Рецепты"):
        result = _scrape_one(client, recipe_id)
        if "error" in result:
            append_jsonl(failed_path, result)
            error_count += 1
            continue
        append_jsonl(output_path, result)
        success_count += 1

    progress = {
        "source": "povarenok.ru",
        "total_ids": len(recipe_ids),
        "scraped_ok": len(load_scraped_ids(output_path)),
        "failed": _count_jsonl(failed_path),
        "last_success_count": success_count,
        "last_error_count": error_count,
        "backend": client.backend,
    }
    save_json(progress_path, progress)
    return progress


def retry_failed_recipes(
    client: PovarenokClient,
    failed_path: Path,
    output_path: Path,
    progress_path: Path,
    limit: int | None = None,
) -> dict:
    if not failed_path.exists():
        return {"retried": 0, "still_failed": 0, "success_count": 0}

    failed_records = []
    with failed_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                failed_records.append(json.loads(line))

    if limit is not None:
        failed_records = failed_records[:limit]

    still_failed: list[dict] = []
    success_count = 0

    for record in tqdm(failed_records, desc="Повтор рецептов"):
        result = _scrape_one(client, record["id"])
        if "error" in result:
            still_failed.append(result)
            continue
        append_jsonl(output_path, result)
        success_count += 1

    with failed_path.open("w", encoding="utf-8") as file:
        for record in still_failed:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    save_json(
        progress_path,
        {
            "scraped_ok": len(load_scraped_ids(output_path)),
            "failed": len(still_failed),
            "last_success_count": success_count,
            "backend": client.backend,
        },
    )
    return {
        "retried": len(failed_records),
        "still_failed": len(still_failed),
        "success_count": success_count,
    }


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
