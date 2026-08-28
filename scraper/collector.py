from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from scraper.client import RussianFoodClient
from scraper.parser import (
    load_json,
    parse_category_links,
    parse_category_preview,
    parse_category_recipe_ids,
    parse_max_page,
    save_json,
)


def _collect_ids_for_category(client: RussianFoodClient, fid: int) -> tuple[set[int], list[dict], str | None]:
    try:
        first_page = client.get_category_page(fid, page=1)
        recipe_ids = parse_category_recipe_ids(first_page)
        previews = parse_category_preview(first_page, fid)
        max_page = parse_max_page(first_page)

        for page in range(2, max_page + 1):
            html = client.get_category_page(fid, page=page)
            recipe_ids.update(parse_category_recipe_ids(html))
            previews.extend(parse_category_preview(html, fid))

        return recipe_ids, previews, None
    except Exception as error:
        return set(), [], str(error)


def collect_categories(client: RussianFoodClient, output_path: Path) -> list[dict]:
    html = client.get("/recipes/")
    categories = parse_category_links(html)
    records = [
        {
            "id": fid,
            "name": name,
            "url": f"https://www.russianfood.com/recipes/bytype/?fid={fid}",
        }
        for fid, name in categories
    ]
    save_json(output_path, records)
    return records


def collect_recipe_ids(
    client: RussianFoodClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
    workers: int = 1,
) -> dict:
    categories = load_json(categories_path, [])
    existing_ids = set(load_json(ids_path, [])) if ids_path.exists() else set()
    existing_previews = {item["id"]: item for item in load_json(previews_path, [])}
    failed_categories = load_json(failed_path, [])

    all_ids = set(existing_ids)
    all_previews = dict(existing_previews)
    new_failures: list[dict] = []

    if workers <= 1:
        iterator = tqdm(categories, desc="Категории")
        for category in iterator:
            recipe_ids, previews, error = _collect_ids_for_category(client, category["id"])
            if error:
                new_failures.append({"id": category["id"], "name": category["name"], "error": error})
                tqdm.write(f"Ошибка категории {category['id']}: {error}")
                continue
            all_ids.update(recipe_ids)
            for preview in previews:
                all_previews[preview["id"]] = preview
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_collect_ids_for_category, client, category["id"]): category
                for category in categories
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc="Категории"):
                category = futures[future]
                recipe_ids, previews, error = future.result()
                if error:
                    new_failures.append({"id": category["id"], "name": category["name"], "error": error})
                    tqdm.write(f"Ошибка категории {category['id']}: {error}")
                    continue
                all_ids.update(recipe_ids)
                for preview in previews:
                    all_previews[preview["id"]] = preview

    sorted_ids = sorted(all_ids)
    save_json(ids_path, sorted_ids)
    save_json(previews_path, list(all_previews.values()))
    save_json(failed_path, new_failures)
    return {
        "recipe_count": len(sorted_ids),
        "preview_count": len(all_previews),
        "failed_categories": len(new_failures),
    }


def retry_failed_categories(
    client: RussianFoodClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
) -> dict:
    categories = {item["id"]: item for item in load_json(categories_path, [])}
    failed = load_json(failed_path, [])
    if not failed:
        return {"retried": 0, "still_failed": 0}

    all_ids = set(load_json(ids_path, []))
    all_previews = {item["id"]: item for item in load_json(previews_path, [])}
    still_failed: list[dict] = []

    for item in tqdm(failed, desc="Повтор категорий"):
        category = categories.get(item["id"], item)
        recipe_ids, previews, error = _collect_ids_for_category(client, category["id"])
        if error:
            still_failed.append({**item, "error": error})
            continue
        all_ids.update(recipe_ids)
        for preview in previews:
            all_previews[preview["id"]] = preview

    save_json(ids_path, sorted(all_ids))
    save_json(previews_path, list(all_previews.values()))
    save_json(failed_path, still_failed)
    return {
        "retried": len(failed),
        "still_failed": len(still_failed),
        "recipe_count": len(all_ids),
    }
