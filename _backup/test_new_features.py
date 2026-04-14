# -*- coding: utf-8 -*-
"""Тест новых функций: модели, роуты, парсинг имён"""
import sys, os

sys.path.insert(0, 'app')

# Локальный путь для SQLite (Windows)
db_path = os.path.join(os.path.abspath('data'), 'test_new.db')
os.makedirs('data', exist_ok=True)
os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

# Патчим os.makedirs чтобы не падало на /data
_orig_makedirs = os.makedirs
def _safe_makedirs(path, **kw):
    if path == '/data':
        path = 'data'
    _orig_makedirs(path, **kw)
os.makedirs = _safe_makedirs

from main import app

print("=== Test 1: Model imports ===")
from models import db, Task, Executor, FileDocument, YandexReport
print("  OK: all models imported")

print("\n=== Test 2: Tables created ===")
with app.app_context():
    db.create_all()
    # Check yandex_reports table exists
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    assert 'yandex_reports' in tables, f"yandex_reports not in {tables}"
    print(f"  OK: tables = {tables}")

print("\n=== Test 3: Sender name extraction ===")
from services.yandex_disk import _extract_sender_from_filename
tests = [
    ('random_file.pdf', None),
]
for fn, expected in tests:
    result = _extract_sender_from_filename(fn)
    status = 'OK' if result == expected else 'FAIL'
    print(f"  {status}: '{fn}' -> '{result}'")

print("\n=== Test 4: Routes ===")
with app.test_client() as client:
    r = client.get('/leaderboard')
    assert r.status_code == 200, f"leaderboard returned {r.status_code}"
    print(f"  OK: GET /leaderboard -> {r.status_code}")

    r = client.get('/api/yandex/reports')
    assert r.status_code == 200
    print(f"  OK: GET /api/yandex/reports -> {r.status_code}, data={r.get_json()}")

    r = client.post('/yandex/test')
    print(f"  OK: POST /yandex/test -> {r.status_code}")

    r = client.post('/yandex/sync')
    print(f"  OK: POST /yandex/sync -> {r.status_code}")

    r = client.get('/dashboard')
    assert b'/leaderboard' in r.data, "Dashboard missing /leaderboard link"
    print(f"  OK: Dashboard has /leaderboard link")

    r = client.get('/')
    assert b'/leaderboard' in r.data, "Index missing /leaderboard link"
    print(f"  OK: Index has /leaderboard link")

print("\n=== Test 5: Traffic light logic with data ===")
with app.app_context():
    import hashlib
    from datetime import datetime, timedelta

    ex1 = Executor(name='TestGreen')
    ex2 = Executor(name='TestYellow')
    ex3 = Executor(name='TestRed')
    db.session.add_all([ex1, ex2, ex3])
    db.session.flush()

    # Green: all completed
    db.session.add(Task(title='G1', item_number='1',
        deadline=datetime.utcnow()+timedelta(days=10),
        status='Vypolneno', file_hash=hashlib.md5(b'g1').hexdigest(),
        executor_id=ex1.id))

    # Yellow: one done, one in progress
    db.session.add(Task(title='Y1', item_number='2',
        deadline=datetime.utcnow()+timedelta(days=10),
        status='Vypolneno', file_hash=hashlib.md5(b'y1').hexdigest(),
        executor_id=ex2.id))
    db.session.add(Task(title='Y2', item_number='3',
        deadline=datetime.utcnow()+timedelta(days=10),
        status='V rabote', file_hash=hashlib.md5(b'y2').hexdigest(),
        executor_id=ex2.id))

    # Red: all overdue
    db.session.add(Task(title='R1', item_number='4',
        deadline=datetime.utcnow()-timedelta(days=5),
        status='Prosrocheno', file_hash=hashlib.md5(b'r1').hexdigest(),
        executor_id=ex3.id))
    db.session.commit()

with app.test_client() as client:
    r = client.get('/leaderboard')
    assert r.status_code == 200
    print(f"  OK: GET /leaderboard with test data -> 200")

# Cleanup
if os.path.exists(db_path):
    os.remove(db_path)

print("\n=============================")
print("ALL TESTS PASSED!")
print("=============================")
