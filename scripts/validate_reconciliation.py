#!/usr/bin/env python3
"""Validate the reconciled Anki CSV and its audit report."""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "shin-kanzen-n1-grammar/notes.csv"
MEDIA_DIR = ROOT / "shin-kanzen-n1-grammar/medias"
REPORT_PATH = ROOT / "reconciliation/reconciliation.csv"


def visible(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value))


def main() -> None:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    expected_directives = [["#separator:comma"], ["#html:true"], ["#deck column:1"], ["#tags column:22"]]
    assert rows[:4] == expected_directives
    cards = rows[4:]
    assert len(cards) == 343
    assert all(len(card) == 22 for card in cards)

    keys: list[str] = []
    for csv_line, card in enumerate(cards, 5):
        key = re.fullmatch(r"第(\d+)課 - (\d+)", card[3])
        assert key, f"invalid card key at CSV line {csv_line}: {card[3]}"
        keys.append(card[3])
        audio_match = re.fullmatch(r"\[sound:(.+)]", card[7])
        assert audio_match and (MEDIA_DIR / audio_match.group(1)).exists(), f"missing audio at CSV line {csv_line}"
        if int(key.group(1)) <= 17:
            assert "【…】" in card[1], f"missing front blank at CSV line {csv_line}"
            assert "grammar-highlight" in card[4], f"missing back highlight at CSV line {csv_line}"
            opening = re.match(r"<p>(.*?)</p>", card[18], re.DOTALL)
            assert opening, f"missing detail opening at CSV line {csv_line}"
            assert visible(card[4]) == visible(opening.group(1)), f"detail opening mismatch at CSV line {csv_line}"
    assert len(keys) == len(set(keys)), "duplicate card keys"

    with REPORT_PATH.open(encoding="utf-8", newline="") as handle:
        report = list(csv.DictReader(handle))
    assert len(report) == 344
    assert sum(row["status"] == "corrected" for row in report) == 343
    assert sum(row["status"] == "not_scanned" for row in report) == 0
    assert sum(row["status"] == "missing_in_legacy" for row in report) == 1
    print(f"VALIDATION PASSED: {len(cards)} cards, {len(report)} reconciliation rows, {len(list(MEDIA_DIR.glob('*.mp3')))} MP3 files")


if __name__ == "__main__":
    main()
