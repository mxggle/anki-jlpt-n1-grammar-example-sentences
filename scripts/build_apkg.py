#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild JLPT_N1_N1__.apkg from the current notes.csv, preserving note/card
IDs and deck IDs so that importing the new package into Anki updates card
content while keeping scheduling/learning progress intact. The build also
syncs the repository templates, CSS, media, and top-level deck description.

How Anki's apkg importer merges (verified against rslib importer source):
- notes are matched by GUID; when the GUID already exists and the incoming
  note's mtime is newer, only the note fields/tags are updated.
- cards are added only when (note_id, template_ord) does not already exist;
  existing cards are skipped, so their scheduling is preserved untouched.
- therefore this build rewrites note fields/checksums and bumps note mtimes,
  while leaving card scheduling rows untouched. It also refreshes the package's
  note template, CSS, media, and top-level deck description from repository
  sources.

Usage:
  python3 scripts/build_apkg.py [OUTPUT.APKG]

If OUTPUT.APKG is omitted, the default JLPT_N1_N1__.apkg in the repo root is
used as both the source base and the destination.
"""
import csv
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS_CSV = os.path.join(REPO, 'shin-kanzen-n1-grammar/notes.csv')
MEDIAS_DIR = os.path.join(REPO, 'shin-kanzen-n1-grammar/medias')
APKG_PATH = os.path.join(REPO, 'JLPT_N1_N1__.apkg')
DESCRIPTION_PATH = os.path.join(REPO, 'ankiweb-description-simple.html')
FRONT_TEMPLATE = os.path.join(REPO, 'shin-kanzen-n1-grammar/templates/front.html')
BACK_TEMPLATE = os.path.join(REPO, 'shin-kanzen-n1-grammar/templates/back.html')
STYLE_TEMPLATE = os.path.join(REPO, 'shin-kanzen-n1-grammar/templates/style.css')

MODEL_FIELDS = 20


def field_checksum(text):
    """Anki csum: big-endian u32 of the first 4 bytes of SHA-1(utf8 text)."""
    return int.from_bytes(hashlib.sha1(text.encode('utf-8')).digest()[:4], 'big')


def strip_html_preserving_media(text):
    """Mirror of Anki's strip_html_preserving_media_filenames + strip_html."""
    media_re = re.compile(
        r'(?xsi)<\b(?:img|audio|video|object|source)\b'
        r'(?:[^>]|"[^"]+?"|\'[^\']+?\')+?'
        r'\b(?:src|data)\b='
        r'(?:"([^"]+?)"[^>]*>|\'([^\']+?)\'[^>]*>|([^>\s"\'][^>]*?)\s/?>)'
    )
    text = media_re.sub(r' \1\2\3 ', text)
    html_re = re.compile(
        r'(?si)'
        r'(<!--.*?-->)|(<style.*?>.*?</style>)|(<script.*?>.*?</script>)'
        r'|(<.*?>)'
    )
    text = html_re.sub('', text)
    text = html.unescape(text)
    text = text.replace('\xa0', ' ')
    return text


def read_notes_csv(path):
    raw = open(path, encoding='utf-8').read().split('\n')
    i = 0
    while i < len(raw) and raw[i].startswith('#'):
        i += 1
    body = '\n'.join(raw[i:])
    rows = list(csv.reader(__import__('io').StringIO(body)))
    by_sortorder = {}
    for r in rows:
        if not r or not r[0]:
            continue
        if len(r) != 22:
            raise SystemExit(f'row {r[:4]} has {len(r)} columns, expected 22')
        by_sortorder[int(r[20])] = r
    return by_sortorder


def csv_row_to_fields(row):
    return [
        row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8],
        row[9], row[10], row[11], row[12], row[13], row[14], row[15],
        row[16], row[17], row[18], row[19], row[20],
    ]


