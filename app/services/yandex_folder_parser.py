"""
Сервис для парсинга Яндекс.Диск папок районов КЧС.

Использует публичный API Яндекс.Диска для получения списка файлов из публичных папок.
Для работы требуется публичная ссылка на папку.

API:
  GET /api/yandex/refresh — обновить данные всех папок
  GET /api/yandex/district/<id> — данные конкретной папки
"""

import logging
import requests
from datetime import datetime

# Публичный API Яндекс.Диска
YANDEX_PUBLIC_API = "https://cloud-api.yandex.net/v1/disk/public/resources"

logger = logging.getLogger(__name__)


def get_public_key_from_url(url: str) -> str:
    """Извлекает public_key из URL Яндекс.Диска."""
    # Формат: https://disk.yandex.ru/d/XXXXXXXX
    parts = url.rstrip('/').split('/')
    return parts[-1]


def parse_yandex_folder(public_url: str) -> dict:
    """
    Получает информацию о публичной папке Яндекс.Диска.
    
    Возвращает:
        {
            'name': str,           # Имя папки
            'type': str,           # 'dir' или 'file'
            'items': list,         # Список файлов/папок
            'total_items': int,    # Количество элементов
            'fetched_at': str,     # Время получения
        }
    """
    try:
        public_key = get_public_key_from_url(public_url)
        params = {
            'public_key': public_key,
            'limit': 1000,
            'fields': 'name,type,items,_embedded.items'
        }
        
        resp = requests.get(YANDEX_PUBLIC_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        items = data.get('_embedded', {}).get('items', [])
        
        return {
            'name': data.get('name', ''),
            'type': data.get('type', 'dir'),
            'items': [
                {
                    'name': item.get('name', ''),
                    'type': item.get('type', 'file'),
                    'size': item.get('size', 0),
                    'created': item.get('created', ''),
                    'path': item.get('path', ''),
                }
                for item in items
            ],
            'total_items': len(items),
            'fetched_at': datetime.utcnow().isoformat(),
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[YandexParser] Ошибка запроса для {public_url}: {e}")
        return {'error': str(e), 'items': []}
    except Exception as e:
        logger.error(f"[YandexParser] Критическая ошибка для {public_url}: {e}", exc_info=True)
        return {'error': str(e), 'items': []}


def parse_all_districts(districts: list) -> list:
    """
    Парсит все папки районов.
    
    Args:
        districts: список dict с полями 'id', 'name', 'yandex_url'
    
    Returns:
        список результатов парсинга
    """
    results = []
    for district in districts:
        logger.info(f"[YandexParser] Парсинг папки: {district['name']}")
        result = parse_yandex_folder(district['yandex_url'])
        result['district_id'] = district['id']
        result['district_name'] = district['name']
        results.append(result)
    return results
