# backend/app/extensions.py
"""
Expose a single Flask-PyMongo client 'mongo' and helpers.
Reads MONGO_URI from env; DB name taken from MONGO_DB or from URI path.
"""

import os
from flask_pymongo import PyMongo

mongo = PyMongo()

def init_extensions(app):
    """
    Attach Flask-PyMongo to the app using env config.
    """
    mongo_uri = os.environ.get('MONGO_URI')
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable is not set")
    
    # Flask-PyMongo expects app.config['MONGO_URI']
    app.config['MONGO_URI'] = mongo_uri
    mongo.init_app(app)

def get_db():
    """
    Return a PyMongo database handle
    If MONGO_DB is set, return that DB from the client.
    Else fall back to mongo.db (db parsed from URI).
    """
    db_name = os.environ.get('MONGO_DB')
    if db_name:
        return mongo.cx[db_name]  
    return mongo.db