def build(out_path=None):
    base_path = APKG_PATH
    out_path = os.path.abspath(out_path or APKG_PATH)
    if out_path != base_path and not os.path.exists(base_path):
        raise SystemExit(f'source apkg not found: {base_path}')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='anki-apkg-build-') as work_dir:
        with zipfile.ZipFile(base_path) as z:
            unsafe = [name for name in z.namelist() if name not in {'meta', 'collection.anki2', 'collection.anki21', 'media'} and not name.isdigit()]
            if unsafe:
                raise SystemExit(f'unexpected or unsafe archive members: {unsafe[:5]}')
            z.extractall(work_dir)

        db_path = os.path.join(work_dir, 'collection.anki21')
        db = sqlite3.connect(db_path)
        cur = db.cursor()

        csv_by_sort = read_notes_csv(CARDS_CSV)
        if len(csv_by_sort) != 343:
            raise SystemExit(f'expected 343 csv rows, got {len(csv_by_sort)}')

        notes = cur.execute('SELECT id, flds, csum FROM notes ORDER BY id').fetchall()
        if len(notes) != 343:
            raise SystemExit(f'expected 343 notes, got {len(notes)}')

        now_secs = int(time.time())
        now_ms = now_secs * 1000
        updated = 0
        mismatches = []

        for nid, flds, csum in notes:
            fields = flds.split('\x1f')
            if len(fields) != MODEL_FIELDS:
                raise SystemExit(f'note {nid} has {len(fields)} fields')
            sort = int(fields[19])
            row = csv_by_sort[sort]

            if row[3].strip() != fields[2]:
                mismatches.append((nid, 'lessoninfo', fields[2], row[3]))
            if row[20] != str(sort):
                mismatches.append((nid, 'sortorder', fields[19], row[20]))

            new_fields = csv_row_to_fields(row)
            new_flds = '\x1f'.join(new_fields)
            new_csum = field_checksum(strip_html_preserving_media(new_fields[0]))
            cur.execute(
                'UPDATE notes SET flds=?, csum=?, mod=? WHERE id=?',
                (new_flds, new_csum, now_secs, nid),
            )
            updated += 1

        if mismatches:
            for m in mismatches[:20]:
                print('MISMATCH', m)
            raise SystemExit(f'{len(mismatches)} identity mismatches between csv and db')

        decks_json, models_json = cur.execute('SELECT decks, models FROM col WHERE id=1').fetchone()
        decks = json.loads(decks_json)
        models = json.loads(models_json)
        description = open(DESCRIPTION_PATH, encoding='utf-8').read().strip()
        top_decks = [deck for deck in decks.values() if deck['name'] == '新完全掌握N1语法例句']
        if len(top_decks) != 1:
            raise SystemExit(f'expected one top-level deck, got {len(top_decks)}')
        top_decks[0]['desc'] = description
        top_decks[0]['mod'] = now_secs

        if len(models) != 1:
            raise SystemExit(f'expected one note type, got {len(models)}')
        model = next(iter(models.values()))
        if len(model.get('tmpls', [])) != 1:
            raise SystemExit('expected one card template')
        model['tmpls'][0]['qfmt'] = open(FRONT_TEMPLATE, encoding='utf-8').read()
        model['tmpls'][0]['afmt'] = open(BACK_TEMPLATE, encoding='utf-8').read()
        model['css'] = open(STYLE_TEMPLATE, encoding='utf-8').read()
        model['mod'] = now_secs

        cur.execute(
            'UPDATE col SET mod=?, scm=?, decks=?, models=? WHERE id=1',
            (now_ms, now_ms, json.dumps(decks, ensure_ascii=False), json.dumps(models, ensure_ascii=False)),
        )
        db.commit()

        # verify recomputed csums round-trip (read rows first, then check)
        rows_after = db.execute('SELECT id, flds, csum FROM notes ORDER BY id').fetchall()
        db.close()
        ok = 0
        for nid, flds, stored in rows_after:
            f = flds.split('\x1f')
            calc = field_checksum(strip_html_preserving_media(f[0]))
            if calc == stored:
                ok += 1
            else:
                print('CSUM MISMATCH', nid)
        if ok != len(rows_after):
            raise SystemExit(f'csum verification failed: {ok}/{len(rows_after)}')
        print(f'notes updated: {updated}/{len(notes)}, csum verified: {ok}/{len(notes)}')

        # copy media files from repo (matched by filename via the media index)
        media_map = json.load(open(os.path.join(work_dir, 'media'), encoding='utf-8'))
        missing = []
        for key, fname in media_map.items():
            if os.path.basename(fname) != fname:
                raise SystemExit(f'unsafe media filename in package: {fname!r}')
            src = os.path.join(MEDIAS_DIR, fname)
            if not os.path.exists(src):
                missing.append(fname)
                continue
            shutil.copy(src, os.path.join(work_dir, key))
        if missing:
            raise SystemExit(f'{len(missing)} media files missing in repo: {missing[:5]}')
        print(f'media copied: {len(media_map)}')

        # Repack atomically. A failed build never corrupts the previous package.
        fd, temp_out = tempfile.mkstemp(prefix='.apkg-', suffix='.tmp', dir=os.path.dirname(out_path))
        os.close(fd)
        try:
            with zipfile.ZipFile(temp_out, 'w', zipfile.ZIP_DEFLATED) as z:
                stored = {'meta', 'collection.anki2', 'media'}
                for name in sorted(os.listdir(work_dir)):
                    if name == 'collection.anki21':
                        z.write(os.path.join(work_dir, name), name, zipfile.ZIP_DEFLATED)
                    elif name in stored or name.isdigit():
                        z.write(os.path.join(work_dir, name), name, zipfile.ZIP_STORED)
                    else:
                        z.write(os.path.join(work_dir, name), name, zipfile.ZIP_DEFLATED)
            os.replace(temp_out, out_path)
            os.chmod(out_path, 0o644)
        finally:
            if os.path.exists(temp_out):
                os.unlink(temp_out)
    print(f'wrote {out_path}')


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else None)
