import os
import platform
from flask import Flask
from routes import main_blueprint
from database import db
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
app.register_blueprint(main_blueprint, url_prefix='/task')

with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
