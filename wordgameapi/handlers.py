import json
from functools import reduce
from datetime import datetime, timedelta
from base64 import b64encode, b64decode
from flask import make_response, jsonify, request
from uuid import uuid4
from sqlalchemy.sql import text
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError
from flask_jwt import jwt_required, current_identity
import jwt

from .models import (
    db, Session, Category, Term, User, Collection,
    TermStat, WeeklyTermStat,
)

JWT_SECRET = 's3cr3t'

client = flow_from_clientsecrets('/Users/khanhhua/dev/wordgame-api/client_secret.json',
                                 scope='email profile openid',
                                 redirect_uri='postmessage') # WTF-postmessage?!

EPOCH = datetime(1970, 1, 1)


def _create_cursor(offset, collection_id=None, category_id=None):
    if collection_id is None and category_id is None:
        raise ValueError('Invalid param')

    if collection_id is not None:
        return b64encode(json.dumps(dict(collection_id=collection_id,
                                         offset=offset)).encode('utf8')).decode('utf8')
    else:
        return b64encode(json.dumps(dict(category_id=category_id,
                                         offset=offset)).encode('utf8')).decode('utf8')


def _term_from_category(category_id, offset):
    return db.session.query(Term)\
        .from_statement(text(
            """
            SELECT DISTINCT `term`.id, word, tags FROM `term`
              LEFT JOIN `nomen` ON word = form
            WHERE SUBSTR(tags, 1, 11) = 'SUB:NOM:SIN'
              AND synset_id in
                (SELECT `synset_id` FROM `synset` AS S JOIN `category_link` AS CL ON S.id = CL.synset_id
                    JOIN `category` AS C ON C.id = CL.category_id
                    WHERE C.id = :category_id)
            LIMIT 1 OFFSET :offset
            """
        ))\
        .params(category_id=category_id,
                offset=offset)\
        .first()


def _term_from_collection(collection_id, offset):
    return db.session.query(Term) \
        .from_statement(text(
        """
        SELECT DISTINCT T.id, T.word, tags
        FROM `term` AS T
            LEFT JOIN `nomen` ON T.word = form
        WHERE SUBSTR(tags, 1, 11) = 'SUB:NOM:SIN'
            AND T.id = (SELECT JSON_EXTRACT(`term_ids`, :path)  FROM `collection`)
        LIMIT 1 OFFSET 0;
        """
    )) \
        .params(collection_id=collection_id,
                path='$[{}]'.format(offset)) \
        .first()


def login():
    access_code = request.json.get('access_code')

    try:
        oauth2credential = client.step2_exchange(access_code)
        user_id = oauth2credential.id_token['sub']
        user = db.session.query(User).filter(User.user_id==user_id).first()

        if user is None:
            db.session.add(User(user_id=user_id, provider='GOOGLE'))
            db.session.add(Collection(owner_id=user_id, name='Default', term_ids=[]))
            db.session.commit()

        iat = datetime.utcnow()
        token = jwt.encode(dict(sub=user_id,
                                iat=iat,
                                nbf=iat + timedelta(seconds=5),
                                exp=iat + timedelta(hours=1)
                                ),
                           JWT_SECRET, algorithm='HS256')

        collection = db.session.query(Collection)\
            .filter(Collection.owner_id==user_id,
                    Collection.name=='Default',
                    ).one()

        return jsonify(ok=True,
                       profile=oauth2credential.id_token,
                       default_collection=collection,
                       token=token.decode())
    except (FlowExchangeError, ValueError) as e:
        return make_response(jsonify(ok=False), 400)


@jwt_required()
def get_profile():
    try:
        user_id = current_identity
        profile = db.session.query(User)\
            .filter(User.user_id==user_id)\
            .one()
        collection = db.session.query(Collection) \
            .filter(Collection.owner_id==user_id,
                    Collection.name=='Default',
                    )\
            .one()
        print(collection)
        return jsonify(ok=True,
                       profile=profile,
                       default_collection=collection)
    except:
        return jsonify(ok=False,
                       error="Authentication")


@jwt_required()
def create_game_session():
    identity = current_identity

    category_id = request.json.get('category_id') if request.json is not None else None
    collection_id = request.json.get('collection_id') if request.json is not None else None
    cursor = _create_cursor(0,
                            collection_id=collection_id,
                            category_id=category_id)

    game_session = Session(id=str(uuid4()),
                           game_type='gender',
                           user_id=identity,
                           cursor=cursor)

    db.session.add(game_session)
    db.session.commit()
    db.session.refresh(game_session)

    return make_response(jsonify(ok=True,
                                 session=game_session),
                         201)


@jwt_required()
def get_my_session():
    identity = current_identity

    game_session = db.session.query(Session)\
        .filter(Session.user_id==identity)\
        .order_by(-Session.created_at)\
        .first()
    if game_session is None:
        return jsonify(ok=False)

    return jsonify(ok=True,
                   session=game_session)\


@jwt_required()
def delete_my_session():
    identity = current_identity

    game_session = db.session.query(Session)\
        .filter(Session.user_id==identity)\
        .order_by(-Session.created_at)\
        .first()
    if game_session is None:
        return jsonify(ok=False)

    game_session.status = Session.STATUS_DONE
    db.session.add(game_session)
    db.session.commit()

    return jsonify(ok=True)


