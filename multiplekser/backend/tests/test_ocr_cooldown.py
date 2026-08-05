from app.modules.ocr.cooldown import RedisOCRCooldownStore


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


def test_kolejne_429_blokuja_na_10_15_20_i_dalej_20_minut():
    store = RedisOCRCooldownStore(_FakeRedis())

    assert [store.record_rate_limit("Gemini darmowy") for _ in range(4)] == [10, 15, 20, 20]


def test_sukces_zeruje_licznik_cooldownu():
    store = RedisOCRCooldownStore(_FakeRedis())
    assert store.record_rate_limit("Gemini darmowy") == 10
    assert store.record_rate_limit("Gemini darmowy") == 15

    store.reset("Gemini darmowy")

    assert store.record_rate_limit("Gemini darmowy") == 10
