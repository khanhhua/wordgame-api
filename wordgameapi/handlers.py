import os
import json
from math import sin, floor
from functools import reduce
from datetime import datetime, timedelta
from base64 import b64encode, b64decode
from random import randint

from flask import make_response, jsonify, request
from uuid import uuid4
from sqlalchemy.sql import text
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError
from flask_jwt import jwt_required, current_identity, _jwt_required
import jwt
import requests

from .models import (
    db, Session, Category, Term, User, Collection,
    TermStat, WeeklyTermStat, PerformanceStat,
)

JWT_SECRET = os.getenv('JWT_SECRET', None)
RECAPTCHA_SECRET = os.getenv('RECAPTCHA_SECRET', None)

client = flow_from_clientsecrets('./client_secret.json',
                                 scope='email profile openid',
                                 redirect_uri='postmessage') # WTF-postmessage?!

EPOCH = datetime(1970, 1, 1)


def _create_cursor(offset, seed=None, collection_id=None, category_id=None):
    if seed is None:
        seed = randint(1, 100)
    if collection_id is None and category_id is None:
        raise ValueError('Invalid param')

    if collection_id is not None:
        return b64encode(json.dumps(dict(collection_id=collection_id,
                                         seed=seed,
                                         offset=offset)).encode('utf8')).decode('utf8')
    else:
        return b64encode(json.dumps(dict(category_id=category_id,
                                         seed=seed,
                                         offset=offset)).encode('utf8')).decode('utf8')


def _term_from_category(category_id, seed, offset):
    count_query = db.engine.execute(text(
        """
        SELECT COUNT(x.id) AS count_ FROM (
            SELECT DISTINCT `term`.id, word, tags FROM `term`
                  LEFT JOIN `nomen` ON word = form
                WHERE SUBSTR(tags, 1, 11) = 'SUB:NOM:SIN'
                  AND synset_id in
                    (SELECT `synset_id` FROM `synset` AS S JOIN `category_link` AS CL ON S.id = CL.synset_id
                        JOIN `category` AS C ON C.id = CL.category_id
                        WHERE C.id = :category_id)
        ) AS x
        """
        ),
        category_id=category_id)
    count = list(count_query)[0]['count_']

    return db.session.query(Term)\
        .from_statement(text(
            """
            SELECT DISTINCT `term`.id, word, tags, MOD(`term`.id, SIN(:seed) * :count -  FLOOR(SIN(:seed) * :count)) AS r
            FROM `term` LEFT JOIN `nomen` ON word = form
            WHERE SUBSTR(tags, 1, 11) = 'SUB:NOM:SIN'
              AND synset_id in
                (SELECT `synset_id` FROM `synset` AS S JOIN `category_link` AS CL ON S.id = CL.synset_id
                    JOIN `category` AS C ON C.id = CL.category_id
                    WHERE C.id = :category_id)
            ORDER BY r
            LIMIT 1 OFFSET :offset
            """
        ))\
        .params(category_id=category_id,
                seed=seed,
                count=count,
                offset=offset)\
        .first()


def _term_from_collection(collection_id, seed, offset):
    collection = (db.session.query(Collection)
                 .filter(Collection.id==collection_id)
                 .one()
                 )
    count = len(collection.term_ids)
    if offset >= count:
        return None

    data = sorted([(term_id, term_id % ((sin(seed) * count) - floor(sin(seed) * count))) for term_id in collection.term_ids],
                  key=lambda item: item[1])
    selected_term_id = data[offset][0]

    return (db.session.query(Term)
            .filter(Term.id == selected_term_id)
            .first())


def is_human(captcha_response):
    payload = {'response': captcha_response, 'secret': RECAPTCHA_SECRET}
    response = requests.post("https://www.google.com/recaptcha/api/siteverify", payload)
    response_text = json.loads(response.text)
    return response_text['success']


def health_check():
    return make_response("ok", 200)


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
        user_or_session, user_id = current_identity
        if user_or_session == 'session':
            return make_response(jsonify(ok=False,
                                         error="Authentication"),
                                 403)

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


