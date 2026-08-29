# RussianFood Recipe Scraper

Парсер рецептов с сайта [russianfood.com](https://www.russianfood.com/).

Собирает категории, ID рецептов и полную информацию по каждому рецепту:

- название, описание, автор, дата
- количество порций и калорийность (если указаны)
- фото блюда
- ингредиенты с количеством
- пошаговые инструкции с фото
- категории и теги
- отзывы (если доступны в печатной версии)

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Использование

### Проверить прогресс

```bash
python -m scraper.main status
```

### 1. Сбор категорий

```bash
python -m scraper.main categories
```

### 2. Сбор ID рецептов из всех категорий

```bash
python -m scraper.main ids --delay 5.0
```

### 3. Парсинг рецептов

```bash
python -m scraper.main scrape --delay 5.0
```

Порциями по 100 штук (рекомендуется при 403):

```bash
python -m scraper.main scrape --delay 8.0 --limit 100
```

### Повтор после ошибок 403

```bash
python scripts/migrate_errors.py
python -m scraper.main retry-recipes --delay 8.0
python -m scraper.main retry --delay 5.0
```

### Полный цикл одной командой

```bash
python -m scraper.main all --delay 5.0
```

### Экспорт в JSON

```bash
python scripts/export_json.py
```

## Результаты

| Файл | Описание |
|------|----------|
| `data/categories.json` | Категории рецептов |
| `data/recipe_ids.json` | Уникальные ID рецептов |
| `data/recipe_previews.json` | Краткие карточки из списков |
| `data/recipes.jsonl` | Полные рецепты (построчно, можно продолжать) |
| `data/recipes.json` | Все рецепты в одном JSON-файле |
| `data/progress.json` | Прогресс парсинга |

## Возобновление

Парсер сохраняет уже обработанные рецепты в `data/recipes.jsonl`. Повторный запуск `scrape` пропускает уже спарсенные ID.

## Примечания

- Сайт использует кодировку Windows-1251 — парсер обрабатывает её автоматически.
- **Обязательно установите `curl_cffi`** — он лучше обходит Cloudflare, чем обычный `requests`.
- Между запросами выдерживается пауза (по умолчанию ~5 с + случайная добавка).
- При серии 403 парсер автоматически делает паузу 5 минут.
- Сайт защищён Cloudflare: при блокировке IP смените интернет (мобильный хотспот / VPN), подождите 2–4 часа и продолжайте.
- Полный парсинг всех рецептов занимает много часов — запускайте **порциями** (`--limit 100`).
- Парсер поддерживает **возобновление**: уже успешно сохранённые рецепты не скачиваются повторно.
