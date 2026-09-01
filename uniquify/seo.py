from __future__ import annotations

import hashlib
import re
import unicodedata


def slugify(text: str, max_length: int = 80) -> str:
    text = text.lower().strip()
    translit_map = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    result = []
    for char in text:
        if char in translit_map:
            result.append(translit_map[char])
        elif char.isalnum():
            result.append(char)
        elif char in {" ", "-", "_"}:
            result.append("-")
    slug = re.sub(r"-+", "-", "".join(result)).strip("-")
    return slug[:max_length].strip("-")


def build_meta_title(title: str, site_name: str = "") -> str:
    clean = re.sub(r"\s+", " ", title).strip()
    if site_name and site_name.lower() not in clean.lower():
        return f"{clean} — пошаговый рецепт | {site_name}"
    return f"{clean} — пошаговый рецепт с фото"


def build_meta_description(title: str, description: str, portions: str | None = None) -> str:
    base = description.strip() if description else f"Готовим {title.lower()} дома по простому рецепту."
    base = re.sub(r"\s+", " ", base)
    if portions:
        suffix = f" Порций: {portions}."
        if suffix.strip() not in base:
            base = base.rstrip(".") + "." + suffix
    if len(base) > 155:
        base = base[:152].rsplit(" ", 1)[0] + "..."
    return base


def build_keywords(title: str, categories: list[str], ingredients: list[dict]) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip().lower()
        if len(value) < 3 or value in seen:
            return
        seen.add(value)
        keywords.append(value)

    add(title)
    for category in categories[:5]:
        add(category)
    for item in ingredients[:8]:
        add(str(item.get("name", "")))
    add("рецепт")
    add("готовка дома")
    return keywords[:15]


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
