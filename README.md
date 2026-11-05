# bhasha

A self-hosted language-learning app built around a precise learner model: FSRS
state for every word you know, used to rate and generate reading at your level.
Mandarin is the first language pack. The full design is in [`docs/design.md`](docs/design.md).

## Status

### Phase 1 PWA (in progress)

- [x] Tutor (Write → Talk): role-play scenarios (ordering food, directions, shopping, taxi, meeting someone, booking
      by phone, seeing a doctor, free chat) with a goal and a twist. Replies are checked against your known and
      level words and rewritten once if they stray; your messages are corrected inline and mistakes become cloze
      cards through the journal's pipeline. Pinyin over unfamiliar words, tap to look up, audio, English and a hint

- [x] Journal (Write tab): write a few sentences with a daily idea and your recent words; the model corrects them in
      the background with a minimal fix, English and one-line explanations per mistake. Each mistake is checked
      against your text before it counts, then becomes a fill-in (cloze) review card from your corrected sentence.
      A character diff shows what changed, and mistakes are counted by category (了/过/着, measure words, word
      order...)
- [x] Importer (Read → Import): paste, a link (article text extracted with trafilatura; http(s) only, 2 MB cap,
      no private or local addresses unless listed in `BHASHA_IMPORT_ALLOW_HOSTS`), an EPUB chapter or range of
      chapters (TOC titles, ruby pinyin stripped), SRT/VTT subtitles (timestamps and tags removed, Chinese
      lines kept from bilingual files, long files split into ~1,500-character parts) and subtitles from your
      Jellyfin (`BHASHA_JELLYFIN_URL`, `BHASHA_JELLYFIN_API_KEY`). Every source shows "62% known · 3,400
      characters" before you add it
- [x] Characters (Progress → Characters, or tap a character in the lookup sheet): a page per character with
      stroke-order animation, Make Me a Hanzi parts and their roles, readings, frequency and your words with it;
      a component explorer ("every character you know with 氵", variants such as 氵/水 and 钅/金 count as one
      family, parts of parts too); your characters grouped by their most common parts. Gentle notes flag
      "opaque" characters whose parts mislead: a sound part that shares neither initial nor rhyme with the
      reading (银 yín, 艮 gěn), or a part a meaning compound's story never uses (又 in 汉)

- [x] Server-side speech: a separate speech service (`speech/`, Kokoro, CPU container on the homelab) that bhasha
      calls over HTTP. Every clip is cached on the homelab; new texts are pre-rendered sentence by sentence in the
      worker; the PWA falls back to the device voice when no host answers. Several hosts can be listed in order,
      so a GPU PC can go first with the homelab CPU as backup (`speech/windows/README.md`). Progress → Voice
      runs a tone check that synthesizes test syllables and scores their pitch, so you pick a voice that gets
      tones right

- [x] Nightly FSRS re-fit: once you have 400 reviews, the worker fits FSRS-6 to your own log (then monthly, or
      when the log grows by a quarter). New parameters are used only if they predict held-out cards better
      (log loss and binned RMSE, as srs-benchmark scores them); every attempt and its numbers is in Progress →
      Scheduling. It also suggests a target recall that minimizes study time, which you can accept with a tap. The
      server and the PWA's offline scheduler switch together. PyTorch (CPU) is in the worker image only

- [x] SUBTLEX-CH word frequencies (99k words) rank every word the HSK list doesn't, shown as "#1,003 most
      common" in the lookup sheet
- [x] Tatoeba example sentences (human-written, CC BY 2.0 FR, Simplified only, each linked to its source):
      three per word in the lookup sheet, ranked by how much of each you can read; a second example on review
      answers; and "Real sentences", a reading text of 8 sentences with at most one unknown word each that
      prefers your learning words and never repeats

- [x] Sound bootcamp (Sounds tab): the four tones with pitch-contour diagrams and English-speaker cues, then
      initials and finals that aren't English (aspiration, j/q/x, zh/ch/sh/r, z/c/s, ü, -n/-ng). Drills:
      which tone, tone pairs on HSK words (answered as spoken, after sandhi), tone changes (3-3, 不, 一), and
      14 minimal-pair contrasts. Weak tones and contrasts come up more, and a drill counts as mastered at
      85% over your last 20. "Say it" records you and draws your pitch against the target tone, with a
      tone guess as a hint (YIN pitch tracking in the browser; the microphone needs HTTPS)

