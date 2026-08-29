from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.client import BASE_URL


@dataclass
class Ingredient:
    name: str
    amount: str = ""
    note: str = ""


@dataclass
class Step:
    number: int
    text: str
    image_url: Optional[str] = None


@dataclass
class Nutrition:
    calories: str = ""
    protein: str = ""
    fat: str = ""
    carbs: str = ""


@dataclass
class Recipe:
    id: int
    url: str
    title: str
    description: str = ""
    author: str = ""
    portions: Optional[str] = None
    cook_time: str = ""
    image_url: Optional[str] = None
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    nutrition: Optional[Nutrition] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _abs_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE_URL, url)
    return url


def parse_recipe_ids_from_html(html: str) -> set[int]:
    ids = set(int(value) for value in re.findall(r"/recipes/show/(\d+)", html))
    json_ids = re.findall(r'"url":"https://www\.povarenok\.ru/recipes/show/(\d+)/?"', html)
    ids.update(int(value) for value in json_ids)
    return ids


def parse_max_page(html: str) -> int:
    match = re.search(r"new\s+Paginator\([^,]+,\s*(\d+),", html)
    if match:
        return max(1, int(match.group(1)))
    return 1


def parse_categories(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    categories: list[dict[str, Any]] = []
    seen: set[int] = set()
    for link in soup.select('a[href*="/recipes/category/"]'):
        href = link.get("href", "")
        match = re.search(r"/recipes/category/(\d+)/?", href)
        if not match:
            continue
        category_id = int(match.group(1))
        if category_id in seen:
            continue
        seen.add(category_id)
        name = _clean(link.get_text())
        if not name:
            continue
        categories.append(
            {
                "id": category_id,
                "name": name,
                "url": f"{BASE_URL}/recipes/category/{category_id}/",
            }
        )
    return categories


def parse_category_previews(html: str, category_id: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    previews: list[dict[str, Any]] = []
    for link in soup.select('a[href*="/recipes/show/"]'):
        match = re.search(r"/recipes/show/(\d+)/?", link.get("href", ""))
        if not match:
            continue
        recipe_id = int(match.group(1))
        title = _clean(link.get("title") or link.get_text())
        img = link.select_one("img")
        previews.append(
            {
                "id": recipe_id,
                "title": title,
                "image_url": _abs_url(img.get("src") if img else None),
                "category_id": category_id,
            }
        )
    return previews


def parse_recipe(html: str, recipe_id: int) -> Optional[Recipe]:
    soup = BeautifulSoup(html, "lxml")
    recipe_root = soup.select_one('[itemtype="http://schema.org/Recipe"]')
    if not recipe_root:
        return None

    title_tag = recipe_root.select_one('[itemprop="name"]')
    title = _clean(title_tag.get_text()) if title_tag else ""
    if not title:
        return None

    description_tag = recipe_root.select_one('[itemprop="description"]')
    description = _clean(description_tag.get_text()) if description_tag else ""

    author_tag = recipe_root.select_one('[itemprop="author"]')
    author = _clean(author_tag.get_text()) if author_tag else ""

    portions_tag = recipe_root.select_one('[itemprop="recipeYield"]')
    portions = _clean(portions_tag.get_text()) if portions_tag else None

    time_tag = recipe_root.select_one('[itemprop="totalTime"]')
    cook_time = _clean(time_tag.get_text()) if time_tag else ""

    image_tag = recipe_root.select_one('[itemprop="image"]')
    image_url = _abs_url(image_tag.get("src") if image_tag else None)

    ingredients: list[Ingredient] = []
    for item in recipe_root.select('[itemprop="recipeIngredient"]'):
        link = item.select_one("a span")
        name = _clean(link.get_text()) if link else ""
        spans = item.select("span")
        amount = _clean(spans[-1].get_text()) if spans else ""
        note_parts = []
        for node in item.contents:
            if getattr(node, "name", None) is None:
                text = _clean(str(node))
                if text and text not in {"—", "-"}:
                    note_parts.append(text.strip("() "))
        note = _clean(" ".join(note_parts))
        if name or amount:
            ingredients.append(Ingredient(name=name, amount=amount, note=note))

    steps: list[Step] = []
    instructions = recipe_root.select('[itemprop="recipeInstructions"] li.cooking-bl')
    for index, block in enumerate(instructions, start=1):
        text_tag = block.select_one("div p")
        if not text_tag:
            continue
        img_tag = block.select_one("img[itemprop=image], img")
        steps.append(
            Step(
                number=index,
                text=_clean(text_tag.get_text(" ", strip=True)),
                image_url=_abs_url(img_tag.get("src") if img_tag else None),
            )
        )

    categories = []
    for tag in recipe_root.select('[itemprop="recipeCategory"]'):
        name = _clean(tag.get_text())
        if name and name not in categories:
            categories.append(name)

    nutrition = None
    nutrition_root = recipe_root.select_one('[itemtype="http://schema.org/NutritionInformation"]')
    if nutrition_root:
        nutrition = Nutrition(
            calories=_clean(nutrition_root.select_one('[itemprop="calories"]').get_text())
            if nutrition_root.select_one('[itemprop="calories"]')
            else "",
            protein=_clean(nutrition_root.select_one('[itemprop="proteinContent"]').get_text())
            if nutrition_root.select_one('[itemprop="proteinContent"]')
            else "",
            fat=_clean(nutrition_root.select_one('[itemprop="fatContent"]').get_text())
            if nutrition_root.select_one('[itemprop="fatContent"]')
            else "",
            carbs=_clean(nutrition_root.select_one('[itemprop="carbohydrateContent"]').get_text())
            if nutrition_root.select_one('[itemprop="carbohydrateContent"]')
            else "",
        )

    return Recipe(
        id=recipe_id,
        url=f"{BASE_URL}/recipes/show/{recipe_id}/",
        title=title,
        description=description,
        author=author,
        portions=portions,
        cook_time=cook_time,
        image_url=image_url,
        ingredients=ingredients,
        steps=steps,
        categories=categories,
        nutrition=nutrition,
    )


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_scraped_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    scraped: set[int] = set()
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                continue
            scraped.add(record["id"])
    return scraped