def create_game_session():
    try:
        _jwt_required(None)
    except:
        pass
    identity = None
    token = None

    _current_identity = current_identity._get_current_object()

    if _current_identity is None or _current_identity[0] == 'session':
        recaptcha_token = request.json.get('recaptcha')

        if recaptcha_token is None:
            return make_response(jsonify(ok=False,
                                         error='Recaptcha missing'),
                                 400)

        if not is_human(recaptcha_token):
            return make_response(jsonify(ok=False,
                                         error='Bad recaptcha'),
                                 400)
        category = _get_random_category()
        category_id = category.id
    else:
        category_id = request.json.get('category_id') if request.json is not None else None
        user_or_session, identity = _current_identity

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

    if identity is None:
        iat = datetime.utcnow()
        token = jwt.encode(dict(sub='session:{}'.format(game_session.id),
                                iat=iat,
                                nbf=iat + timedelta(seconds=5),
                                exp=iat + timedelta(minutes=10)
                                ),
                           JWT_SECRET, algorithm='HS256').decode()

    return make_response(jsonify(ok=True,
                                 session=game_session,
                                 token=token),
                         201)


@jwt_required()
def get_my_session():
    user_or_session, identity = current_identity

    if user_or_session == 'user':
        game_session = db.session.query(Session)\
            .filter(Session.user_id==identity) \
            .order_by(-Session.created_at)\
            .first()
    else:
        game_session = db.session.query(Session) \
            .filter(Session.id == identity) \
            .first()

    if game_session is None:
        return jsonify(ok=False)

    return jsonify(ok=True,
                   session=game_session)\


def _get_random_category():
    count = db.session.query(Category).count()
    return (db.session.query(Category)
            .offset(randint(0, count - 1))
            .first()
           )


@jwt_required()
def delete_my_session():
    user_or_session, identity = current_identity

    game_session = None
    if user_or_session == 'user':
        game_session = db.session.query(Session)\
            .filter(Session.user_id==identity)\
            .order_by(-Session.created_at)\
            .first()
    else:
        game_session = db.session.query(Session) \
            .filter(Session.id == identity) \
            .first()
    if game_session is None:
        return jsonify(ok=False)

    game_session.status = Session.STATUS_DONE
    db.session.add(game_session)
    db.session.commit()

    return jsonify(ok=True)


@jwt_required()
def search_terms():
    query = request.args.get('q', '').strip()
    if len(query) == 0:
        return jsonify(ok=True,
                       terms=[])

    terms = (db.session.query(Term)
             .distinct()
             .filter(Term.word.ilike('{}%'.format(query)))
             .filter(Term.tags.like('SUB:NOM:SIN%'))
             .all()
             )
    return jsonify(ok=True,
                   terms=[dict(id=item.id,
                               word=item.word)
                          for item in terms])


def list_collections():
    collections = db.session.query(Category).all()

    return jsonify(ok=True,
                   collections=collections)


@jwt_required()
def list_my_collections():
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return make_response(jsonify(ok=False),
                             403)

    collections = db.session\
            .query(Collection)\
            .filter(Collection.owner_id==identity)\
            .all()

    return jsonify(ok=True,
                   collections=[dict(
                       id=item.id,
                       name=item.name,
                       is_owned=True,
                   ) for item in collections])


@jwt_required()
def create_collection():
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return make_response(jsonify(ok=False),
                             403)
    name = request.json.get('name')
    if name is None:
        return make_response(jsonify(ok=False, error="Name missing"), 400)

    collection = Collection(name=name, owner_id=identity)
    db.session.add(collection)
    db.session.commit()
    db.session.refresh(collection)

    return make_response(jsonify(ok=True,
                   collection=dict(
                       id=collection.id,
                       name=collection.name,
                       is_owned=True,
                   )), 201)


@jwt_required()
def get_collection(collection_id):
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return make_response(jsonify(ok=False),
                             403)

    collection = (db.session.query(Collection)
                  .filter(Collection.owner_id == identity)
                  .filter(Collection.id == collection_id)
                  .one()
                  )
    if collection is None:
        return make_response(jsonify(ok=False), 404)

    terms = [] if collection.term_ids is None else (db.session.query(Term)
                                                    .filter(Term.id.in_(collection.term_ids))
                                                    .all())
    return make_response(jsonify(ok=True,
                                 collection=dict(
                                     id=collection.id,
                                     name=collection.name,
                                     is_owned=True,
                                     terms=terms,
                                 )), 200)


