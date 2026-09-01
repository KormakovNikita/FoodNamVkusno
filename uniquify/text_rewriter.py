from __future__ import annotations

import json
import os
import random
import re
from typing import Any, Optional

from uniquify.seo import build_keywords, build_meta_description, build_meta_title, slugify


REMOVE_PHRASES = [
    r"приятного аппетита!?",
    r"рецепт\s+(непременно\s+)?пригодится!?",
    r"с\s+сайта\s+\w+\.ru",
    r"поваренок\.?ру?",
    r"russianfood\.?com?",
]

TITLE_PREFIXES = [
    "Классический ",
    "Домашний ",
    "Проверенный ",
    "Сочный ",
    "Ароматный ",
    "Нежный ",
    "Сытный ",
]

TITLE_SUFFIXES = [
    " — простой рецепт",
    " — пошагово",
    " — домашний рецепт",
    " — быстро и вкусно",
]

VERB_REPLACEMENTS = [
    (r"\bНарежьте\b", ["Нарежьте", "Аккуратно нарежьте", "Нарежьте тонко"]),
    (r"\bДобавьте\b", ["Добавьте", "Внесите", "Положите"]),
    (r"\bПеремешайте\b", ["Перемешайте", "Тщательно перемешайте", "Аккуратно перемешайте"]),
    (r"\bОбжарьте\b", ["Обжарьте", "Подрумяньте на сковороде", "Обжарьте до золотистой корочки"]),
    (r"\bВыложите\b", ["Выложите", "Аккуратно выложите", "Разложите"]),
    (r"\bЗапекайте\b", ["Запекайте", "Выпекайте в духовке", "Готовьте в духовке"]),
    (r"\bДоведите\b", ["Доведите", "Доведите аккуратно"]),
    (r"\bПодготовьте\b", ["Подготовьте", "Заранее подготовьте", "Подготовьте все"]),
    (r"\bПромойте\b", ["Промойте", "Тщательно промойте", "Промойте под проточной водой"]),
    (r"\bПосолите\b", ["Посолите", "Добавьте соль", "Приправьте солью"]),
    (r"\bПеремешайте\b", ["Перемешайте", "Смешайте до однородности"]),
]

SYNONYMS = {
    "вкусный": ["ароматный", "насыщенный", "аппетитный"],
    "простой": ["лёгкий", "доступный", "понятный"],
    "быстро": ["за короткое время", "без лишних хлопот", "без долгого ожидания"],
    "блюдо": ["кушанье", "рецепт", "закуска"],
    "салат": ["салатик", "овощная закуска"],
    "суп": ["первое блюдо", "супчик"],
    "духовке": ["духовом шкафу", "духовке"],
    "сковороде": ["сковородке", "разогретой сковороде"],
    "мягк": ["нежн", "тающ"],
    "хрустящ": ["золотист", "хрустящ"],
}


class OfflineTextRewriter:
    def __init__(self, site_name: str = "FoodNamVkusno") -> None:
        self.site_name = site_name

    def _rng(self, text: str, salt: str = "") -> random.Random:
        return random.Random(abs(hash(f"{salt}:{text}")) % (2**32))

    def _clean_source_refs(self, text: str) -> str:
        result = text
        for pattern in REMOVE_PHRASES:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", result).strip(" .")

    def _apply_synonyms(self, text: str, rng: random.Random, ratio: float = 0.25) -> str:
        def replace_word(word: str) -> str:
            match = re.match(r"^([^\w]*)([\w\u0400-\u04FF]+)([^\w]*)$", word)
            if not match:
                return word
            prefix, core, suffix = match.groups()
            lower = core.lower()
            if lower in SYNONYMS and rng.random() < ratio:
                replacement = rng.choice(SYNONYMS[lower])
                if core[0].isupper():
                    replacement = replacement.capitalize()
                return prefix + replacement + suffix
            return word

        return " ".join(replace_word(word) for word in text.split())

    def _rewrite_sentence(self, text: str, rng: random.Random) -> str:
        result = self._clean_source_refs(text)
        for pattern, options in VERB_REPLACEMENTS:
            if re.search(pattern, result):
                result = re.sub(pattern, rng.choice(options), result, count=1)
                break
        result = self._apply_synonyms(result, rng)
        if result and result[0].islower():
            result = result[0].upper() + result[1:]
        return result

    def rewrite_title(self, title: str) -> str:
        rng = self._rng(title, "title")
        clean = self._clean_source_refs(title)
        if rng.random() > 0.35:
            prefix = rng.choice(TITLE_PREFIXES)
            if not clean.lower().startswith(prefix.lower().strip()):
                clean = prefix + clean[0].lower() + clean[1:] if clean else prefix.strip()
        if rng.random() > 0.4:
            clean = clean.rstrip(".") + rng.choice(TITLE_SUFFIXES)
        return re.sub(r"\s+", " ", clean).strip()

    def rewrite_description(self, description: str, title: str) -> str:
        rng = self._rng(description or title, "desc")
        if not description:
            description = f"{title} — удобный домашний рецепт с понятными шагами и доступными ингредиентами."
        parts = re.split(r"(?<=[.!?])\s+", self._clean_source_refs(description))
        rewritten = [self._rewrite_sentence(part, rng) for part in parts if part.strip()]
        text = " ".join(rewritten)
        if "рецепт" not in text.lower():
            text += f" Пошаговый рецепт «{title}» подойдёт для повседневного и праздничного стола."
        return re.sub(r"\s+", " ", text).strip()

    def rewrite_step(self, text: str, step_number: int) -> str:
        rng = self._rng(text, f"step-{step_number}")
        rewritten = self._rewrite_sentence(text, rng)
        if rewritten.lower().startswith("шаг"):
            return rewritten
        if step_number == 1 and rng.random() > 0.5:
            starters = ["Для начала", "Сначала", "На первом этапе"]
            rewritten = f"{rng.choice(starters)} {rewritten[0].lower() + rewritten[1:]}"
        return rewritten

    def rewrite_ingredient_name(self, name: str) -> str:
        rng = self._rng(name, "ing")
        return self._apply_synonyms(name, rng, ratio=0.15)

    def rewrite_recipe(self, recipe: dict[str, Any]) -> dict[str, Any]:
        title = self.rewrite_title(recipe.get("title", ""))
        description = self.rewrite_description(recipe.get("description", ""), title)

        ingredients = []
        for item in recipe.get("ingredients", []):
            ingredients.append(
                {
                    **item,
                    "name": self.rewrite_ingredient_name(str(item.get("name", ""))),
                }
            )

        steps = []
        for step in recipe.get("steps", []):
            steps.append(
                {
                    **step,
                    "text": self.rewrite_step(str(step.get("text", "")), int(step.get("number", 0) or 0)),
                }
            )

        categories = list(dict.fromkeys(recipe.get("categories", [])))
        portions = recipe.get("portions")
        portions_text = str(portions) if portions else None

        result = {
            **recipe,
            "title": title,
            "description": description,
            "ingredients": ingredients,
            "steps": steps,
            "author": self.site_name,
            "source_id": recipe.get("id"),
            "slug": slugify(title),
            "meta_title": build_meta_title(title, self.site_name),
            "meta_description": build_meta_description(title, description, portions_text),
            "keywords": build_keywords(title, categories, ingredients),
            "uniquified": True,
            "rewrite_mode": "offline",
        }
        if recipe.get("url"):
            result["source_url"] = recipe["url"]
            result["url"] = f"/recipes/{result['slug']}-{recipe['id']}/"
        return result


