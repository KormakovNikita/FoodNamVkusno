#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from scraper.client import RussianFoodClient
from scraper.collector import collect_categories, collect_recipe_ids, retry_failed_categories
from scraper.scraper import scrape_recipes

DATA_DIR = Path("data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Парсер рецептов russianfood.com")
    subparsers = parser.add_subparsers(dest="command", required=True)

    categories_parser = subparsers.add_parser("categories", help="Собрать категории")
    categories_parser.add_argument("--delay", type=float, default=0.35)

    ids_parser = subparsers.add_parser("ids", help="Собрать ID рецептов из категорий")
    ids_parser.add_argument("--delay", type=float, default=1.0)
    ids_parser.add_argument("--workers", type=int, default=1)

    retry_parser = subparsers.add_parser("retry", help="Повторить сбор для категорий с ошибками")
    retry_parser.add_argument("--delay", type=float, default=1.5)

    scrape_parser = subparsers.add_parser("scrape", help="Спарсить рецепты по ID")
    scrape_parser.add_argument("--delay", type=float, default=1.0)
    scrape_parser.add_argument("--workers", type=int, default=2)
    scrape_parser.add_argument("--limit", type=int, default=None)

    all_parser = subparsers.add_parser("all", help="Полный цикл: категории → ID → рецепты")
    all_parser.add_argument("--delay", type=float, default=1.0)
    all_parser.add_argument("--workers", type=int, default=2)
    all_parser.add_argument("--limit", type=int, default=None)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    categories_path = DATA_DIR / "categories.json"
    ids_path = DATA_DIR / "recipe_ids.json"
    previews_path = DATA_DIR / "recipe_previews.json"
    failed_path = DATA_DIR / "failed_categories.json"
    recipes_path = DATA_DIR / "recipes.jsonl"
    progress_path = DATA_DIR / "progress.json"

    client = RussianFoodClient(delay=args.delay)

    if args.command == "categories":
        categories = collect_categories(client, categories_path)
        print(f"Сохранено категорий: {len(categories)}")
        return

    if args.command == "ids":
        if not categories_path.exists():
            collect_categories(client, categories_path)
        stats = collect_recipe_ids(
            client, categories_path, ids_path, previews_path, failed_path, workers=args.workers
        )
        print(stats)
        return

    if args.command == "retry":
        stats = retry_failed_categories(client, categories_path, ids_path, previews_path, failed_path)
        print(stats)
        return

    if args.command == "scrape":
        if not ids_path.exists():
            if not categories_path.exists():
                collect_categories(client, categories_path)
            collect_recipe_ids(
                client,
                categories_path,
                ids_path,
                previews_path,
                failed_path,
                workers=min(args.workers, 2),
            )
        stats = scrape_recipes(
            client,
            ids_path,
            recipes_path,
            progress_path,
            workers=args.workers,
            limit=args.limit,
        )
        print(stats)
        return

    if args.command == "all":
        categories = collect_categories(client, categories_path)
        print(f"Категорий: {len(categories)}")
        stats_ids = collect_recipe_ids(
            client, categories_path, ids_path, previews_path, failed_path, workers=min(args.workers, 2)
        )
        print(stats_ids)
        stats_scrape = scrape_recipes(
            client,
            ids_path,
            recipes_path,
            progress_path,
            workers=args.workers,
            limit=args.limit,
        )
        print(stats_scrape)


if __name__ == "__main__":
    main()
