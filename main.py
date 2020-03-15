from dotenv import load_dotenv
load_dotenv()
import os

from flask import Flask
from flask_cors import CORS

from wordgameapi.models import db
from wordgameapi import handlers
from wordgameapi.auth import jwt

DEBUG = os.getenv('DEBUG', False)
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT', '3306')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = DEBUG != False
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://{}:{}@{}:{}/wordgame'.format(DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
app.config['JWT_AUTH_HEADER_PREFIX'] = 'Bearer'
app.config['SECRET_KEY'] = 's3cr3t'

db.init_app(app)
jwt.init_app(app)
CORS(app, resources={r'/api/*': {'origins': '*', 'supports_credential': True}})

app.add_url_rule("/api/health-check", "health-check", methods=['GET'],
                 view_func=handlers.health_check)
app.add_url_rule("/api/auth", "login", methods=['POST'],
                 view_func=handlers.login)
app.add_url_rule("/api/auth", "get-profile", methods=['GET'],
                 view_func=handlers.get_profile)
app.add_url_rule("/api/session", "create-session", methods=['POST'],
                 view_func=handlers.create_game_session)
app.add_url_rule("/api/session", "get-session", methods=['GET'],
                 view_func=handlers.get_my_session)
app.add_url_rule("/api/session", "delete-session", methods=['DELETE'],
                 view_func=handlers.delete_my_session)
app.add_url_rule("/api/search", "search-terms", methods=['GET'],
                 view_func=handlers.search_terms)
app.add_url_rule("/api/me/collections", "list-my-collections", methods=['GET'],
                 view_func=handlers.list_my_collections)
app.add_url_rule("/api/me/collections/<int:collection_id>", "get-collection", methods=['GET'],
                 view_func=handlers.get_collection)
app.add_url_rule("/api/me/collections", "create-collection", methods=['POST'],
                 view_func=handlers.create_collection)
app.add_url_rule("/api/me/collections/<int:collection_id>", "update-collection", methods=['PATCH'],
                 view_func=handlers.update_collection)
app.add_url_rule("/api/me/collections/<int:collection_id>/terms", "add-term-to-collections", methods=['POST'],
                 view_func=handlers.add_term_to_collection)
app.add_url_rule("/api/me/collections/<int:collection_id>/terms/<int:term_id>", "remove-term-from-collection",
                 methods=['DELETE'],
                 view_func=handlers.remove_term_from_collection)
app.add_url_rule("/api/collections", "list-categories", methods=['GET'],
                 view_func=handlers.list_collections)
app.add_url_rule("/api/words", "get-next-word", methods=['GET'],
                 view_func=handlers.next_word)
app.add_url_rule("/api/stats/<session_id>", "get-session-stat", methods=['GET'],
                 view_func=handlers.get_session_stat)
app.add_url_rule("/api/stats", "get-weekly-performance-stat", methods=['GET'],
                 view_func=handlers.get_weekly_performance_stat)
app.add_url_rule("/api/stats", "create-stat", methods=['POST'],
                 view_func=handlers.create_stat)

if __name__ == '__main__':
    if os.getenv('GAE_ENV', '').startswith('standard'):
        app.run()  # production
    else:
        app.run(port=8080, host="0.0.0.0", debug=True)  # localhost
