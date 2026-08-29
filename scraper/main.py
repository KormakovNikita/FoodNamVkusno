#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from scraper.client import RussianFoodClient, USE_CURL_CFFI
from scraper.collector import collect_categories, collect_recipe_ids, retry_failed_categories
from scraper.scraper import retry_failed_recipes, scrape_recipes
from scraper.status import show_status

DATA_DIR = Path("data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Парсер рецептов russianfood.com")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--delay", type=float, default=5.0, help="Пауза между запросами (сек)")
    common.add_argument("--cooldown", type=float, default=300.0, help="Пауза после серии 403 (сек)")

    subparsers.add_parser("categories", parents=[common], help="Собрать категории")
    subparsers.add_parser("ids", parents=[common], help="Собрать ID рецептов")
    subparsers.add_parser("retry", parents=[common], help="Повторить категории с ошибками")

    scrape_parser = subparsers.add_parser("scrape", parents=[common], help="Скачать рецепты")
    scrape_parser.add_argument("--limit", type=int, default=None, help="Сколько рецептов скачать")

    retry_recipes = subparsers.add_parser("retry-recipes", parents=[common], help="Повторить рецепты с ошибками")
    retry_recipes.add_argument("--limit", type=int, default=None)

    all_parser = subparsers.add_parser("all", parents=[common], help="Полный цикл")
    all_parser.add_argument("--limit", type=int, default=None)

    subparsers.add_parser("status", help="Показать прогресс")

    return parser


def make_client(args: argparse.Namespace) -> RussianFoodClient:
    client = RussianFoodClient(delay=args.delay, cooldown_seconds=args.cooldown)
    print(f"HTTP backend: {client.backend}" + ("" if USE_CURL_CFFI else " (установите curl_cffi для обхода 403)"))
    client.warmup()
    return client


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    categories_path = DATA_DIR / "categories.json"
    ids_path = DATA_DIR / "recipe_ids.json"
    previews_path = DATA_DIR / "recipe_previews.json"
    failed_categories_path = DATA_DIR / "failed_categories.json"
    recipes_path = DATA_DIR / "recipes.jsonl"
    failed_recipes_path = DATA_DIR / "failed_recipes.jsonl"
    progress_path = DATA_DIR / "progress.json"

    if args.command == "status":
        show_status(DATA_DIR)
        return

    client = make_client(args)

    if args.command == "categories":
        categories = collect_categories(client, categories_path)
        print(f"Сохранено категорий: {len(categories)}")
        return

    if args.command == "ids":
        if not categories_path.exists():
            collect_categories(client, categories_path)
        stats = collect_recipe_ids(
            client,
            categories_path,
            ids_path,
            previews_path,
            failed_categories_path,
            workers=1,
        )
        print(stats)
        return

    if args.command == "retry":
        stats = retry_failed_categories(
            client, categories_path, ids_path, previews_path, failed_categories_path
        )
        print(stats)
        return

    if args.command == "scrape":
        if not ids_path.exists():
            raise SystemExit("Сначала соберите ID: python -m scraper.main ids")
        stats = scrape_recipes(
            client,
            ids_path,
            recipes_path,
            failed_recipes_path,
            progress_path,
            limit=args.limit,
        )
        print(stats)
        return

    if args.command == "retry-recipes":
        stats = retry_failed_recipes(
            client,
            failed_recipes_path,
            recipes_path,
            progress_path,
            limit=args.limit,
        )
        print(stats)
        return

    if args.command == "all":
        categories = collect_categories(client, categories_path)
        print(f"Категорий: {len(categories)}")
        stats_ids = collect_recipe_ids(
            client,
            categories_path,
            ids_path,
            previews_path,
            failed_categories_path,
            workers=1,
        )
        print(stats_ids)
        stats_scrape = scrape_recipes(
            client,
            ids_path,
            recipes_path,
            failed_recipes_path,
            progress_path,
            limit=args.limit,
        )
        print(stats_scrape)


if __name__ == "__main__":
    main()
