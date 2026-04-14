#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backup and restore script for Smart Control project.

Usage:
  python backup_project.py backup   - create backup
  python backup_project.py restore  - restore from backup
"""
import os
import shutil
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, '_backup')

FILES_TO_BACKUP = [
    'app/main.py',
    'app/models.py',
    'app/routes.py',
    'app/parser/pdf_engine.py',
    'app/services/districts.py',
    'app/services/notifier.py',
    'app/services/watcher.py',
    'app/services/yandex_disk.py',
    'app/templates/add_task.html',
    'app/templates/dashboard.html',
    'app/templates/index.html',
    'app/templates/leaderboard.html',
    'docker-compose.yml',
    'Dockerfile',
    'requirements.txt',
    '.gitignore',
    'README.md',
    'links.txt',
    'test_local.py',
    'test_new_features.py',
    'test_regex.py',
    'Tools/extract_inside.py',
    'Tools/extract_pdf.py',
    'Tools/test_parser.py',
]


def backup():
    if os.path.exists(BACKUP_DIR):
        shutil.rmtree(BACKUP_DIR)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    backed_up = 0
    errors = 0

    for rel_path in FILES_TO_BACKUP:
        src = os.path.join(BASE_DIR, rel_path)
        dst = os.path.join(BACKUP_DIR, rel_path)

        if not os.path.exists(src):
            print("  [WARN] Not found: " + rel_path)
            continue

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(src, dst)
            size = os.path.getsize(src)
            print("  [OK] " + rel_path + " (" + str(size) + " bytes)")
            backed_up += 1
        except Exception as e:
            print("  [ERR] Copy error " + rel_path + ": " + str(e))
            errors += 1

    meta_path = os.path.join(BACKUP_DIR, '_backup_info.txt')
    with open(meta_path, 'w', encoding='utf-8') as f:
        f.write("Backup created: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n")
        f.write("Files backed up: " + str(backed_up) + "\n")
        f.write("Errors: " + str(errors) + "\n")
        f.write("Base dir: " + BASE_DIR + "\n")

    print("")
    print("=" * 50)
    print("Backup created: " + BACKUP_DIR)
    print("Files backed up: " + str(backed_up))
    print("Errors: " + str(errors))
    print("=" * 50)


def restore():
    if not os.path.exists(BACKUP_DIR):
        print("Error: backup not found in " + BACKUP_DIR)
        print("First run: python backup_project.py backup")
        return

    restored = 0
    errors = 0

    for rel_path in FILES_TO_BACKUP:
        src = os.path.join(BACKUP_DIR, rel_path)
        dst = os.path.join(BASE_DIR, rel_path)

        if not os.path.exists(src):
            print("  [WARN] Not in backup: " + rel_path)
            continue

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(src, dst)
            size = os.path.getsize(dst)
            print("  [OK] " + rel_path + " (" + str(size) + " bytes)")
            restored += 1
        except Exception as e:
            print("  [ERR] Restore error " + rel_path + ": " + str(e))
            errors += 1

    print("")
    print("=" * 50)
    print("Files restored: " + str(restored))
    print("Errors: " + str(errors))
    print("=" * 50)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python backup_project.py backup   - create backup")
        print("  python backup_project.py restore  - restore from backup")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'backup':
        print("Creating backup...")
        backup()
    elif command == 'restore':
        print("Restoring from backup...")
        restore()
    else:
        print("Unknown command: " + command)
        print("Use 'backup' or 'restore'")
        sys.exit(1)


if __name__ == '__main__':
    main()
