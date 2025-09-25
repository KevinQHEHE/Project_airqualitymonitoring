"""Create collections, apply validators and indexes using pymongo.

This mirrors the mongo shell helper but can run in the project's Python environment
and prints verification output.

Usage:
  python scripts/create_collections.py --mongo-uri <uri> --db <name>
If --mongo-uri / --db are omitted the app Config defaults will be used.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from pymongo import MongoClient, errors

# Ensure the repository root is on sys.path so `backend` package imports work
# when this script is executed directly (e.g., inside a venv).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Config


def load_json(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mongo-uri')
    p.add_argument('--db')
    p.add_argument('--recreate', action='store_true', help='Drop existing collections before creating them (use with caution)')
    args = p.parse_args()

    mongo_uri = args.mongo_uri or os.environ.get('MONGO_URI') or Config.MONGO_URI
    db_name = args.db or os.environ.get('MONGO_DB') or Config.MONGO_DB

    client = MongoClient(mongo_uri)
    db = client[db_name]

    base = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app', 'schemas')
    # resolve relative path to validators
    validators_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app', 'schemas', 'mongo_validators')

    subs_validator_path = os.path.join(validators_dir, 'alert_subscriptions.validator.json')
    logs_validator_path = os.path.join(validators_dir, 'notification_logs.validator.json')

    subs_validator = load_json(subs_validator_path)
    logs_validator = load_json(logs_validator_path)

    # Create or update collections with validators
    for name, validator in (('alert_subscriptions', subs_validator), ('notification_logs', logs_validator)):
        try:
            if args.recreate:
                # Drop the collection first if requested
                if name in db.list_collection_names():
                    print(f"Dropping existing collection: {name}")
                    db.drop_collection(name)
            # If collection exists, use collMod to apply validator
            if name in db.list_collection_names():
                print(f"Updating validator for existing collection: {name}")
                try:
                    db.command({'collMod': name, 'validator': validator, 'validationLevel': 'moderate'})
                except errors.OperationFailure as e:
                    print(f"  collMod failed for {name}: {e}")
            else:
                print(f"Creating collection: {name}")
                db.create_collection(name, validator=validator)
        except Exception as e:
            print(f"Failed to create/update {name}: {e}")

    # Create indexes (same as the JS helper)
    try:
        subs = db.alert_subscriptions
        subs.create_index([('user_id', 1)])
        subs.create_index([('station_id', 1)])
        subs.create_index([('station_id', 1), ('alert_threshold', 1), ('status', 1)])
        subs.create_index([('user_id', 1), ('status', 1)])
        print('Created indexes for alert_subscriptions')
    except Exception as e:
        print('Error creating alert_subscriptions indexes:', e)

    try:
        logs = db.notification_logs
        logs.create_index([('subscription_id', 1)])
        logs.create_index([('user_id', 1)])
        logs.create_index([('station_id', 1)])
        logs.create_index([('sentAt', 1)])
        # TTL index: 90 days
        try:
            logs.create_index('sentAt', expireAfterSeconds=90 * 24 * 60 * 60)
            print('Created TTL index for notification_logs.sentAt (90 days)')
        except Exception as e:
            print('Failed to create TTL index (may already exist with different options):', e)
    except Exception as e:
        print('Error creating notification_logs indexes:', e)

    # Verification
    print('\nVerification:')
    try:
        print('Collections:', db.list_collection_names())
        print('\nalert_subscriptions indexes:')
        for idx in db.alert_subscriptions.list_indexes():
            print(' ', idx['name'], idx.get('key'), 'expireAfterSeconds=' + str(idx.get('expireAfterSeconds')) if idx.get('expireAfterSeconds') else '')
        print('\nnotification_logs indexes:')
        for idx in db.notification_logs.list_indexes():
            print(' ', idx['name'], idx.get('key'), 'expireAfterSeconds=' + str(idx.get('expireAfterSeconds')) if idx.get('expireAfterSeconds') else '')
    except Exception as e:
        print('Verification failed:', e)


if __name__ == '__main__':
    main()
