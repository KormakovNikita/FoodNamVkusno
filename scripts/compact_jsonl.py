#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compact_jsonl(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0

    valid: list[dict] = []
    errors = 0
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                errors += 1
                continue
            valid.append(record)

    with path.open("w", encoding="utf-8") as file:
        for record in valid:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    return len(valid), errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Удалить ошибочные записи из recipes.jsonl")
    parser.add_argument("--input", type=Path, default=Path("data/recipes.jsonl"))
    args = parser.parse_args()
    valid, errors = compact_jsonl(args.input)
    print(f"Оставлено успешных: {valid}, удалено ошибок: {errors}")


if __name__ == "__main__":
    main()
