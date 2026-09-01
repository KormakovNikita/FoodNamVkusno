#!/usr/bin/env python3
"""HTML-превью одного рецепта для проверки."""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_recipe(path: Path, recipe_id: int | None) -> dict:
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                continue
            if recipe_id is None or record.get("id") == recipe_id:
                return record
    raise SystemExit("Рецепт не найден")


def render_recipe(recipe: dict) -> str:
    title = html.escape(recipe.get("title", ""))
    description = html.escape(recipe.get("description", ""))
    meta_title = html.escape(recipe.get("meta_title", title))
    meta_description = html.escape(recipe.get("meta_description", description))
    image_url = html.escape(recipe.get("image_url", ""))
    author = html.escape(recipe.get("author", ""))
    portions = html.escape(str(recipe.get("portions", "")))
    cook_time = html.escape(str(recipe.get("cook_time", "")))
    keywords = ", ".join(html.escape(k) for k in recipe.get("keywords", []))

    ingredients_html = "\n".join(
        f"<li><strong>{html.escape(item.get('name', ''))}</strong> — {html.escape(item.get('amount', ''))}</li>"
        for item in recipe.get("ingredients", [])
    )

    steps_html = ""
    for step in recipe.get("steps", []):
        text = html.escape(step.get("text", ""))
        step_img = step.get("image_url")
        img_block = f'<img src="{html.escape(step_img)}" alt="Шаг {step.get("number", "")}" loading="lazy">' if step_img else ""
        steps_html += f"""
        <div class="step">
          <h3>Шаг {step.get("number", "")}</h3>
          <p>{text}</p>
          {img_block}
        </div>
        """

    categories = ", ".join(html.escape(c) for c in recipe.get("categories", []))
    nutrition = recipe.get("nutrition") or {}

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{meta_title}</title>
  <meta name="description" content="{meta_description}">
  <meta name="keywords" content="{keywords}">
  <style>
    body {{ font-family: Georgia, serif; max-width: 860px; margin: 0 auto; padding: 24px; color: #222; line-height: 1.6; }}
    h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
    .meta {{ color: #666; margin-bottom: 1.5rem; }}
    .hero img {{ width: 100%; border-radius: 12px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px; }}
    ul {{ padding-left: 1.2rem; }}
    .step {{ margin: 24px 0; padding-bottom: 16px; border-bottom: 1px solid #eee; }}
    .step img {{ max-width: 100%; border-radius: 8px; margin-top: 8px; }}
    .seo {{ background: #f7f7f7; padding: 12px; border-radius: 8px; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <article>
    <h1>{title}</h1>
    <p class="meta">Автор: {author} | Порций: {portions} | Время: {cook_time}</p>
    <div class="hero"><img src="{image_url}" alt="{title}"></div>
    <p>{description}</p>
    <div class="grid">
      <section>
        <h2>Ингредиенты</h2>
        <ul>{ingredients_html}</ul>
      </section>
      <section>
        <h2>Категории</h2>
        <p>{categories}</p>
        <h2>Пищевая ценность</h2>
        <p>Калории: {html.escape(str(nutrition.get('calories', '')))}</p>
        <p>Белки: {html.escape(str(nutrition.get('protein', '')))} | Жиры: {html.escape(str(nutrition.get('fat', '')))} | Углеводы: {html.escape(str(nutrition.get('carbs', '')))}</p>
      </section>
    </div>
    <section>
      <h2>Приготовление</h2>
      {steps_html}
    </section>
    <section class="seo">
      <strong>SEO slug:</strong> {html.escape(recipe.get('slug', ''))}<br>
      <strong>Meta title:</strong> {meta_title}<br>
      <strong>Meta description:</strong> {meta_description}
    </section>
  </article>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="HTML-превью рецепта")
    parser.add_argument("--input", type=Path, default=Path("data/recipes_unique.jsonl"))
    parser.add_argument("--id", type=int, default=None, help="ID рецепта (по умолчанию первый)")
    parser.add_argument("--output", type=Path, default=Path("data/preview_recipe.html"))
    args = parser.parse_args()

    recipe = load_recipe(args.input, args.id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_recipe(recipe), encoding="utf-8")
    print(f"Рецепт: {recipe.get('title')}")
    print(f"Фото: {recipe.get('image_url')}")
    print(f"Ингредиентов: {len(recipe.get('ingredients', []))}, шагов: {len(recipe.get('steps', []))}")
    print(f"HTML: {args.output}")


if __name__ == "__main__":
    main()
