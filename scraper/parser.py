from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.client import BASE_URL, RussianFoodClient


@dataclass
class Ingredient:
    name: str
    amount: str = ""


@dataclass
class Step:
    number: int
    text: str
    image_url: Optional[str] = None


@dataclass
class Comment:
    author: str
    date: str
    text: str


@dataclass
class Recipe:
    id: int
    url: str
    title: str
    description: str = ""
    portions: Optional[int] = None
    calories_per_portion: Optional[str] = None
    author: str = ""
    date: str = ""
    image_url: Optional[str] = None
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _abs_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE_URL, url)
    return url


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_int(value: str) -> Optional[int]:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else None


def parse_recipe_from_print(html: str, recipe_id: int) -> Optional[Recipe]:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("font", style=re.compile(r"font-size:\s*20px", re.I))
    if not title_tag:
        return None
    title = _clean_text(title_tag.get_text())
    if not title:
        return None

    description = ""
    portions = None
    calories = None
    rcp_text = soup.select_one("td.rcp_text")
    if rcp_text:
        for paragraph in rcp_text.find_all("p"):
            text = _clean_text(paragraph.get_text())
            if not text:
                continue
            lower = text.lower()
            if "количество порций" in lower:
                portions = _extract_int(text)
            elif "калорийность" in lower:
                match = re.search(r"(\d+\s*ккал)", text, re.I)
                calories = match.group(1) if match else text
            elif not description and not text.startswith("Количество") and not text.startswith("Калорийность"):
                description = text

    image_tag = soup.select_one("img.main_photo")
    image_url = _abs_url(image_tag.get("src") if image_tag else None)

    ingredients: list[Ingredient] = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) != 2:
            continue
        name = _clean_text(cells[0].get_text())
        amount = _clean_text(cells[1].get_text())
        if not name or name.lower() in {"продукты", "ингредиенты"}:
            continue
        if name.startswith("печать") or "blank.gif" in str(row):
            continue
        ingredients.append(Ingredient(name=name, amount=amount))

    steps: list[Step] = []
    step_number = 0
    for row in soup.select("table.step_images tr"):
        text_tag = row.select_one("p.step_by_step_text")
        if not text_tag:
            continue
        step_number += 1
        img_tag = row.select_one("img")
        steps.append(
            Step(
                number=step_number,
                text=_clean_text(text_tag.get_text()),
                image_url=_abs_url(img_tag.get("src") if img_tag else None),
            )
        )

    categories: list[str] = []
    categories_block = soup.select_one("#link_to_site")
    if categories_block:
        for link in categories_block.select("a.mainNav"):
            name = _clean_text(link.get_text())
            if name:
                categories.append(name)

    comments: list[Comment] = []
    comments_root = soup.select_one("#comments_print")
    if comments_root:
        user_names = comments_root.select("span.user_name")
        dates = comments_root.select("span.datetime")
        texts = comments_root.select("td.comment_text")
        for index, text_cell in enumerate(texts):
            comments.append(
                Comment(
                    author=_clean_text(user_names[index].get_text()) if index < len(user_names) else "",
                    date=_clean_text(dates[index].get_text()) if index < len(dates) else "",
                    text=_clean_text(text_cell.get_text()),
                )
            )

    return Recipe(
        id=recipe_id,
        url=f"{BASE_URL}/recipes/recipe.php?rid={recipe_id}",
        title=title,
        description=description,
        portions=portions,
        calories_per_portion=calories,
        image_url=image_url,
        ingredients=ingredients,
        steps=steps,
        categories=categories,
        comments=comments,
    )


