#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def migrate_errors(recipes_path: Path, failed_path: Path) -> tuple[int, int]:
    if not recipes_path.exists():
        return 0, 0

    ok_lines: list[str] = []
    failed_lines: list[str] = []
    with recipes_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                failed_lines.append(line)
            else:
                ok_lines.append(line)

    with recipes_path.open("w", encoding="utf-8") as file:
        for line in ok_lines:
            file.write(line + "\n")

    if failed_lines:
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if failed_path.exists():
            existing = {line.strip() for line in failed_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        with failed_path.open("a", encoding="utf-8") as file:
            for line in failed_lines:
                if line not in existing:
                    file.write(line + "\n")

    return len(ok_lines), len(failed_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Убрать ошибки из recipes.jsonl в failed_recipes.jsonl")
    parser.add_argument("--input", type=Path, default=Path("data/recipes.jsonl"))
    parser.add_argument("--failed", type=Path, default=Path("data/failed_recipes.jsonl"))
    args = parser.parse_args()
    ok, failed = migrate_errors(args.input, args.failed)
    print(f"Успешных рецептов: {ok}")
    print(f"Перенесено ошибок: {failed}")


if __name__ == "__main__":
    main()
