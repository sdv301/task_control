#!/usr/bin/env python3
"""Test KCHS protocol + response PDFs. Run in container:
  docker compose exec task-app python /data/test_kchs_samples.py
"""
import json
import os
import sys

sys.path.insert(0, '/app')

from pdf_parser.pdf_engine import parse_pdf, _extract_text_best, _score_extracted_text
from services.yandex_disk import (
    _extract_pdf_text,
    _parse_response_metadata,
    _extract_report_sections,
    _task_matches_report,
)

SAMPLES_DIR = os.environ.get('KCHS_SAMPLES', '/samples')

PROTOCOL = os.path.join(SAMPLES_DIR, 'кчс 13 от 04.03.2026.pdf')
RESPONSE = os.path.join(SAMPLES_DIR, 'КЧС 13ответ .pdf')


def _deadline_str(dt):
    if not dt:
        return '—'
    if dt.year >= 2099:
        return 'не указан'
    return dt.strftime('%d.%m.%Y')


def test_protocol(path):
    print('=' * 60)
    print('PROTOCOL:', path)
    if not os.path.isfile(path):
        print('  MISSING')
        return None

    with open(path, 'rb') as f:
        raw = f.read()

    text = _extract_text_best(raw)
    print(f'  text length: {len(text)}, score: {_score_extracted_text(text)}')
    print(f'  doc header snippet: {text[:200].replace(chr(10), " ")!r}...')

    result = parse_pdf(file_bytes=raw, filename=os.path.basename(path))
    if not result:
        print('  PARSE FAILED')
        return None

    tasks = result.get('tasks', [])
    print(f'  doc_number: {result.get("doc_number")}')
    print(f'  doc_date: {result.get("doc_date")}')
    print(f'  total tasks: {len(tasks)}')

    from collections import Counter
    by_item = Counter(t.get('item_number', '?') for t in tasks)
    print('  by item_number:')
    for k in sorted(by_item.keys(), key=lambda x: (len(x.split('.')), x)):
        print(f'    {k}: {by_item[k]}')

    print('  sample tasks:')
    for t in tasks[:8]:
        print(f'    {t.get("item_number")} | {_deadline_str(t.get("deadline"))} | {t.get("executor", "")[:45]}')
        print(f'      {t.get("title", "")[:70]}')

    item_41 = [t for t in tasks if str(t.get('item_number', '')).startswith('4.1')]
    print(f'  item 4.1 tasks: {len(item_41)} (expect ~36 districts)')
    if item_41:
        print(f'    deadline 4.1: {_deadline_str(item_41[0].get("deadline"))} (expect 20.03.2026)')
        print(f'    executors sample: {[t["executor"][:25] for t in item_41[:3]]}')

    return result


def test_response(path, protocol_tasks=None):
    print('=' * 60)
    print('RESPONSE:', path)
    if not os.path.isfile(path):
        print('  MISSING')
        return

    with open(path, 'rb') as f:
        raw = f.read()

    text = _extract_pdf_text(raw, use_ocr=True)
    print(f'  extracted text length: {len(text or "")}')
    if text:
        print(f'  snippet: {text[:300].replace(chr(10), " ")!r}')

    meta = _parse_response_metadata(os.path.basename(path), text or '')
    print(f'  kchs_number: {meta.get("kchs_number")}')
    print(f'  kchs_date: {meta.get("kchs_date")}')
    print(f'  item_numbers: {sorted(meta.get("item_numbers") or [])}')
    sections = meta.get('sections') or []
    print(f'  sections: {len(sections)}')
    for s in sections[:6]:
        print(f'    {s.get("item_number")}: {s.get("title", "")[:60]} deadline={s.get("deadline", "—")}')

    if protocol_tasks:
        print('  match against protocol tasks:')
        matched = 0
        for t in protocol_tasks[:20]:
            class FakeTask:
                pass
            ft = FakeTask()
            ft.item_number = t.get('item_number')
            ft.title = t.get('title')
            ft.text = t.get('text')
            ok, reason = _task_matches_report(
                ft, meta.get('item_numbers') or set(), sections
            )
            if ok:
                matched += 1
                print(f'    OK {ft.item_number}: {reason}')
        print(f'  matched {matched} / {min(20, len(protocol_tasks))} (first 20)')


if __name__ == '__main__':
    proto = test_protocol(PROTOCOL)
    tasks = proto.get('tasks', []) if proto else None
    test_response(RESPONSE, tasks)
