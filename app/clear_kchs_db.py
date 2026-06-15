#!/usr/bin/env python3
"""Очистка всех данных КЧС: поручения, протоколы, отчёты с Яндекс.Диска."""
import sys

from main import app
from services.kchs_maintenance import clear_kchs_database


def clear_kchs():
    with app.app_context():
        result = clear_kchs_database()
        print("До очистки:", result["before"])
        print("После очистки:", result["after"])
        print("Готово. Настройки уведомлений сохранены.")


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        print("Подтвердите: python clear_kchs_db.py --yes")
        sys.exit(1)
    clear_kchs()
