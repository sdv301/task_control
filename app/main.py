import os
import platform
from flask import Flask
from routes import main
from models import db
from werkzeug.middleware.proxy_fix import ProxyFix

# Базовые пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))

app = Flask(__name__,
            static_url_path='/task/static') # For browser links

# Enable ProxyFix (x_prefix=0 because we use url_prefix)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=0)

# Database config
_default_db = os.environ.get('DATABASE_URL')
if not _default_db:
    db_path = os.path.join(DATA_DIR, 'tasks.db').replace('\\', '/')
    _default_db = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_DATABASE_URI'] = _default_db
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'dev-secret'

db.init_app(app)

# Register Blueprint with explicit prefix
app.register_blueprint(main, url_prefix='/task')

with app.app_context():
    try:
        db.create_all()
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        migrations = []
        if 'yandex_reports' in inspector.get_table_names():
            existing_cols = {col['name'] for col in inspector.get_columns('yandex_reports')}
            if 'kchs_number' not in existing_cols:
                migrations.append("ALTER TABLE yandex_reports ADD COLUMN kchs_number VARCHAR(50)")
            if 'parsed_item_numbers' not in existing_cols:
                migrations.append("ALTER TABLE yandex_reports ADD COLUMN parsed_item_numbers TEXT")
            if 'items_matched' not in existing_cols:
                migrations.append("ALTER TABLE yandex_reports ADD COLUMN items_matched INTEGER DEFAULT 0")
            for col, sql in [
                ('parsed_sections', "ALTER TABLE yandex_reports ADD COLUMN parsed_sections TEXT"),
                ('match_details', "ALTER TABLE yandex_reports ADD COLUMN match_details TEXT"),
                ('file_version', "ALTER TABLE yandex_reports ADD COLUMN file_version INTEGER DEFAULT 1"),
                ('superseded_by_id', "ALTER TABLE yandex_reports ADD COLUMN superseded_by_id INTEGER"),
                ('completeness_status', "ALTER TABLE yandex_reports ADD COLUMN completeness_status VARCHAR(20) DEFAULT 'none'"),
            ]:
                if col not in existing_cols:
                    migrations.append(sql)
        if 'yandex_report_task_links' in inspector.get_table_names():
            link_cols = {col['name'] for col in inspector.get_columns('yandex_report_task_links')}
            if 'match_method' not in link_cols:
                migrations.append("ALTER TABLE yandex_report_task_links ADD COLUMN match_method VARCHAR(20) DEFAULT 'auto'")
            if 'confidence' not in link_cols:
                migrations.append("ALTER TABLE yandex_report_task_links ADD COLUMN confidence REAL DEFAULT 1.0")
        for sql in migrations:
            db.session.execute(text(sql))
        if migrations:
            db.session.commit()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