- [x] Handwriting track: Review → Writing is its own daily session (separate caps: 5 new, 40 total). You write
      from memory on a 田字格 grid with Hanzi Writer; mistakes map to a suggested rating (0 Good, 1–2 Hard,
      3+, a hint or giving up Again) that you confirm. Apple Pencil palm rejection is on: in Pencil-only mode
      finger touches are ignored, switched on automatically the first time a Pencil touches the pad. Characters
      come from the official HSK 3.0 handwriting list (Progress → Handwriting → Add the next 5) or a Write
      button on any character in the lookup sheet. Stroke data is served by the API, not a CDN, and cached
      for offline use

- [x] Background worker: generation is queued as a job (a Postgres table with `SKIP LOCKED`, no Redis) and run by
      the `worker` container. The library shows progress and "Ready" when done, plus Retry for failures.
      Jobs survive restarts, and a job orphaned by a crashed worker is requeued after 15 minutes

- [x] Graded-reader generator: "Write me a text" with topic, kind (story, dialogue, everyday, news), length
      and words to practise. Every word is checked against what you know plus an HSK level pool, with up to
      two rewrites naming the exact words to replace. The reader adds English per sentence, a flag-as-unnatural
      button and comprehension questions
- [x] LLM gateway with **Sign in with ChatGPT** (your Plus or Pro plan, no API key; adapted from SurfSense,
      Apache-2.0) or any OpenAI-compatible endpoint (LM Studio, API key). Tokens are encrypted at rest; there's
      a daily call cap and per-call usage logging

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

Next: g2pM for polyphones.

## Run it

```bash
cp .env.example .env   # set POSTGRES_PASSWORD, BHASHA_SECRET_KEY (openssl rand -hex 32) and BHASHA_SPEECH_TOKEN
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

To generate texts, open Progress → Text generation → Sign in with ChatGPT. Approve bhasha in the tab that
opens. That tab then fails to load an `http://127.0.0.1:1455/callback?...` address, which is expected: copy that
address and paste it back into bhasha. OpenAI calls Sign in with ChatGPT a preview, and usage counts toward your
plan's limits.

**Recorded voices (optional):** the Sounds tab uses your device's Mandarin voice until you add Tone Perfect
(Michigan State University, open access; cite it if you share work that uses it). Download it from
https://tone.lib.msu.edu, unpack the MP3s anywhere under `data/toneperfect/` (files are named like
`ma3_FV1_MP3.mp3`), then run `./ops/import-data.sh`. Drills then play six different speakers at random.

**Speech:** the `speech` container runs Kokoro on the homelab's CPU and downloads its weights (~330 MB) on first use.
After the first start, open Progress → Voice and press **Check tones**. To use a GPU PC as well, follow
`speech/windows/README.md`, then list it first:
`BHASHA_SPEECH_URLS=http://<pc>:8790,http://speech:8790`.

There are no native apps: the PWA is the app on iPhone, iPad and Mac. To install it on iPhone, iPad or Mac (Share, then Add to Home Screen / Add to Dock), serve it over
HTTPS through Traefik. Browsers only enable the service worker and offline caching in a secure
context. Over plain `http://<lan-ip>:8000` the app still works, but only online.

## Develop

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]' && pytest
```

Without `BHASHA_DATABASE_URL` the API uses SQLite (`bhasha.db`). Run `alembic upgrade head` first. Either run
`python -m app.worker` alongside the API, or set `BHASHA_INLINE_JOBS=true` to run jobs inside the API process.

The FSRS-fit tests need PyTorch (`pip install -e '.[optimizer]'`) and are skipped without it. The tests use
SQLite by default. To run them on Postgres, which also covers the concurrent-claim test:

```bash
BHASHA_TEST_DATABASE_URL="postgresql+psycopg://bhasha@/bhasha_test?host=/run/postgresql" pytest
```

```bash
cd web && npm install && npm run dev   # http://localhost:5173, proxies /api to :8000
```

## Layout

```
speech/                speech service (FastAPI + Kokoro); windows/ has GPU-PC scripts
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

CC-CEDICT is CC BY-SA 4.0 (kept in its own table, attributed in lookups). The HSK 3.0 handwriting lists come from
krmanik/HSK-3.0, transcribed from the official syllabus. Tatoeba sentences are CC BY 2.0 FR and link to
their source pages. SUBTLEX-CH (Cai & Brysbaert, 2010) is a research dataset; cite it if you publish anything. Make Me a Hanzi's
`dictionary.txt` and `graphics.txt` are licensed separately (graphics: Arphic PL).
complete-hsk-vocabulary, jieba, pypinyin and py-fsrs are MIT.