def parse_recipe_from_page(html: str, recipe_id: int) -> Optional[Recipe]:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.select_one("h1.title")
    if not title_tag:
        return None
    title = _clean_text(title_tag.get_text())
    if not title:
        return None

    description = ""
    announce = soup.select_one("table.recipe_new td > div > p")
    if announce:
        description = _clean_text(announce.get_text())

    portions = None
    author = ""
    date = ""
    for block in soup.select(".sub_info .el"):
        text = _clean_text(block.get_text())
        if "порци" in text.lower():
            portions = _extract_int(text)
        elif block.select_one(".ico_user"):
            link = block.select_one("a")
            author = _clean_text(link.get_text()) if link else ""
            date_match = re.search(r"\d{2}\.\d{2}\.\d{2}", text)
            date = date_match.group() if date_match else ""

    image_tag = soup.select_one("table.main_image img")
    image_url = _abs_url(image_tag.get("src") if image_tag else None)

    ingredients: list[Ingredient] = []
    for row in soup.select("table.ingr tr"):
        cell = row.select_one("td span")
        if not cell:
            continue
        line = _clean_text(cell.get_text())
        if not line or line.lower().startswith("продукты"):
            continue
        if "—" in line:
            name, amount = line.split("—", 1)
            ingredients.append(Ingredient(name=_clean_text(name), amount=_clean_text(amount)))
        else:
            ingredients.append(Ingredient(name=line))

    steps: list[Step] = []
    step_number = 0
    for step_block in soup.select("div.step_n"):
        text_tag = step_block.select_one("p")
        if not text_tag:
            continue
        step_number += 1
        img_tag = step_block.select_one("img")
        steps.append(
            Step(
                number=step_number,
                text=_clean_text(text_tag.get_text()),
                image_url=_abs_url(img_tag.get("src") if img_tag else None),
            )
        )

    categories: list[str] = []
    for link in soup.select("a.tag_have_recipes, .tags_title a"):
        name = _clean_text(link.get_text())
        if name and name not in categories:
            categories.append(name)

    return Recipe(
        id=recipe_id,
        url=f"{BASE_URL}/recipes/recipe.php?rid={recipe_id}",
        title=title,
        description=description,
        portions=portions,
        author=author,
        date=date,
        image_url=image_url,
        ingredients=ingredients,
        steps=steps,
        categories=categories,
    )


def parse_recipe(html: str, recipe_id: int, source: str = "auto") -> Optional[Recipe]:
    if source == "print":
        return parse_recipe_from_print(html, recipe_id)
    if source == "page":
        return parse_recipe_from_page(html, recipe_id)

    recipe = parse_recipe_from_print(html, recipe_id)
    if recipe and recipe.ingredients:
        return recipe
    return parse_recipe_from_page(html, recipe_id)


def parse_category_links(html: str) -> list[tuple[int, str]]:
    soup = BeautifulSoup(html, "lxml")
    categories: list[tuple[int, str]] = []
    seen: set[int] = set()
    for link in soup.select('a[href*="/recipes/bytype/?fid="]'):
        href = link.get("href", "")
        match = re.search(r"fid=(\d+)", href)
        if not match:
            continue
        fid = int(match.group(1))
        if fid in seen:
            continue
        seen.add(fid)
        name = _clean_text(link.get_text())
        categories.append((fid, name))
    return categories


def parse_category_recipe_ids(html: str) -> set[int]:
    ids = set(int(value) for value in re.findall(r"recipe\.php\?rid=(\d+)", html))
    return ids


def parse_max_page(html: str) -> int:
    pages = [int(value) for value in re.findall(r"page=(\d+)#rcp_list", html)]
    return max(pages) if pages else 1


def parse_category_preview(html: str, fid: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    previews: list[dict[str, Any]] = []
    for item in soup.select('[itemprop="itemListElement"]'):
        link = item.select_one('a[href*="recipe.php?rid="]')
        if not link:
            continue
        match = re.search(r"rid=(\d+)", link.get("href", ""))
        if not match:
            continue
        recipe_id = int(match.group(1))
        title_tag = item.select_one('[itemprop="name"]')
        description_tag = item.select_one('[itemprop="description"]')
        image_tag = item.select_one("img")
        previews.append(
            {
                "id": recipe_id,
                "title": _clean_text(title_tag.get_text()) if title_tag else "",
                "description": _clean_text(description_tag.get_text()) if description_tag else "",
                "image_url": _abs_url(image_tag.get("src") if image_tag else None),
                "category_id": fid,
            }
        )
    return previews


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
