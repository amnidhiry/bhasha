# bhasha

A self-hosted language-learning app built around a precise learner model: FSRS
state for every word you know, used to rate and generate reading at your level.
Mandarin is the first language pack. The full design is in [`docs/design.md`](docs/design.md).

## Status

### Phase 1 PWA (in progress)

- [x] Reader as the home screen: segmented text with ruby pinyin over new and learning words (or all or none),
      word-status colors (dotted underline new, amber learning), punctuation kept on the line, text size, tone colors
- [x] Tap lookup sheet: spoken and written tones, HSK level, measure words, meanings, character
      decomposition with meaning and sound components, add to reviews / I know this / ignore
- [x] Review screen: meaning, reading and listening cards with context sentence, keyboard 1–4 and space.
      Ratings go to an offline outbox (client UUIDs) and sync when online
- [x] Offline scheduling with ts-fsrs pinned to FSRS-6 and the server's own parameters (`/api/reviews/params`):
      failed and new cards come back after their 1 and 10 minute steps with or without a connection.
      `backend/tests/test_fsrs_parity.py` checks it against py-fsrs
- [x] Progress: known words and characters, cumulative HSK 3.0 bars, placement marks per level
- [x] Installable PWA (manifest, icons, service worker caching the app and recent API reads), light and dark
- [x] Interim audio through the browser's Mandarin voice (built into iOS and macOS) until CosyVoice

### Phase 0 backend

- [x] Docker Compose skeleton (api + Postgres, optional Traefik overlay), Alembic migrations
- [x] Core schema: `unit`, `unit_relation`, `card`, `review_log`, `exposure`, `text`, `text_token`,
      `unit_mark`, `cedict_entry` (own table, CC BY-SA), `character_info`, `pack_version`, `llm_call`.
      Every per-learner table has `user_id`, so family use needs no retrofit
- [x] Importers: complete-hsk-vocabulary (HSK 3.0 Nov 2025 → `hsk3-2025:N` tags, plus 2021 and 2.0),
      CC-CEDICT, Make Me a Hanzi `dictionary.txt`. All idempotent and version-recorded
- [x] zh pack: jieba with curriculum user dictionary, Lute-style split rules, proper-noun and number
      detection, per-word pinyin with **citation and surface tones** (不, 一 and third-tone sandhi)
- [x] FSRS-6 (py-fsrs) with meaning and reading cards; a listening card is added once meaning reaches review
- [x] Review sync that is idempotent by client review id, with out-of-order offline reviews replayed from history
- [x] Daily review and new-card caps, the sibling-facet-per-day rule, leech flag
- [x] Reader API: paste import with coverage, word status (new, learning, known, ignored), finish → exposures
- [x] Lookup (HSK data, CC-CEDICT, decomposition). A tap on a carded word logs an unscheduled failed review
- [x] Mining requires a context sentence or text; placement bulk-marking by HSK level
- [x] Progress: known words and characters, cumulative HSK coverage, characters read

Next: the LLM gateway and graded-reader generator with its repair loop, the arq worker, the
nightly FSRS optimizer, then SUBTLEX-CH and Tatoeba imports, g2pM for polyphones, and the sound bootcamp.

## Run it

```bash
cp .env.example .env   # set POSTGRES_PASSWORD
```

```bash
./ops/fetch-data.sh
```

```bash
docker compose up -d --build
```

```bash
./ops/import-data.sh
```

The app is at http://localhost:8000/ and the API under `/api` (docs at `/api/docs`). For nightly
backups, add `ops/backup.sh` to cron.

To install it on iPhone, iPad or Mac (Share, then Add to Home Screen / Add to Dock), serve it over
HTTPS through Traefik. Browsers only enable the service worker and offline caching in a secure
context. Over plain `http://<lan-ip>:8000` the app still works, but only online.

## Develop

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]' && pytest
```

Without `BHASHA_DATABASE_URL` the API uses SQLite (`bhasha.db`). Run `alembic upgrade head` first.

```bash
cd web && npm install && npm run dev   # http://localhost:5173, proxies /api to :8000
```

## Layout

```
backend/app/
  models.py         core tables
  learner.py        FSRS mapping, replay, knownness, coverage
  reader.py         analyze → resolve units → coverage → serialize
  packs/base.py     language-pack interface (core never branches on language)
  packs/zh/         jieba segmentation, pinyin + sandhi, split rules
  importers/        hsk, cedict, hanzi
  api/              reviews, texts, lookup, mine, progress (mounted under /api)
web/src/
  views/            Library, Reader, Review, Progress
  components/       LookupSheet, Pinyin (tone colors), Sheet, TabBar, Toast
  outbox.ts         offline review queue with client UUIDs
  speech.ts         interim browser TTS
  public/sw.js      service worker
```

## Data licenses

CC-CEDICT is CC BY-SA 4.0 (kept in its own table, attributed in lookups). Make Me a Hanzi's
`dictionary.txt` and `graphics.txt` are licensed separately (graphics: Arphic PL).
complete-hsk-vocabulary, jieba, pypinyin and py-fsrs are MIT.
