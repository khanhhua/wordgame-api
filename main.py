import os

from flask import Flask
from flask_cors import CORS

from wordgameapi.models import db
from wordgameapi import handlers
from wordgameapi.auth import jwt

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:ILkopTAD2ut2exVEJUh5UjehL@f@localhost:3306/wordgame'
app.config['JWT_AUTH_HEADER_PREFIX'] = 'Bearer'
app.config['SECRET_KEY'] = 's3cr3t'

db.init_app(app)
jwt.init_app(app)
CORS(app, resources={r'/api/*': {'origins': '*', 'supports_credential': True}})

app.add_url_rule("/api/auth", "login", methods=['POST'],
                 view_func=handlers.login)
app.add_url_rule("/api/session", "create-session", methods=['POST'],
                 view_func=handlers.create_game_session)
app.add_url_rule("/api/session", "get-session", methods=['GET'],
                 view_func=handlers.get_my_session)
app.add_url_rule("/api/me/collections", "list-my-collections", methods=['GET'],
                 view_func=handlers.list_my_collections)
app.add_url_rule("/api/me/collections/<int:collection_id>/terms", "add-term-to-collections", methods=['POST'],
                 view_func=handlers.add_term_to_collection)
app.add_url_rule("/api/collections", "list-categories", methods=['GET'],
                 view_func=handlers.list_collections)
app.add_url_rule("/api/words", "get-next-word", methods=['GET'],
                 view_func=handlers.next_word)
app.add_url_rule("/api/stats/<session_id>", "get-session-stat", methods=['GET'],
                 view_func=handlers.get_session_stat)
app.add_url_rule("/api/stats", "create-stat", methods=['POST'],
                 view_func=handlers.create_stat)

if __name__ == '__main__':
    if os.getenv('GAE_ENV', '').startswith('standard'):
        app.run()  # production
    else:
        app.run(port=8080, host="localhost", debug=True)  # localhost
