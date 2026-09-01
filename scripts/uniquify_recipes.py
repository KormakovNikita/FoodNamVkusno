#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uniquify.pipeline import UniquifyPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Уникализация рецептов: SEO-текст и обработка фотографий",
    )
    parser.add_argument("--input", type=Path, default=Path("data/recipes.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/recipes_unique.jsonl"))
    parser.add_argument("--images-dir", type=Path, default=Path("data/images"))
    parser.add_argument("--progress", type=Path, default=Path("data/uniquify_progress.json"))
    parser.add_argument("--site-name", default="FoodNamVkusno", help="Название вашего сайта для SEO")
    parser.add_argument(
        "--text-mode",
        choices=["offline", "llm"],
        default="offline",
        help="offline = без API, llm = OpenAI-compatible API (лучше для SEO)",
    )
    parser.add_argument("--text-only", action="store_true", help="Только текст, без фото")
    parser.add_argument("--images-only", action="store_true", help="Только фото, без переписывания текста")
    parser.add_argument("--force-images", action="store_true", help="Перегенерировать уже сохранённые фото")
    parser.add_argument("--main-image-only", action="store_true", help="Обрабатывать только главное фото (экономит место)")
    parser.add_argument("--limit", type=int, default=None, help="Лимит рецептов для теста")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.input.exists():
        raise SystemExit(f"Файл не найден: {args.input}")

    rewrite_text = not args.images_only
    rewrite_images = not args.text_only

    pipeline = UniquifyPipeline(
        input_path=args.input,
        output_path=args.output,
        images_dir=args.images_dir,
        progress_path=args.progress,
        site_name=args.site_name,
        text_mode=args.text_mode,
        rewrite_text=rewrite_text,
        rewrite_images=rewrite_images,
        force_images=args.force_images,
        main_image_only=args.main_image_only,
    )
    print(
        pipeline.run(limit=args.limit),
    )


if __name__ == "__main__":
    main()
