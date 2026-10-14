# Multiplekser AUTO Gemini FREE1 + FREE2 (2026-10-14)

## Scope

- Two separate free-tier Google projects via `GEMINI_API_KEY_FREE` and `GEMINI_API_KEY_FREE_2`. Never print credentials; `.env` is mode 0600.
- The primary OCR worker receives `GEMINI_API_KEY_FREE_2` from docker-compose.prod.yml. Other production containers need not receive this key.
- AUTO V3 still runs Gemini-first, then Claude Sonnet as fallback and JEV ACTIVE. No auto use of `GEMINI_API_KEY_PAID`, even if defined.
- Each model/project pair uses an **independently named Redis cooldown** (`FREE2` suffix for second key). FREE1 labels retain backward compatibility with existing Redis cooldowns.
- Classification prioritizes 3.5 Flash-Lite FREE1, then FREE2; 3.6 Flash FREE1, then FREE2; 3.1 Flash-Lite last because 7s minimal text probes timed out on both.
- Full OCR prefers 3.6 Flash (the successful classification project first), then the other free project, then 3.5 Flash-Lite and 3.1 Flash-Lite. A 15s cap applies to the classification stage; total Gemini-stage limit remains 26s and still falls back to Claude if unsuccessful.
- A model appearing in `models.list` is **not** proof of an available OCR quota. Success is validated via actual `generateContent` and independent document shadow probes.

## Tests completed

| Test | FREE1 | FREE2 |
|---|---|---|
| `models.list` | Existing previously functional | HTTP 200 in 0.18s; 3.5/3.1/3.6/3.8 visible |
| Gemini 3.5 Flash-Lite minimal text generation | HTTP 200 / 0.53s | HTTP 200 / 0.76s |
| Gemini 3.6 Flash minimal text generation | HTTP 200 / 1.14s | HTTP 200 / 1.99s |
| Gemini 3.1 Flash-Lite minimal text generation | timeout after 7s | timeout after 7s |
| FREE2 Gemini 3.6 Flash real 2-page hydraulics (8 reference rows) | Not tested in this stage | 5.958s OCR and matcher, 2.667s PDF preparation, correct department, 8/8 exact name matches |

A one-off FREE2 Gemini 3.6 real-doc probe earlier returned an error before a second successful probe. Neither a single success nor matching item names establishes handwritten **quantity** correctness or 20s including JEV. Production validation remains necessary.

## How to check without printing secrets

```bash
cd /root/Multiplexer/multiplekser
docker exec multiplekser-worker-1 python -c 'from app.core.config import settings;print("FREE1:",bool(settings.gemini_api_key_free),"FREE2:",bool(settings.gemini_api_key_free_2),"PAID_CONFIGURED:",bool(settings.gemini_api_key_paid))'
```

To run a **read-only** real-OCR check on FREE2 with default completed reference document:

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps worker python -m scripts.probe_gemini_free_pools --pool FREE2 --model gemini-3.6-flash
```

Keep a previous known working worker image for fast rollback. Do not run additional repeated API probes automatically; use actual production events plus Redis cooldowns to avoid unnecessary quota consumption. Production files/items must never be modified by the probe script.
