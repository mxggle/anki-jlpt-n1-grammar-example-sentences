#!/usr/bin/env python3
"""Regenerate all example-sentence audio for shin-kanzen-n1-grammar via the local VOICEVOX engine.

Usage:
    python3 scripts/gen_audio_voicevox.py [--speaker 23] [--workers 4] [--dry-run]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "shin-kanzen-n1-grammar/notes.csv"
MEDIA_DIR = ROOT / "shin-kanzen-n1-grammar/medias"
ENGINE_URL = "http://127.0.0.1:50021"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def card_text(card: list[str]) -> str:
    return strip_html(card[4])


def card_audio_name(card: list[str]) -> str:
    m = re.fullmatch(r"\[sound:(.+\.mp3)]", card[7])
    assert m, f"bad audio field: {card[7]!r}"
    return m.group(1)


def safe_media_path(name: str) -> Path:
    """Resolve a CSV media reference without allowing path traversal."""
    if Path(name).name != name:
        raise ValueError(f"unsafe audio filename: {name!r}")
    return MEDIA_DIR / name


def synth_one(speaker: int, text: str, out_wav: Path, timeout: int = 180) -> None:
    query_url = f"{ENGINE_URL}/audio_query?speaker={speaker}&text={urllib.parse.quote(text)}"
    req = urllib.request.Request(query_url, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        query = json.loads(resp.read().decode("utf-8"))
    synth_url = f"{ENGINE_URL}/synthesis?speaker={speaker}"
    data = json.dumps(query).encode("utf-8")
    req = urllib.request.Request(
        synth_url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out_wav.write_bytes(resp.read())


def to_mp3(wav: Path, mp3: Path) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(wav),
         "-codec:a", "libmp3lame", "-b:a", "64k", "-ar", "24000", "-ac", "1", str(mp3)],
        check=True,
    )


def process_card(args: tuple[list[str], int, int]) -> tuple[str, bool]:
    card, speaker, idx = args
    name = card_audio_name(card)
    text = card_text(card)
    out = safe_media_path(name)
    tmp_wav: Path | None = None
    tmp_mp3: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_wav = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".mp3", dir=MEDIA_DIR, delete=False) as f:
            tmp_mp3 = Path(f.name)
        synth_one(speaker, text, tmp_wav)
        to_mp3(tmp_wav, tmp_mp3)
        tmp_mp3.replace(out)
        tmp_wav.unlink(missing_ok=True)
        return name, True
    except Exception as exc:  # noqa: BLE001
        try:
            if tmp_wav:
                tmp_wav.unlink(missing_ok=True)
            if tmp_mp3:
                tmp_mp3.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return name, False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", type=int, default=23, help="VOICEVOX speaker id (WhiteCUL ノーマル = 23)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.reader(handle) if r and not r[0].startswith("#")]
    tasks = [(card, args.speaker, i) for i, card in enumerate(rows)]
    if args.limit is not None:
        tasks = tasks[: args.limit]
    if args.dry_run:
        for card, _, _ in tasks:
            print(f"{card_audio_name(card)}\t{card_text(card)}")
        return 0

    print(f"Regenerating {len(tasks)} audio files (speaker={args.speaker}, workers={args.workers}) into {MEDIA_DIR}")
    t0 = time.time()
    ok = 0
    failed: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_card, t): t[0] for t in tasks}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            name, success = fut.result()
            ok += success
            if not success:
                failed.append(name)
            if i % 20 == 0 or not success:
                print(f"[{i}/{len(tasks)}] ok={ok} failed={len(failed)} elapsed={time.time()-t0:.0f}s")
    print(f"DONE: {ok}/{len(tasks)} ok, {len(failed)} failed in {time.time()-t0:.0f}s")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
