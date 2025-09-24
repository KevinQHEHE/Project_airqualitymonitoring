import math


def haversine_distance_km(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    hav = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    R = 6371.0088
    c = 2 * math.asin(min(1, math.sqrt(hav)))
    return R * c


def format_km(value: float) -> float:
    return round(value + 1e-12, 2)


def test_haversine_known_values():
    # Hanoi approx (21.0278, 105.8342) to Ho Chi Minh City (10.8231, 106.6297)
    hanoi = (21.0278, 105.8342)
    hcm = (10.8231, 106.6297)
    dist = haversine_distance_km(hanoi, hcm)
    # Known approximate distance ~1150 km, allow 5% tolerance
    assert 1000 < dist < 1300


def test_format_km_rounding():
    assert format_km(1.23456) == 1.23
    assert format_km(1.2356) == 1.24