def list_collections():
    collections = db.session.query(Category).all()

    return jsonify(ok=True,
                   collections=collections)


@jwt_required()
def list_my_collections():
    collections = db.session\
            .query(Collection)\
            .filter(Collection.owner_id==current_identity)\
            .all()

    return jsonify(ok=True,
                   collections=[dict(
                       id=item.id,
                       name=item.name,
                       is_owned=True,
                   ) for item in collections])


@jwt_required()
def add_term_to_collection(collection_id):
    collection = db.session.query(Collection).filter(Collection.id==collection_id).one()
    if collection is None:
        return make_response(jsonify(ok=False), 404)

    if 'term_id' not in request.json:
        return make_response(jsonify(ok=False), 400)

    term_id = request.json['term_id']
    if term_id not in collection.term_ids:
        collection.term_ids = collection.term_ids + [term_id]
        db.session.add(collection)
        db.session.commit()

    return jsonify(ok=True,
                   collection=collection)


def next_word():
    raw_cursor = request.args.get('cursor')
    if raw_cursor is None:
        return make_response(jsonify(ok=False,
                                     error="Cursor missing"))

    cursor = json.loads(b64decode(raw_cursor))
    category_id = None
    collection_id = None
    offset = cursor['offset']

    if 'category_id' in cursor:
        category_id = cursor['category_id']

        # TODO Refactor this magic from_statement SQL
        term = _term_from_category(category_id, offset)
        next_term = _term_from_collection(collection_id, offset + 1)
        has_next = next_term is not None
    elif 'collection_id' in cursor:
        collection_id = cursor['collection_id']
        term = _term_from_collection(collection_id, offset)
        next_term = _term_from_collection(collection_id, offset + 1)
        has_next = next_term is not None

    return jsonify(ok=True,
                   term=term,
                   has_next=has_next,
                   cursor=_create_cursor(offset + 1,
                                         category_id=category_id,
                                         collection_id=collection_id)
                   )


@jwt_required()
def get_session_stat(session_id):
    identity = current_identity
    rows = db.session.query(WeeklyTermStat).from_statement(text(
        """
        SELECT T.id, TS.week, TS.session_id, T.word, N.tags,
              SUM(TS.corrects) AS corrects, SUM(TS.wrongs) AS wrongs, SUM(TS.skippeds) AS skippeds
        FROM      `term_stat`  AS TS
        LEFT JOIN `session`    AS S ON S.id = TS.session_id
        LEFT JOIN `term`       AS T ON T.id = TS.term_id
        LEFT JOIN `nomen`      AS N ON N.form = T.word
        WHERE user_id = :user_id
            AND SUBSTR(tags, 1, 11) = 'SUB:NOM:SIN'
        GROUP BY T.id, TS.week, TS.session_id, T.word, N.tags
        """
        ))\
        .params(user_id=identity)

    game_type = 'gender'

    def count_corrects_wrongs(acc, item):
        acc.update(corrects=int(acc['corrects'] + item.corrects),
                   wrongs=int(acc['wrongs'] + item.wrongs)
                   )
        return acc

    if game_type == 'gender':
        report = dict(der=reduce(count_corrects_wrongs, [row for row in rows if row.tags == 'SUB:NOM:SIN:MAS'],
                                 dict(corrects=0, wrongs=0)),
                      die=reduce(count_corrects_wrongs, [row for row in rows if row.tags == 'SUB:NOM:SIN:FEM'],
                                 dict(corrects=0, wrongs=0)),
                      das=reduce(count_corrects_wrongs, [row for row in rows if row.tags == 'SUB:NOM:SIN:NEU'],
                                 dict(corrects=0, wrongs=0)))
    else:
        report = {}

    return jsonify(ok=True,
                   report=report)


@jwt_required()
def create_stat():
    identity = current_identity
    week = (datetime.utcnow() - EPOCH).days / 7
    session_id = request.json.get('session_id')
    term_id = request.json.get('term_id')
    correct = request.json.get('correct', None)
    skipped = request.json.get('skipped', None)

    # TODO Check if session belongs to identity

    if term_id is None:
        return make_response(jsonify(ok=False), 400)

    exists = db.session.query(db.session.query(TermStat)\
        .filter(TermStat.session_id == session_id,
                TermStat.term_id == term_id)\
        .exists())\
        .scalar()

    if exists:
        db.session.query(TermStat) \
            .filter(TermStat.session_id == session_id,
                    TermStat.term_id == term_id) \
            .update({
                TermStat.corrects: TermStat.corrects + 1 if correct == True else TermStat.corrects,
                TermStat.wrongs: TermStat.wrongs + 1 if correct == False else TermStat.wrongs,
                TermStat.skippeds: TermStat.skippeds + 1 if skipped == True else TermStat.skippeds,
            })
    else:
        db.session.add(TermStat(session_id=session_id,
                                term_id=term_id,
                                week=week,
                                corrects=1 if correct == True else 0,
                                wrongs=1 if correct == False else 0,
                                skippeds=1 if skipped == True else 0))
        db.session.commit()

    return jsonify(ok=True)
