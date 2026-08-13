#!/usr/bin/env python3
"""Verify release metadata, source data, audio, and an optional APKG artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
CSV_PATH = ROOT / "shin-kanzen-n1-grammar/notes.csv"
MEDIA_DIR = ROOT / "shin-kanzen-n1-grammar/medias"
SIMPLE_DESCRIPTION = ROOT / "ankiweb-description-simple.html"
FULL_DESCRIPTION = ROOT / "ankiweb-description.html"


def data_rows() -> list[list[str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.reader(handle) if row and not row[0].startswith("#")]


def verify_sources() -> None:
    rows = data_rows()
    assert len(rows) == 343, f"expected 343 cards, got {len(rows)}"
    assert all(len(row) == 22 for row in rows), "every CSV row must have 22 columns"
    simple = SIMPLE_DESCRIPTION.read_text(encoding="utf-8")
    full = FULL_DESCRIPTION.read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name, text in {
        "simple description": simple,
        "full description": full,
        "changelog": changelog,
        "README": readme,
    }.items():
        assert f"v{VERSION}" in text or f"[{VERSION}]" in text, f"{name} does not contain {VERSION}"

    referenced = {row[7][7:-1] for row in rows if row[7].startswith("[sound:") and row[7].endswith("]")}
    media = {path.name for path in MEDIA_DIR.glob("*.mp3")}
    assert len(referenced) == 343, f"expected 343 audio references, got {len(referenced)}"
    assert media == referenced, f"media mismatch: missing={sorted(referenced-media)[:3]}, extra={sorted(media-referenced)[:3]}"
    assert all((MEDIA_DIR / name).stat().st_size > 0 for name in media), "zero-byte MP3 found"
    print(f"sources verified: v{VERSION}, {len(rows)} cards, {len(media)} MP3 files")


def verify_apkg(path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="verify-apkg-") as work:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            assert "collection.anki21" in names and "media" in names
            archive.extract("collection.anki21", work)
            media_map = json.loads(archive.read("media"))
            for key, filename in media_map.items():
                assert key.isdigit() and Path(filename).name == filename, f"unsafe APKG media mapping: {key!r} -> {filename!r}"
                source_hash = hashlib.sha256((MEDIA_DIR / filename).read_bytes()).digest()
                package_hash = hashlib.sha256(archive.read(key)).digest()
                assert source_hash == package_hash, f"APKG media differs from source: {filename}"
        db = sqlite3.connect(Path(work) / "collection.anki21")
        notes = db.execute("SELECT count(*) FROM notes").fetchone()[0]
        cards = db.execute("SELECT count(*) FROM cards").fetchone()[0]
        note_rows = db.execute("SELECT flds FROM notes").fetchall()
        decks_json, models_json = db.execute("SELECT decks, models FROM col WHERE id=1").fetchone()
        db.close()
        decks = json.loads(decks_json)
        models = json.loads(models_json)
        top = [deck for deck in decks.values() if deck["name"] == "新完全掌握N1语法例句"]
        expected_desc = SIMPLE_DESCRIPTION.read_text(encoding="utf-8").strip()
        assert len(top) == 1 and top[0]["desc"] == expected_desc, "APKG deck description mismatch"
        assert len(models) == 1
        model = next(iter(models.values()))
        assert len(model["tmpls"]) == 1
        assert model["tmpls"][0]["qfmt"] == (ROOT / "shin-kanzen-n1-grammar/templates/front.html").read_text(encoding="utf-8")
        assert model["tmpls"][0]["afmt"] == (ROOT / "shin-kanzen-n1-grammar/templates/back.html").read_text(encoding="utf-8")
        assert model["css"] == (ROOT / "shin-kanzen-n1-grammar/templates/style.css").read_text(encoding="utf-8")
        assert notes == cards == 343, f"APKG count mismatch: notes={notes}, cards={cards}"
        assert len(media_map) == 343, f"APKG media count mismatch: {len(media_map)}"
        expected_fields = {row[20]: "\x1f".join(row[1:21]) for row in data_rows()}
        actual_fields = {flds.split("\x1f")[19]: flds for (flds,) in note_rows}
        assert actual_fields == expected_fields, "APKG note fields differ from notes.csv"
        print(f"APKG verified: {path} ({notes} notes/cards, {len(media_map)} media)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apkg", type=Path)
    args = parser.parse_args()
    verify_sources()
    if args.apkg:
        verify_apkg(args.apkg.resolve())


if __name__ == "__main__":
    main()