class LLMTextRewriter:
    def __init__(
        self,
        site_name: str = "FoodNamVkusno",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.site_name = site_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("UNIQUIFY_MODEL", "gpt-4o-mini")
        if not self.api_key:
            raise RuntimeError("Для LLM-режима нужен OPENAI_API_KEY")

    def rewrite_recipe(self, recipe: dict[str, Any]) -> dict[str, Any]:
        import urllib.error
        import urllib.request

        prompt = {
            "title": recipe.get("title", ""),
            "description": recipe.get("description", ""),
            "portions": recipe.get("portions"),
            "cook_time": recipe.get("cook_time"),
            "ingredients": recipe.get("ingredients", []),
            "steps": [{"number": s.get("number"), "text": s.get("text")} for s in recipe.get("steps", [])],
            "categories": recipe.get("categories", []),
        }
        system = (
            "Ты SEO-редактор кулинарного сайта. Перепиши рецепт полностью уникально на русском языке. "
            "Сохрани точные количества ингредиентов. Не упоминай другие сайты. "
            "Сделай текст полезным для поисковиков, естественным и без клише. "
            "Верни только JSON с полями: title, description, ingredients[{name,amount,note}], "
            "steps[{number,text}], meta_description."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.9,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API error {error.code}: {body[:300]}") from error

        content = data["choices"][0]["message"]["content"]
        rewritten = json.loads(content)

        title = rewritten.get("title") or recipe.get("title", "")
        description = rewritten.get("description") or recipe.get("description", "")
        portions_text = str(recipe.get("portions")) if recipe.get("portions") else None

        result = {
            **recipe,
            "title": title,
            "description": description,
            "ingredients": rewritten.get("ingredients") or recipe.get("ingredients", []),
            "steps": self._merge_steps(recipe.get("steps", []), rewritten.get("steps", [])),
            "author": self.site_name,
            "source_id": recipe.get("id"),
            "slug": slugify(title),
            "meta_title": build_meta_title(title, self.site_name),
            "meta_description": rewritten.get("meta_description") or build_meta_description(title, description, portions_text),
            "keywords": build_keywords(title, recipe.get("categories", []), rewritten.get("ingredients") or recipe.get("ingredients", [])),
            "uniquified": True,
            "rewrite_mode": "llm",
        }
        if recipe.get("url"):
            result["source_url"] = recipe["url"]
            result["url"] = f"/recipes/{result['slug']}-{recipe['id']}/"
        return result

    @staticmethod
    def _merge_steps(original_steps: list[dict], new_steps: list[dict]) -> list[dict]:
        text_by_number = {int(step.get("number", idx + 1)): step.get("text", "") for idx, step in enumerate(new_steps)}
        merged = []
        for step in original_steps:
            number = int(step.get("number", 0) or 0)
            merged.append({**step, "text": text_by_number.get(number, step.get("text", ""))})
        return merged


def create_rewriter(mode: str, site_name: str = "FoodNamVkusno") -> OfflineTextRewriter | LLMTextRewriter:
    if mode == "llm":
        return LLMTextRewriter(site_name=site_name)
    return OfflineTextRewriter(site_name=site_name)
