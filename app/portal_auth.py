"""Общий middleware авторизации для всех бэкенд-сервисов портала.

Этот файл копируется в каждый Flask-сервис (flask-app, task-app, task_on_day).
Он читает заголовки X-User-Id / X-User-Role, установленные Nginx после auth_request,
и проверяет права пользователя на конкретный модуль через таблицу user_permissions в PostgreSQL.

Использование:
    from portal_auth import require_read, require_write, require_admin, get_current_user

    @app.route('/api/upload', methods=['POST'])
    @require_write('fuel')
    def upload_file():
        user = get_current_user()  # {'user_id': 1, 'role': 'admin', 'username': 'admin'}
        ...
"""
import os
import logging
from functools import wraps
from flask import request, jsonify, g, render_template, make_response

logger = logging.getLogger('portal_auth')

# В prod всегда false. true — только для локальной отладки без nginx.
DEV_AUTH_BYPASS = os.getenv('PORTAL_AUTH_DEV_BYPASS', 'false').lower() in ('1', 'true', 'yes')

# ── Подключение к БД для проверки прав ──
_db_url = None


def _get_db_url():
    global _db_url
    if _db_url is None:
        _db_url = os.getenv('DATABASE_URL', '')
    return _db_url


def _check_permission(user_id, module, permission_type='can_read'):
    """Проверить права пользователя на модуль через PostgreSQL.

    Args:
        user_id: ID пользователя
        module: Название модуля (fuel, reserves, tasks, fire, flood, planner)
        permission_type: 'can_read', 'can_write' или 'can_admin'

    Returns:
        bool: True если есть права
    """
    db_url = _get_db_url()
    if not db_url:
        logger.warning('DATABASE_URL не задан — пропускаем проверку прав')
        return True

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            f'SELECT {permission_type} FROM user_permissions WHERE user_id = %s AND module = %s',
            (user_id, module)
        )
        row = cur.fetchone()
        conn.close()
        return bool(row and row[0])
    except Exception as e:
        logger.error(f'Ошибка проверки прав: {e}')
        return False


def get_current_user():
    """Получить данные текущего пользователя из заголовков Nginx.

    Nginx устанавливает эти заголовки после auth_request к auth-service.
    """
    if hasattr(g, '_portal_user'):
        return g._portal_user

    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role', 'viewer')
    user_name = request.headers.get('X-User-Name', '')

    if not user_id:
        return None

    g._portal_user = {
        'user_id': int(user_id),
        'role': user_role,
        'username': user_name,
    }
    return g._portal_user


def _wants_json_response():
    path = request.path or ''
    if '/api/' in path:
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes
    return accept['application/json'] >= accept['text/html'] and accept['application/json'] > 0


def _forbidden_response(error_msg, module, permission_type):
    if _wants_json_response():
        return jsonify({
            'error': error_msg,
            'module': module,
            'required': permission_type,
        }), 403

    landing_403 = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'landing', '403.html')
    )
    if os.path.isfile(landing_403):
        with open(landing_403, encoding='utf-8') as fh:
            return make_response(fh.read(), 403, {'Content-Type': 'text/html; charset=utf-8'})

    return make_response(render_template('forbidden.html'), 403)


def _require_permission(module, permission_type, error_msg):
    """Фабрика декораторов для проверки прав."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()

            if not user:
                if DEV_AUTH_BYPASS:
                    logger.debug('Нет X-User-Id — PORTAL_AUTH_DEV_BYPASS включён')
                    return f(*args, **kwargs)
                logger.warning('Запрос без авторизации: %s %s', request.method, request.path)
                return _forbidden_response('Требуется авторизация', module, permission_type)

            # Admin всегда имеет полный доступ
            if user['role'] == 'admin':
                return f(*args, **kwargs)

            # Проверяем права в БД
            if not _check_permission(user['user_id'], module, permission_type):
                return _forbidden_response(error_msg, module, permission_type)

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_read(module):
    """Декоратор: требуется право на чтение модуля.

    @require_read('fuel')
    def get_companies(): ...
    """
    return _require_permission(module, 'can_read', 'Нет доступа на чтение этого раздела')


def require_write(module):
    """Декоратор: требуется право на запись/загрузку в модуле.

    @require_write('fuel')
    def upload_file(): ...
    """
    return _require_permission(module, 'can_write', 'Нет доступа на изменение данных в этом разделе')


def require_admin(module):
    """Декоратор: требуется право на администрирование модуля.

    @require_admin('tasks')
    def delete_all_tasks(): ...
    """
    return _require_permission(module, 'can_admin', 'Нет административного доступа к этому разделу')
