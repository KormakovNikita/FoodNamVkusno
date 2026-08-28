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


def collect_categories(client: RussianFoodClient, output_path: Path) -> list[dict]:
    html = client.get("/recipes/")
    categories = parse_category_links(html)
    records = [{"id": fid, "name": name, "url": f"https://www.russianfood.com/recipes/bytype/?fid={fid}"} for fid, name in categories]
    save_json(output_path, records)
    return records


def _collect_ids_for_category(client: RussianFoodClient, fid: int) -> tuple[set[int], list[dict]]:
    first_page = client.get_category_page(fid, page=1)
    recipe_ids = parse_category_recipe_ids(first_page)
    previews = parse_category_preview(first_page, fid)
    max_page = parse_max_page(first_page)

    for page in range(2, max_page + 1):
        html = client.get_category_page(fid, page=page)
        recipe_ids.update(parse_category_recipe_ids(html))
        previews.extend(parse_category_preview(html, fid))

    return recipe_ids, previews


def collect_recipe_ids(
    client: RussianFoodClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    workers: int = 4,
) -> dict:
    categories = load_json(categories_path, [])
    all_ids: set[int] = set()
    all_previews: dict[int, dict] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_collect_ids_for_category, client, category["id"]): category
            for category in categories
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Категории"):
            category = futures[future]
            try:
                recipe_ids, previews = future.result()
                all_ids.update(recipe_ids)
                for preview in previews:
                    all_previews[preview["id"]] = preview
            except Exception as error:
                tqdm.write(f"Ошибка категории {category['id']}: {error}")

    sorted_ids = sorted(all_ids)
    save_json(ids_path, sorted_ids)
    save_json(previews_path, list(all_previews.values()))
    return {"recipe_count": len(sorted_ids), "preview_count": len(all_previews)}
