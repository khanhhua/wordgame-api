from flask_jwt import JWT

def identity(payload):
    """
    :param payload:
    :return: Tagged tuple "session"|"user", ID
    """
    subject = payload['sub']
    if 'session:' in subject:
        return 'session', subject[8:]

    return 'user', subject

jwt = JWT(authentication_handler=lambda: True,
          identity_handler=identity)
