"""Testy jednostkowe blokady konta po nieudanych probach logowania (lockout.py) - ten sam wzorzec
_FakeRedis co tests/test_ocr_cooldown.py."""
from app.modules.users.lockout import RedisLoginLockoutStore


class _FakeRedis:
    def __init__(self):
        self.values: dict[str, int | str] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.ttls[key] = ex

    def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)


def test_ponizej_progu_nie_blokuje():
    store = RedisLoginLockoutStore(_FakeRedis())

    assert [store.record_failure("a@test.local") for _ in range(4)] == [0, 0, 0, 0]
    assert store.remaining_seconds("a@test.local") == 0


def test_piata_nieudana_proba_blokuje_na_15_minut():
    store = RedisLoginLockoutStore(_FakeRedis())

    results = [store.record_failure("a@test.local") for _ in range(5)]

    assert results == [0, 0, 0, 0, 15 * 60]
    assert store.remaining_seconds("a@test.local") == 15 * 60


def test_reset_zeruje_licznik_i_blokade():
    store = RedisLoginLockoutStore(_FakeRedis())
    for _ in range(5):
        store.record_failure("a@test.local")
    assert store.remaining_seconds("a@test.local") > 0

    store.reset("a@test.local")

    assert store.remaining_seconds("a@test.local") == 0
    assert store.record_failure("a@test.local") == 0


def test_blokada_jest_per_konto_case_insensitive():
    store = RedisLoginLockoutStore(_FakeRedis())
    for _ in range(5):
        store.record_failure("A@Test.local")

    assert store.remaining_seconds("a@test.local") == 15 * 60
    assert store.remaining_seconds("inny@test.local") == 0
