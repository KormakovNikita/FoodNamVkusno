from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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

_write_lock = threading.Lock()
_worker_state = threading.local()


def _clone_client(client: PovarenokClient) -> PovarenokClient:
    return PovarenokClient(
        delay=client.delay,
        timeout=client.timeout,
        max_retries=client.max_retries,
        cooldown_after=client.cooldown_after,
        cooldown_seconds=client.cooldown_seconds,
    )


def _init_worker_client(template: PovarenokClient) -> None:
    _worker_state.client = _clone_client(template)


def _get_worker_client(template: PovarenokClient) -> PovarenokClient:
    client = getattr(_worker_state, "client", None)
    if client is None:
        client = _clone_client(template)
        _worker_state.client = client
    return client


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


def _handle_result(result: dict, output_path: Path, failed_path: Path) -> bool:
    if "error" in result:
        tqdm.write(f"[!] ID {result['id']}: {result['error'][:100]}")
    return _store_result(result, output_path, failed_path)


def _store_result(result: dict, output_path: Path, failed_path: Path) -> bool:
    with _write_lock:
        if "error" in result:
            append_jsonl(failed_path, result)
            return False
        append_jsonl(output_path, result)
        return True


def scrape_recipes(
    client: PovarenokClient,
    ids_path: Path,
    output_path: Path,
    failed_path: Path,
    progress_path: Path,
    limit: int | None = None,
    workers: int = 1,
) -> dict:
    recipe_ids = load_json(ids_path, [])
    scraped_ids = load_scraped_ids(output_path)
    pending = [recipe_id for recipe_id in recipe_ids if recipe_id not in scraped_ids]
    if limit is not None:
        pending = pending[:limit]

    success_count = 0
    error_count = 0
    workers = max(1, workers)

    if workers == 1:
        for recipe_id in tqdm(pending, desc="Рецепты"):
            result = _scrape_one(client, recipe_id)
            if _handle_result(result, output_path, failed_path):
                success_count += 1
            else:
                error_count += 1
    else:
        print(f"Параллельно: {workers} потоков, пауза {client.delay} сек на поток")

        def worker_task(recipe_id: int) -> dict:
            return _scrape_one(_get_worker_client(client), recipe_id)

        with ThreadPoolExecutor(
            max_workers=workers,
            initializer=_init_worker_client,
            initargs=(client,),
        ) as executor:
            futures = {executor.submit(worker_task, recipe_id): recipe_id for recipe_id in pending}
            for future in tqdm(as_completed(futures), total=len(pending), desc="Рецепты"):
                result = future.result()
                if _handle_result(result, output_path, failed_path):
                    success_count += 1
                else:
                    error_count += 1

    progress = {
        "source": "povarenok.ru",
        "total_ids": len(recipe_ids),
        "scraped_ok": len(load_scraped_ids(output_path)),
        "failed": _count_jsonl(failed_path),
        "last_success_count": success_count,
        "last_error_count": error_count,
        "backend": client.backend,
        "workers": workers,
    }
    save_json(progress_path, progress)
    return progress


def retry_failed_recipes(
    client: PovarenokClient,
    failed_path: Path,
    output_path: Path,
    progress_path: Path,
    limit: int | None = None,
    workers: int = 1,
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
    workers = max(1, workers)

    if workers == 1:
        for record in tqdm(failed_records, desc="Повтор рецептов"):
            result = _scrape_one(client, record["id"])
            if "error" in result:
                still_failed.append(result)
                continue
            append_jsonl(output_path, result)
            success_count += 1
    else:
        print(f"Параллельно: {workers} потоков")

        def worker_task(record: dict) -> dict:
            return _scrape_one(_get_worker_client(client), record["id"])

        with ThreadPoolExecutor(
            max_workers=workers,
            initializer=_init_worker_client,
            initargs=(client,),
        ) as executor:
            futures = {executor.submit(worker_task, record): record for record in failed_records}
            for future in tqdm(as_completed(futures), total=len(failed_records), desc="Повтор рецептов"):
                result = future.result()
                if "error" in result:
                    with _write_lock:
                        still_failed.append(result)
                else:
                    with _write_lock:
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
            "workers": workers,
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
