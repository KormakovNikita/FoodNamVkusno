from __future__ import annotations

from pathlib import Path

from tqdm import tqdm

from scraper.client import PovarenokClient
from scraper.parser import (
    load_json,
    parse_categories,
    parse_category_previews,
    parse_max_page,
    parse_recipe_ids_from_html,
    save_json,
)


def collect_categories(client: PovarenokClient, output_path: Path) -> list[dict]:
    html = client.get_catalog_page()
    categories = parse_categories(html)
    save_json(output_path, categories)
    return categories


def _collect_ids_for_category(client: PovarenokClient, category_id: int) -> tuple[set[int], list[dict], str | None]:
    try:
        first_page = client.get_category_page(category_id, page=1)
        recipe_ids = parse_recipe_ids_from_html(first_page)
        previews = parse_category_previews(first_page, category_id)
        max_page = parse_max_page(first_page)

        for page in range(2, max_page + 1):
            html = client.get_category_page(category_id, page=page)
            page_ids = parse_recipe_ids_from_html(html)
            if not page_ids:
                break
            recipe_ids.update(page_ids)
            previews.extend(parse_category_previews(html, category_id))

        return recipe_ids, previews, None
    except Exception as error:
        return set(), [], str(error)


def collect_recipe_ids(
    client: PovarenokClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
) -> dict:
    categories = load_json(categories_path, [])
    all_ids = set(load_json(ids_path, [])) if ids_path.exists() else set()
    all_previews = {item["id"]: item for item in load_json(previews_path, [])}
    failures: list[dict] = []

    for category in tqdm(categories, desc="Категории"):
        recipe_ids, previews, error = _collect_ids_for_category(client, category["id"])
        if error:
            failures.append({"id": category["id"], "name": category["name"], "error": error})
            tqdm.write(f"Ошибка категории {category['id']}: {error}")
            continue
        all_ids.update(recipe_ids)
        for preview in previews:
            all_previews[preview["id"]] = preview
        save_json(ids_path, sorted(all_ids))
        save_json(previews_path, list(all_previews.values()))

    save_json(failed_path, failures)
    return {
        "recipe_count": len(all_ids),
        "preview_count": len(all_previews),
        "failed_categories": len(failures),
    }


def retry_failed_categories(
    client: PovarenokClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
) -> dict:
    categories = {item["id"]: item for item in load_json(categories_path, [])}
    failed = load_json(failed_path, [])
    if not failed:
        return {"retried": 0, "still_failed": 0, "recipe_count": len(load_json(ids_path, []))}

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
