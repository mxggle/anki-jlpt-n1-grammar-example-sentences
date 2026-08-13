#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers to read/write the Anki notes.csv for the N1 grammar deck project.

notes.csv = Anki export. First 4 lines are `#` directives. Data from line 5.
22 comma-separated columns. HTML fields may contain quoted values (Anki doubles
inner double-quotes). This module round-trips rows reliably using csv.reader
and csv.writer with the SAME dialect Anki uses:
  - comment rows (starting with #) preserved verbatim
  - data rows quoted with '"' when they contain delimiter/quote/newline
  - Anki escapes a literal quote as two quotes inside a quoted field
"""
import csv, io, re

HEADER_LINES = 4
# 0-based indexes of the fields of interest
COL_TRANSLATION = 6      # col7 中文翻译
COL_DETAIL = 18          # col19 DetailedExplanation (big HTML)


def read_rows(path):
    """Return (header_lines:list[str], rows:list[list])"""
    raw = open(path, encoding='utf-8').read().split('\n')
    header = []
    i = 0
    while i < len(raw) and raw[i].startswith('#'):
        header.append(raw[i]); i += 1
    # join remaining raw lines back (rows may span multiple lines if quoted newlines)
    body = '\n'.join(raw[i:])
    rows = list(csv.reader(io.StringIO(body)))
    return header, rows


def write_rows(path, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
    for r in rows:
        w.writerow(r)
    out = '\n'.join(header) + '\n' + buf.getvalue()
    # Anki style: it writes bare rows with doubled quotes inside quoted fields;
    # csv.writer already handles quotes. Trim a trailing final newline cleanly.
    out = out.rstrip('\n') + '\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(out)


def strip_html(s):
    return re.sub(r'<[^>]+>', ' ', s)


def by_lesson(rows):
    """Map lessoninfo -> row for all data rows."""
    m = {}
    for r in rows:
        if not r or not r[0]:
            continue
        li = r[3].strip()
        m[li] = r
    return m