@jwt_required()
def update_collection(collection_id):
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return make_response(jsonify(ok=False),
                             403)

    name = request.json.get('name')
    if name is None:
        return make_response(jsonify(ok=True), 200)

    collection = (db.session.query(Collection)
                  .filter(Collection.owner_id == identity)
                  .filter(Collection.id == collection_id)
                  .first()
                  )
    if collection is None:
        return make_response(jsonify(ok=False), 404)

    collection.name = name
    db.session.add(collection)
    db.session.commit()
    db.session.refresh(collection)

    return make_response(jsonify(ok=True,
                   collection=dict(
                       id=collection.id,
                       name=collection.name,
                       is_owned=True,
                   )), 200)


@jwt_required()
def add_term_to_collection(collection_id):
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return make_response(jsonify(ok=False),
                             403)

    collection = (db.session.query(Collection)
                  .filter(Collection.owner_id == identity)
                  .filter(Collection.id==collection_id)
                  .first()
                  )
    if collection is None:
        return make_response(jsonify(ok=False), 404)

    if 'term_id' not in request.json:
        return make_response(jsonify(ok=False), 400)

    term_id = request.json['term_id']
    if collection.term_ids is None:
        collection.term_ids = [term_id]
        db.session.add(collection)
        db.session.commit()
    elif term_id not in collection.term_ids:
        collection.term_ids = collection.term_ids + [term_id]
        db.session.add(collection)
        db.session.commit()

    return jsonify(ok=True,
                   collection=collection)


@jwt_required()
def remove_term_from_collection(collection_id, term_id):
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return make_response(jsonify(ok=False),
                             403)

    collection = (db.session.query(Collection)
                  .filter(Collection.owner_id == identity)
                  .filter(Collection.id==collection_id)
                  .first()
                  )
    if collection is None:
        return make_response(jsonify(ok=False), 404)

    if collection.term_ids is None:
        return jsonify(ok=True,
                       collection=collection)
    elif term_id in collection.term_ids:
        collection.term_ids = [_id for _id in collection.term_ids if _id != term_id]
        db.session.add(collection)
        db.session.commit()

    return jsonify(ok=True,
                   collection=collection)


@jwt_required()
def next_word():
    raw_cursor = request.args.get('cursor')
    if raw_cursor is None:
        return make_response(jsonify(ok=False,
                                     error="Cursor missing"))

    cursor = json.loads(b64decode(raw_cursor))
    category_id = None
    collection_id = None
    offset = cursor['offset']
    seed = cursor['seed']

    if 'category_id' in cursor:
        category_id = cursor['category_id']

        # TODO Refactor this magic from_statement SQL
        term = _term_from_category(category_id, seed, offset)
        next_term = _term_from_category(category_id, seed, offset + 1)
        has_next = next_term is not None
    elif 'collection_id' in cursor:
        collection_id = cursor['collection_id']
        term = _term_from_collection(collection_id, seed, offset)
        next_term = _term_from_collection(collection_id, seed, offset + 1)
        has_next = next_term is not None

    return jsonify(ok=True,
                   term=term,
                   has_next=has_next,
                   cursor=_create_cursor(offset + 1,
                                         seed=seed,
                                         category_id=category_id,
                                         collection_id=collection_id)
                   )


