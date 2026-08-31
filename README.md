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
python -m scraper.main ids --delay 2.0 --timeout 90 --mode fresh
python -m scraper.main scrape --delay 1.5
```

## Сбор ID (важно)

Сайт использует **JavaScript-пагинацию**: обычные URL `/recipes/2/` возвращают те же 15 рецептов, что и страница 1. Парсер автоматически использует AJAX-эндпоинт `/recipes/~2/?mode=load`.

**Если у вас уже есть `data/recipe_ids.json` с ~16 ID после старого запуска — удалите его и `data/progress.json`, затем соберите ID заново.**

Рекомендуется общий каталог:

```bash
python -m scraper.main ids --delay 2.0 --timeout 90 --mode fresh
```

Ожидаемый результат: ~157 000 уникальных ID за ~10 000 страниц (~12 часов при delay 2.0).

Тест (20 страниц ≈ 300 ID):

```bash
python -m scraper.main ids --delay 2.0 --max-pages 20
```

Альтернатива — перебор ID напрямую (медленнее, ~3 суток):

```bash
python -m scraper.main ids --mode scan --delay 1.5 --start-id 1 --end-id 185000
```

После прерывания — запустите ту же команду снова (продолжит с сохранённой позиции).

## Скорость скачивания

157 000 рецептов в **1 потоке** при `--delay 3.0` — это **~7 суток**. Ускорение:

| Настройки | Скорость | ~Время на 157k |
|-----------|----------|----------------|
| `--delay 3.0` (1 поток) | ~0.3 рец/сек | ~7 суток |
| `--delay 2.0 --workers 3` | ~1.5 рец/сек | ~1–1.5 суток |
| `--delay 1.5 --workers 4` | ~2.5 рец/сек | ~18 часов |

**Рекомендуемая команда:**

```bash
python -m scraper.main scrape --delay 2.0 --timeout 90 --workers 3
```

Тест (100 рецептов):

```bash
python -m scraper.main scrape --delay 2.0 --workers 3 --limit 100
```

Если много ошибок 403 — уменьшите `--workers` до 2 или увеличьте `--delay`.

## Порционный режим

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
