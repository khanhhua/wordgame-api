from flask_jwt import JWT

def identity(payload):
    return payload['sub']

jwt = JWT(authentication_handler=lambda: True,
          identity_handler=identity)
