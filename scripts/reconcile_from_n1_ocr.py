#!/usr/bin/env python3
"""Reconcile the legacy Anki CSV with visually transcribed book examples.

Only fields directly supported by the book transcription are changed. Derived
Chinese translations, generated analyses, and audio are reported for review.
"""

from __future__ import annotations

import argparse
import csv
import html
import itertools
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


EXPECTED_COUNTS = {
    1: [4, 4, 3, 3, 3, 3], 2: [3, 3, 3, 3, 3], 3: [3, 4, 3, 3, 3],
    4: [4, 4, 3, 3], 5: [4, 3, 3, 3, 4], 6: [4, 3, 6, 4, 3],
    7: [3, 3, 3], 8: [3, 4, 4, 5, 3], 9: [3, 3, 3, 5, 3],
    10: [5, 3, 4, 4, 4], 11: [3, 3, 3], 12: [3, 3, 4, 4, 3],
    13: [3, 5, 3, 3, 4, 3], 14: [4, 4, 4, 3, 5], 15: [4, 4, 4],
    16: [4, 3, 3, 4], 17: [4, 4, 3, 4, 3, 3],
}

LEGACY_COUNTS = {lesson: list(counts) for lesson, counts in EXPECTED_COUNTS.items()}
LEGACY_COUNTS[15] = [3, 4, 4]  # The legacy deck omits book lesson 15, grammar 1, example 1.


@dataclass
class GrammarBlock:
    lesson: int
    grammar: str
    meaning: str
    formation: str
    note: str
    examples: list[tuple[str, str, str, int]]  # plain, cloze, source file, line


def plain_markdown(value: str) -> str:
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    return value.strip().lstrip("：: ")


def normalize_grammar(value: str) -> str:
    value = value.replace("〜", "～")
    value = re.sub(r"（続き）$", "", value)
    value = re.sub(r"\s*→.*$", "", value)
    value = value.replace("（に）", "(に)").replace("（は）", "(は)")
    return value.strip()


def grammar_key(value: str) -> str:
    value = normalize_grammar(value).replace("リ", "り")
    return re.sub(r"[～〜・…（）()\s]", "", value).replace("にに", "に")


def remove_cloze(value: str) -> str:
    return re.sub(r"\{\{c1::(.*?)\}\}", r"\1", value)


def render_front(cloze: str) -> str:
    return re.sub(r"\{\{c1::.*?\}\}", "【…】", cloze)


def render_back(cloze: str) -> str:
    def span(match: re.Match[str]) -> str:
        return ('<span class="grammar-highlight" style="background-color: #ffeb3b; '
                'font-weight: bold; padding: 2px 4px; border-radius: 3px; '
                f'color: #333;">{match.group(1)}</span>')
    return re.sub(r"\{\{c1::(.*?)\}\}", span, cloze)


def render_detail_sentence(cloze: str) -> str:
    return re.sub(r"\{\{c1::(.*?)\}\}", r"<b>\1</b>", cloze)


def ensure_cloze(cloze: str, grammar: str) -> str:
    if "{{c1::" in cloze:
        return cloze
    candidates_by_grammar = {
        "～にひきかえ": ["にひきかえ"],
        "～にもまして": ["にもまして"],
        "～ないまでも": ["とはいかないまでも", "とは言わないまでも", "ないまでも"],
        "～に至って・～に至っても": ["に至っても", "に至って"],
        "～に至っては": ["に至っては"],
    }
    for candidate in candidates_by_grammar.get(normalize_grammar(grammar), []):
        if candidate in cloze:
            return cloze.replace(candidate, f"{{{{c1::{candidate}}}}}", 1)
    raise ValueError(f"No cloze range in OCR and no safe inference for {grammar}: {cloze}")


