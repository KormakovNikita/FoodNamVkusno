#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def export_jsonl_to_json(jsonl_path: Path, json_path: Path) -> int:
    records = []
    with jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Экспорт recipes.jsonl в recipes.json")
    parser.add_argument("--input", type=Path, default=Path("data/recipes.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/recipes.json"))
    args = parser.parse_args()
    count = export_jsonl_to_json(args.input, args.output)
    print(f"Экспортировано рецептов: {count}")


if __name__ == "__main__":
    main()
