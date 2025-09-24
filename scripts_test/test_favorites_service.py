import pytest
from types import SimpleNamespace

from backend.app.services.user import favorites_service as svc


def test_create_favorite_with_latlon(monkeypatch):
    user = {'_id': '507f1f77bcf86cd799439011'}

    def fake_find_by_id(uid):
        return user

    def fake_update_user_by_id(uid, ops):
        # ensure location set
        assert '$set' in ops and 'location' in ops['$set']
        return True

    monkeypatch.setattr(svc, 'users_repo', SimpleNamespace(find_by_id=fake_find_by_id, update_user_by_id=fake_update_user_by_id))

    payload = {'latitude': 10.0, 'longitude': 20.0}
    res = svc.create_favorite(user['_id'], payload)
    assert res['user_id'] == str(user['_id'])
    assert res['location']['type'] == 'Point'
    assert isinstance(res['location']['coordinates'][0], float)


def test_create_favorite_invalid_coords(monkeypatch):
    user = {'_id': '507f1f77bcf86cd799439011'}
    monkeypatch.setattr(svc, 'users_repo', SimpleNamespace(find_by_id=lambda uid: user))
    with pytest.raises(svc.FavoritesServiceError):
        svc.create_favorite(user['_id'], {'latitude': 200.0, 'longitude': 0.0})


def test_list_favorites_none(monkeypatch):
    user = {'_id': '1', 'location': None}
    monkeypatch.setattr(svc, 'users_repo', SimpleNamespace(find_by_id=lambda uid: user))
    res = svc.list_favorites(user['_id'])
    assert res == []


def test_update_favorite_location(monkeypatch):
    user = {'_id': '1', 'location': {'type': 'Point', 'coordinates': [20.0, 10.0]}}

    def fake_find_by_id(uid):
        return user

    def fake_update_user_by_id(uid, ops):
        assert '$set' in ops and 'location' in ops['$set']
        user['location'] = ops['$set']['location']
        return True

    monkeypatch.setattr(svc, 'users_repo', SimpleNamespace(find_by_id=fake_find_by_id, update_user_by_id=fake_update_user_by_id))
    out = svc.update_favorite(user['_id'], None, {'latitude': 11.0, 'longitude': 21.0})
    assert out['location']['coordinates'] == [21.0, 11.0]


def test_delete_favorite(monkeypatch):
    user = {'_id': '1', 'location': {'type': 'Point', 'coordinates': [20.0, 10.0]}}

    def fake_find_by_id(uid):
        return user

    def fake_update_user_by_id(uid, ops):
        # emulate $unset of location
        if '$unset' in ops and 'location' in ops['$unset']:
            user.pop('location', None)
        return True

    monkeypatch.setattr(svc, 'users_repo', SimpleNamespace(find_by_id=fake_find_by_id, update_user_by_id=fake_update_user_by_id))
    svc.delete_favorite(user['_id'], None)
    assert 'location' not in user