@jwt_required()
def get_session_stat(session_id):
    user_or_session, identity = current_identity
    if user_or_session == 'session' and session_id != identity:
        return make_response(jsonify(ok=False),
                             403)

    rows = db.session.query(WeeklyTermStat).from_statement(text(
        """
        SELECT T.id, TS.week, TS.session_id, T.word, N.tags,
              SUM(TS.corrects) AS corrects, SUM(TS.wrongs) AS wrongs, SUM(TS.skippeds) AS skippeds
        FROM      `term_stat`  AS TS
        LEFT JOIN `session`    AS S ON S.id = TS.session_id
        LEFT JOIN `term`       AS T ON T.id = TS.term_id
        LEFT JOIN `nomen`      AS N ON N.form = T.word
        WHERE S.id = :session_id
            AND SUBSTR(tags, 1, 11) = 'SUB:NOM:SIN'
        GROUP BY T.id, TS.week, TS.session_id, T.word, N.tags
        """
        ))\
        .params(session_id=session_id)

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
def get_weekly_performance_stat():
    user_or_session, identity = current_identity
    if user_or_session == 'session':
        return jsonify(ok=True,
                       report={}
                       )

    week = (datetime.utcnow() - EPOCH).days / 7
    # LIMIT REPORT scopes to 8 weeks ago
    WEEKS_LIMIT = 8

    types = request.args.getlist('reports')
    report = dict()

    if 'worst' in types:
        worst_performers = (db.session.query(PerformanceStat)
                            .filter(PerformanceStat.user_id == identity)
                            .filter(PerformanceStat.correct_factor != 1)
                            .filter(PerformanceStat.week >= week - WEEKS_LIMIT)
                            .limit(100)
                            .all()
                            )
        report['worst_performers'] = worst_performers

    if 'weekly' in types:
        weekly_performance = (db.session.query(PerformanceStat)
                              .from_statement(text(
            """
            SELECT `week` as `term_id`, '' AS user_id, '' AS word, '' AS tags, `week`,
                AVG(confidence_factor) AS confidence_factor,
                AVG(correct_factor) AS correct_factor
            FROM performance_stat
            WHERE user_id = :user_id AND week >= :week
            GROUP BY `week`
            """
                              ))
                              .params(user_id=identity,
                                      week=week-WEEKS_LIMIT)
                              .all())
        report['weekly_performance'] = [dict(week=item.week,
                                             confidence_factor=float(item.confidence_factor),
                                             correct_factor=float(item.correct_factor))
                                       for item in weekly_performance]

    if 'histogram' in types:
        histogram = (db.engine.execute(text(
            """
            SELECT AB.`seconds`, correct_count, wrong_count
            FROM (SELECT DISTINCT `seconds`
                FROM `term_stat` JOIN `session` AS S ON S.id = session_id
                WHERE user_id = :user_id AND week >= :week) AS AB
            LEFT JOIN (SELECT seconds_correct AS `seconds`, COUNT(*) AS correct_count
                FROM `term_stat` JOIN `session` AS S ON S.id = session_id
                WHERE seconds_correct IS NOT NULL AND user_id = :user_id AND week >= :week
                GROUP BY seconds_correct) AS A ON AB.`seconds` = A.`seconds`
            LEFT JOIN
                (SELECT seconds, COUNT(*) AS wrong_count
                FROM `term_stat` JOIN `session` AS S ON S.id = session_id
                WHERE seconds_correct IS NULL AND user_id = :user_id AND week >= :week
                GROUP BY seconds) AS B ON AB.`seconds` = B.`seconds`
            ORDER BY AB.`seconds`;
            """
                    ),
        week=week - WEEKS_LIMIT,
        user_id=identity))
        report['histogram'] = [dict(seconds=item['seconds'],
                                    correct_count=item['correct_count'],
                                    wrong_count=item['wrong_count'])
                               for item in histogram
                               ]

    if len(report) == 0:
        return jsonify(ok=False,
                       error='Invalid report(s) requested')

    return jsonify(ok=True,
                   report=report)


@jwt_required()
def create_stat():
    week = (datetime.utcnow() - EPOCH).days / 7
    session_id = request.json.get('session_id')
    term_id = request.json.get('term_id')
    correct = request.json.get('correct', None)
    skipped = request.json.get('skipped', None)
    seconds = request.json.get('seconds', 1)

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
                TermStat.seconds: TermStat.seconds + seconds,
                TermStat.seconds_correct: TermStat.seconds_correct + seconds if correct == True else TermStat.seconds_correct,
            })
    else:
        db.session.add(TermStat(session_id=session_id,
                                term_id=term_id,
                                week=week,
                                corrects=1 if correct == True else 0,
                                wrongs=1 if correct == False else 0,
                                skippeds=1 if skipped == True else 0,
                                seconds=seconds,
                                seconds_correct=seconds if correct == True else None))
        db.session.commit()

    return jsonify(ok=True)