def parse_parts(parts_dir: Path) -> list[GrammarBlock]:
    blocks: list[GrammarBlock] = []
    lesson: int | None = None
    active: GrammarBlock | None = None
    collecting = False
    for path in sorted(parts_dir.glob("*.md")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            lesson_match = re.search(r"(?<!\d)([1-9]|1[0-7])\s*課(?:\s|　)", line)
            if lesson_match and not any(x in line for x in ("页脚", "書内页脚", "ページ下部")):
                lesson = int(lesson_match.group(1))

            heading = re.match(r"^###\s+\d+\s*[　 ]+([～〜].+)$", line)
            if heading and lesson:
                active = GrammarBlock(lesson, normalize_grammar(heading.group(1)), "", "", "", [])
                blocks.append(active)
                collecting = True
                continue
            if not active:
                continue

            field = re.match(r"^(?:[-*]\s*)?(?:\*\*)?(意味|接続|注意)(?:\*\*)?[：:]\s*(.*)$", line)
            if field:
                name, value = field.groups()
                value = plain_markdown(value)
                if name == "意味":
                    active.meaning = value
                elif name == "接続":
                    active.formation = value
                    collecting = False
                else:
                    active.note = value
                continue
            if line.startswith("⇒"):
                active.meaning = line[1:].strip()
                continue
            if not collecting:
                continue

            example = re.match(r"^\s*(?:[-*]\s*)?(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.．])\s*(.+)$", line)
            if example:
                cloze = example.group(1).strip()
                if "（　　　）" not in cloze and "（　）" not in cloze and len(cloze) > 8:
                    active.examples.append((remove_cloze(cloze), cloze, path.name, line_no))

    # The same grammar can continue on the next page; merge adjacent continuation blocks.
    merged: list[GrammarBlock] = []
    for block in blocks:
        if merged and block.lesson == merged[-1].lesson and grammar_key(block.grammar) == grammar_key(merged[-1].grammar):
            merged[-1].examples.extend(block.examples)
            merged[-1].meaning = merged[-1].meaning or block.meaning
            merged[-1].formation = merged[-1].formation or block.formation
            merged[-1].note = merged[-1].note or block.note
        else:
            merged.append(block)
    return merged


def replace_detail_opening(detail: str, cloze: str) -> str:
    opening = f"<p>{render_detail_sentence(cloze)}</p>"
    if re.match(r"<p>.*?</p>", detail, re.DOTALL):
        return re.sub(r"^<p>.*?</p>", opening, detail, count=1, flags=re.DOTALL)
    return opening + detail


def displayed_sentence(row: list[str]) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", row[4]))


def best_assignment(old_sentences: list[str], examples: list[tuple[str, str, str, int]]) -> tuple[list[int], list[int]]:
    """Return OCR indices for legacy rows and unmatched OCR indices."""
    if len(old_sentences) > len(examples):
        raise ValueError("legacy grammar group has more examples than OCR")
    best_score = -1.0
    best_indices: tuple[int, ...] | None = None
    for indices in itertools.permutations(range(len(examples)), len(old_sentences)):
        score = sum(SequenceMatcher(None, old, examples[index][0]).ratio()
                    for old, index in zip(old_sentences, indices))
        if score > best_score:
            best_score = score
            best_indices = indices
    assert best_indices is not None
    unmatched = sorted(set(range(len(examples))) - set(best_indices))
    return list(best_indices), unmatched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-root", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    blocks = parse_parts(args.ocr_root / "output/ocr/parts")
    by_lesson: dict[int, list[GrammarBlock]] = {}
    for block in blocks:
        if block.lesson <= 17 and block.examples:
            by_lesson.setdefault(block.lesson, []).append(block)

    problems: list[str] = []
    for lesson, counts in EXPECTED_COUNTS.items():
        actual = [len(block.examples) for block in by_lesson.get(lesson, [])]
        if actual != counts:
            problems.append(f"第{lesson}課 grammar example counts: expected {counts}, got {actual}")
    if problems:
        raise SystemExit("OCR structure mismatch; refusing to write:\n" + "\n".join(problems))

    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        all_rows = list(csv.reader(handle))
    directives, rows = all_rows[:4], all_rows[4:]
    if len(rows) != 343 or any(len(row) != 22 for row in rows):
        raise SystemExit("Legacy CSV shape changed; refusing to write")

    legacy_by_lesson: dict[int, list[list[str]]] = {}
    for row in rows:
        match = re.fullmatch(r"第(\d+)課 - (\d+)", row[3])
        if match and int(match.group(1)) <= 17:
            legacy_by_lesson.setdefault(int(match.group(1)), []).append(row)

    lookup: dict[tuple[int, int], tuple[GrammarBlock, tuple[str, str, str, int]]] = {}
    missing_examples: list[tuple[int, GrammarBlock, tuple[str, str, str, int]]] = []
    for lesson, lesson_blocks in by_lesson.items():
        legacy_start = 0
        for group_index, block in enumerate(lesson_blocks):
            legacy_count = LEGACY_COUNTS[lesson][group_index]
            legacy_group = legacy_by_lesson[lesson][legacy_start:legacy_start + legacy_count]
            assignments, unmatched = best_assignment([displayed_sentence(row) for row in legacy_group], block.examples)
            for row, example_index in zip(legacy_group, assignments):
                within = int(row[3].split(" - ")[1])
                lookup[(lesson, within)] = (block, block.examples[example_index])
            for example_index in unmatched:
                missing_examples.append((lesson, block, block.examples[example_index]))
            legacy_start += legacy_count

    report_rows: list[list[str]] = []
    changed_cards = 0
    sentence_changes = 0
    for csv_line, row in enumerate(rows, 5):
        key_match = re.fullmatch(r"第(\d+)課 - (\d+)", row[3])
        if not key_match:
            raise SystemExit(f"Invalid card key at CSV line {csv_line}: {row[3]}")
        lesson, within = map(int, key_match.groups())
        if lesson > 17:
            report_rows.append([row[3], str(csv_line), "", "", row[2], "", "", "", "not_scanned", "", "unknown", "n1-ocr ends before lesson 18"])
            continue
        block, (ocr_sentence, cloze, source_file, source_line) = lookup[(lesson, within)]
        cloze = ensure_cloze(cloze, block.grammar)
        old_sentence = displayed_sentence(row)
        old_grammar = row[2]
        new_grammar = block.grammar
        grammar_ok = grammar_key(row[2]) == grammar_key(new_grammar)
        if not grammar_ok:
            similarity = SequenceMatcher(None, grammar_key(row[2]), grammar_key(new_grammar)).ratio()
            if similarity < 0.6:
                raise SystemExit(f"Grammar mismatch at {row[3]}: {row[2]} != {new_grammar}")

        changed_fields: list[str] = []
        replacements = {
            1: render_front(cloze), 2: new_grammar, 4: render_back(cloze),
            8: block.formation or row[8], 9: block.formation or row[9],
            11: block.meaning or row[11], 15: block.note or row[15],
        }
        for field_index, new_value in replacements.items():
            if new_value and row[field_index] != new_value:
                row[field_index] = new_value
                changed_fields.append(str(field_index + 1))
        new_detail = replace_detail_opening(row[18], cloze)
        if row[18] != new_detail:
            row[18] = new_detail
            changed_fields.append("19-opening")

        sentence_changed = old_sentence != ocr_sentence
        if sentence_changed:
            sentence_changes += 1
        if changed_fields:
            changed_cards += 1
        report_rows.append([
            row[3], str(csv_line), source_file, str(source_line), old_grammar, new_grammar,
            old_sentence, ocr_sentence, "corrected" if changed_fields else "exact",
            ";".join(changed_fields), "review_or_rerecord" if sentence_changed else "keep",
            "translation and generated analysis require review" if sentence_changed else "",
        ])

    for lesson, block, (ocr_sentence, _cloze, source_file, source_line) in missing_examples:
        report_rows.append([
            f"第{lesson}課 - MISSING", "", source_file, str(source_line), "", block.grammar,
            "", ocr_sentence, "missing_in_legacy", "", "missing", "create a new card and audio after review",
        ])

    args.report_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = args.report_dir / "reconciliation.csv"
    with mapping_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "legacy_csv_line", "ocr_file", "ocr_line", "old_grammar", "ocr_grammar",
                         "old_sentence", "ocr_sentence", "status", "changed_fields", "audio_action", "notes"])
        writer.writerows(report_rows)

    summary = (
        "# N1 OCR reconciliation summary\n\n"
        f"- OCR-backed legacy cards: 280 (lessons 1–17)\n"
        f"- Book examples missing from the legacy deck: {len(missing_examples)}\n"
        f"- Cards with directly supported field changes: {changed_cards}\n"
        f"- Cards whose Japanese sentence changed: {sentence_changes}\n"
        "- Legacy cards not scanned: 63 (lessons 18–20)\n"
        "- Changed fields: FrontSentence, Grammar, BackSentence, both formation fields, "
        "Japanese meaning, Japanese note, and the opening sentence of DetailedExplanation.\n"
        "- Not automatically changed: Chinese translation, generated analysis body, and MP3 bytes.\n"
        "- Every changed Japanese sentence is marked `review_or_rerecord` in reconciliation.csv.\n"
    )
    (args.report_dir / "README.md").write_text(summary, encoding="utf-8")

    if args.apply:
        with args.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerows(directives + rows)
    print(summary, end="")


if __name__ == "__main__":
    main()
