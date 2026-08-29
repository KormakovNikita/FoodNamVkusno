# Povarenok Recipe Scraper

Парсер рецептов с сайта [povarenok.ru](https://www.povarenok.ru/).

Собирает:
- название, описание, автор
- порции, время приготовления
- фото блюда
- ингредиенты с количеством
- пошаговые инструкции с фото
- категории и пищевую ценность (калории, БЖУ)

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

## Быстрый старт

```bash
# Проверить прогресс
python -m scraper.main status

# Полный цикл
python -m scraper.main all --delay 1.5

# Или по шагам
python -m scraper.main categories
python -m scraper.main ids --delay 1.5
python -m scraper.main scrape --delay 1.5
```

## Порционный режим (рекомендуется)

```bash
python -m scraper.main scrape --delay 2.0 --limit 100
```

Повторяйте команду — уже скачанные рецепты пропускаются.

## Повтор после ошибок

```bash
python -m scraper.main retry --delay 2.0
python -m scraper.main retry-recipes --delay 2.0 --limit 100
python scripts/migrate_errors.py
```

## Экспорт в JSON

```bash
python scripts/export_json.py
```

## Результаты

| Файл | Описание |
|------|----------|
| `data/categories.json` | Категории рецептов |
| `data/recipe_ids.json` | Уникальные ID |
| `data/recipe_previews.json` | Краткие карточки |
| `data/recipes.jsonl` | Полные рецепты |
| `data/failed_recipes.jsonl` | Ошибки скачивания |
| `data/recipes.json` | Экспорт в один JSON |

## Примечания

- Сайт использует кодировку Windows-1251 — парсер обрабатывает автоматически.
- Povarenok проще парсить, чем russianfood.com — нет жёсткого Cloudflare.
- Рекомендуется `curl_cffi` (`pip install curl_cffi`).
- Парсер поддерживает возобновление с места остановки.
