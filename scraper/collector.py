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


def _collect_ids_for_category(
    client: PovarenokClient,
    category_id: int,
    max_pages: int | None = None,
) -> tuple[set[int], list[dict], str | None]:
    try:
        first_page = client.get_category_page(category_id, page=1)
        recipe_ids = parse_recipe_ids_from_html(first_page)
        previews = parse_category_previews(first_page, category_id)
        max_page = parse_max_page(first_page)
        if max_pages is not None:
            max_page = min(max_page, max_pages)

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


def collect_recipe_ids_from_fresh(
    client: PovarenokClient,
    ids_path: Path,
    previews_path: Path,
    progress_path: Path,
    start_page: int = 1,
    max_pages: int | None = None,
) -> dict:
    first_page_html = client.get_fresh_page(1)
    total_pages = parse_max_page(first_page_html)
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    all_ids = set(load_json(ids_path, [])) if ids_path.exists() else set()
    all_previews = {item["id"]: item for item in load_json(previews_path, [])}
    progress = load_json(progress_path, {})
    resume_page = max(start_page, int(progress.get("last_fresh_page", 0)) + 1)

    if resume_page == 1:
        all_ids.update(parse_recipe_ids_from_html(first_page_html))
        for preview in parse_category_previews(first_page_html, 0):
            all_previews[preview["id"]] = preview
        save_json(ids_path, sorted(all_ids))
        save_json(previews_path, list(all_previews.values()))

    page_range = range(max(2, resume_page), total_pages + 1)
    for page in tqdm(page_range, desc="Страницы рецептов", initial=resume_page - 1, total=total_pages):
        try:
            html = client.get_fresh_page(page)
            page_ids = parse_recipe_ids_from_html(html)
            if not page_ids:
                break
            all_ids.update(page_ids)
            for preview in parse_category_previews(html, 0):
                all_previews[preview["id"]] = preview
            save_json(ids_path, sorted(all_ids))
            save_json(previews_path, list(all_previews.values()))
            save_json(progress_path, {"last_fresh_page": page, "total_pages": total_pages, "mode": "fresh"})
        except Exception as error:
            save_json(progress_path, {"last_fresh_page": page - 1, "total_pages": total_pages, "mode": "fresh"})
            raise RuntimeError(f"Ошибка на странице {page}: {error}") from error

    save_json(progress_path, {"last_fresh_page": total_pages, "total_pages": total_pages, "mode": "fresh", "done": True})
    return {
        "recipe_count": len(all_ids),
        "preview_count": len(all_previews),
        "total_pages": total_pages,
        "mode": "fresh",
    }


def collect_recipe_ids_from_categories(
    client: PovarenokClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
    max_pages_per_category: int | None = None,
) -> dict:
    categories = load_json(categories_path, [])
    all_ids = set(load_json(ids_path, [])) if ids_path.exists() else set()
    all_previews = {item["id"]: item for item in load_json(previews_path, [])}
    failures: list[dict] = []

    for category in tqdm(categories, desc="Категории"):
        recipe_ids, previews, error = _collect_ids_for_category(
            client,
            category["id"],
            max_pages=max_pages_per_category,
        )
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
        "mode": "categories",
    }


def collect_recipe_ids(
    client: PovarenokClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
    progress_path: Path,
    mode: str = "fresh",
    max_pages: int | None = None,
    max_pages_per_category: int | None = None,
) -> dict:
    if mode == "fresh":
        return collect_recipe_ids_from_fresh(
            client,
            ids_path,
            previews_path,
            progress_path,
            max_pages=max_pages,
        )
    if not categories_path.exists():
        collect_categories(client, categories_path)
    return collect_recipe_ids_from_categories(
        client,
        categories_path,
        ids_path,
        previews_path,
        failed_path,
        max_pages_per_category=max_pages_per_category,
    )


def retry_failed_categories(
    client: PovarenokClient,
    categories_path: Path,
    ids_path: Path,
    previews_path: Path,
    failed_path: Path,
    max_pages_per_category: int | None = None,
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
        recipe_ids, previews, error = _collect_ids_for_category(
            client,
            category["id"],
            max_pages=max_pages_per_category,
        )
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
