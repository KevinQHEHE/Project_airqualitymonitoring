"""Migration helper: migrate documents from `favorite_locations` collection
into `users.location` (single location per user). Idempotent: will skip
if user already has `location` set unless `--force` is provided.

Usage: python scripts/migrate_favorites_to_users.py --mongo-uri <uri> --db <name> [--force]
"""
import argparse
from pymongo import MongoClient
from datetime import datetime


def migrate(mongo_uri: str, db_name: str, force: bool = False):
    client = MongoClient(mongo_uri)
    db = client[db_name]

    favs = db.get_collection('favorite_locations')
    users = db.get_collection('users')

    total = favs.count_documents({})
    print(f"Found {total} favorite_locations to consider")
    moved = 0
    for doc in favs.find({}):
        uid = doc.get('user_id')
        if not uid:
            continue
        user = users.find_one({'_id': uid})
        # support string / ObjectId ids by matching both
        if not user:
            user = users.find_one({'_id': {'$in': [uid]}})
        if not user:
            print(f"No user found for favorite {doc.get('_id')}, user_id={uid}")
            continue

        if user.get('location') and not force:
            print(f"Skipping user {user.get('_id')} (already has location). Use --force to override")
            continue

        location = doc.get('location')
        if not location:
            print(f"Skipping favorite {doc.get('_id')} with no location")
            continue

        now = datetime.utcnow()
        res = users.update_one({'_id': user.get('_id')}, {'$set': {'location': location, 'updatedAt': now}})
        if res.modified_count > 0:
            moved += 1
            print(f"Migrated favorite {doc.get('_id')} -> user {user.get('_id')}")

    print(f"Migration complete. moved={moved}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mongo-uri', required=True)
    p.add_argument('--db', required=True)
    p.add_argument('--force', action='store_true')
    args = p.parse_args()
    migrate(args.mongo_uri, args.db, force=args.force)


if __name__ == '__main__':
    main()
