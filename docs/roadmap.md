# Roadmap: remaining medium and large features

Nov 5, 2026 · research notes for the next build sessions

This plans the ten features still open after phase 1 (see `README.md` for what's built, `docs/design.md` for the
why). For each one: the goal, an approach that fits the existing code, open components and their licenses, the
data it needs, effort, risks, dependencies and how to test it. The recommended order and sources are at the end.

**Effort** is S, M or L with a rough count of build sessions. A session means a focused build like the ones that
produced the journal or the importer: about one feature slice with tests.

**Verification.** Many primary sites couldn't be fetched from the research sandbox: chinesetest.cn, huggingface.co,
developers.openai.com, mandarin.ac.cn and mdbg.net. Facts that rest only on search summaries or third-party pages
are marked *(unverified)*. The section "What couldn't be verified" collects them.

## At a glance

| # | Feature | Size | Sessions | Depends on | Unlocks |
|---|---|---|---|---|---|
| 1 | Production, tone and component cards | M | 3–4 | none (tone production gets better with #6) | Opt-in production, bootcamp → vocabulary bridge |
| 2 | Grammar track | M–L | 4–5 | #5 helps (examples) | Journal errors raise grammar priority; generator targets grammar |
| 3 | Listening mode and dictation | M | 2–3 | Speech cache (built) | Listening minutes, dictation cards |
| 4 | Minutes and "coverage of typical texts" | S–M | 2 | none | Honest progress; data you can't backfill later |
| 5 | Batch enrichment | S–M | 2 | Job queue, gateway (built) | Examples for grammar and listening |
| 6 | Speech recognition and tone scoring | L | 6–8 | GPU PC optional | Tone production cards, voice tutor, shadowing scores |
| 7 | Voice tutor | M | 3 | #6 | Speaking practice for the HSK 3 speaking test |
| 8 | Medical Chinese track | L | 6–8, plus content | Core at HSK 3–4, #2, #7 | MCT prep, standardized-patient practice |
| 9 | Family logins | M | 3 | none | Second learner |
| 10 | Progress export for vidya | S | 1–2 | #4 (for minutes), #9 (tokens) | One dashboard across apps |

---

## 1. Card types without UI: production, tone, component

**Goal.** Finish the card types the design defines but the review screen can't show yet. `mine.py` already
accepts `tone` and `production` in `ALLOWED_FACETS`, and `Unit.type` already allows `component`.

### Production (English cue → type the Chinese)

- **Prompt.** Show the English gloss plus the English translation of the card's context sentence. A single gloss is
  ambiguous: 知道 and 认识 both translate as "know". When you have carded words that share a gloss, add a
  "not 认识" hint, using CC-CEDICT gloss overlap among your own cards.
- **Input.** A plain text field. On iPhone, iPad and Mac the system pinyin keyboard is the IME, so we don't build
  one. That also matches the design: "most daily writing is pinyin input". Accept typed pinyin with tone numbers
  as a fallback for devices without a Chinese keyboard, and grade that as a reading answer.
- **Grading.** Same model as handwriting: the app suggests a rating and you confirm it.
  - Exact headword (simplified or traditional) → Good.
  - Right syllables but the wrong character picked from the IME (a homophone) → Hard, and the character diff
    (`web/src/diff.ts`) shows which character.
  - Another word you know with an overlapping gloss → no rating yet. Say "right idea, we wanted 认识", then reveal
    and let you rate.
  - Anything else → Again.
- **Default.** Opt-in per word, as the design says. Offer it in bulk ("turn on production for my HSK 1 words once
  meaning is in review") from the progress page.

### Tone cards (words with 2+ syllables)

- **Perception (build now).** Play the word: the cached server TTS clip, which the tone check has already shown
  gets tones right, or the device voice as fallback. The answer is one tone picker per syllable (1–4 plus neutral),
  so a two-syllable word is two taps. Grade against **surface** tones from the zh pack (`citation_syllables` plus
  the sandhi rules already used by the bootcamp's tone-pair drill). All right → Good. One syllable wrong → Hard
  (you confirm). More → Again.
- **Production (basic now, real after #6).** Reuse `SayIt.tsx`. Record, track pitch with YIN (already in the
  browser and in `backend/app/tonecheck.py`), split the voiced stretch into N equal parts for N syllables, and
  classify each part with `tonecheck.classify`. Show the score only as a hint next to the contour. After #6, forced
  alignment replaces the equal split and the score becomes worth trusting.
- **When the card appears.** On during the bootcamp. After that it is added automatically for words with repeated
  tone trouble: two or more failed reading reviews in 30 days, or a weak tone pair in `DrillAttempt` that the word
  contains. This is the "words with repeated tone errors" rule in the design.

### Component cards

- **Prompt.** The component (for example 氵) → its meaning or sound role. The answer shows the Make Me a Hanzi
  meaning hint, your known characters with it (the component explorer already computes this) and any "opaque"
  notes.
- **Creation.** Only for productive components: once a component appears in **three or more** characters you have
  carded. The design says "first appearance", but that would create cards for parts like 丶 that teach nothing.
  Treat variants as one family (氵/水), as the explorer already does.
- **Retention.** Desired retention 0.8, since this is scaffolding, not an end skill. The per-facet retention
  setting already exists in the design.

**Open components.** None new. ts-fsrs and py-fsrs (MIT) are already in use; Hanzi Writer isn't needed here.

**Data.** CC-CEDICT glosses (have), Make Me a Hanzi decompositions (have), surface tones (have).

**Effort.** M, 3–4 sessions: production 1, tone perception 1, basic tone production 0.5, component cards 1, plus
the review-screen prompts.

**Risks.**
- Production cards double the review load if they're turned on wholesale. Keep them opt-in and count them against
  the same daily cap.
- Equal-split tone scoring is often wrong on fast or creaky speech (third tones). Label it "rough" until #6.

**Testing.**
- Unit tests for the production grader: exact match, traditional form, homophone, synonym and wrong answer.
- Tone answer-key tests on sandhi cases: 你好 → 2-3, 不是 → 2-4, 一个 → 2-4 (or 2-neutral, whichever the
  pack's dictionary gives; the card must agree with the pack, not with a hard-coded answer).
- Component creation threshold and variant merging.
- A Playwright-style smoke test of each card on the review screen with the keyboard.

---

## 2. Grammar track

**Goal.** Make grammar points real knowledge units with FSRS cards, detected in texts, targeted by the generator,
and raised in priority when the journal or tutor sees you get them wrong.

### Source inventory

The official HSK 3.0 syllabus (the 2021 standard, revised November 2025) includes a grammar inventory.
`krmanik/HSK-3.0` has it per level as text and JSON in `New HSK (2025)/HSK Grammar/`. I checked the JSON
directly:

| Level | Entries | Examples of what lands there |
|---|---|---|
| HSK 1 | 70 | 了1 (completion), 了2 (change), 在/正在…呢, 是/有 sentences, 不 vs 没 |
| HSK 2 | 78 | 过 (experience), 着 (continuous state), 是…的 (emphasis on time, place, manner), 比 comparisons, result and direction complements, 得 complements of state |
| HSK 3 | 96 | 把 sentences (three patterns), 被 passives, potential complements (V得/不V), 越…越, 除了…以外 |
| HSK 4 | 95 | More 把 patterns, 叫/让 passives, rhetorical questions (难道…吗) |

Each entry has a category (类别: 语素, 词类, 短语, 固定格式, 句子成分, 句子的类型, 动作的态, 特殊表达法), a subcategory
and content. Two kinds of entries need different handling:

- **Lexical entries** list words, for example modal verbs 会、能 or measure words 本、个、家. These are not new units.
  Tag the existing word units (`unit.extra["grammar"]`) so the generator and the grammar page can show them, but
  don't make grammar cards for them. Their word cards already exist.
- **Structural entries** are patterns: aspect, complements, 把/被, 是…的, comparisons, complex sentences. Each
  becomes `Unit(type="grammar")` with:
  - `headword` as a stable ID, for example `hsk2025.2.持续态.着`;
  - `level_tags=["hsk3-2025:2"]`;
  - `extra` holding the Chinese pattern, an English name and explanation, contrast-set IDs, a detector name and a
    Chinese Grammar Wiki link.

That gives roughly 150–200 structural points for HSK 1–4, a manageable number to hand-check.

**Licensing.**
- The syllabus is an official standard. `krmanik/HSK-3.0`'s `License.md` cites the Ministry of Education and CTI
  PDFs as the source and gives CC BY-SA 4.0 for the author's word lists, but doesn't name a license for the
  grammar files. Treat them as CC BY-SA: keep the import in its own data file, version-tagged, attributed, the same
  way as CC-CEDICT.
- **Chinese Grammar Wiki** is CC BY-NC-SA. Link to it from each point and don't copy its text in. English
  explanations are ours, written once per point by the LLM through the batch enrichment job (#5) and spot-checked.

### Detection

A grammar point is "seen" in a text when a detector matches it. A detector is a small rule over the zh pack's
tokens, with jieba's POS tags where needed. For example:

- 把-sentence: 把 followed by an NP, then a verb;
- V了 vs sentence-final 了;
- V过;
- V着;
- 是…的 with 的 before final punctuation;
- V得 + adjective;
- potential complement V得/不 + result or direction morpheme.

Write detectors for about 40 high-value points first: everything in aspect, complements, 把/被, 是…的, comparisons
and the common paired conjunctions. The rest get a detector when needed. Detectors live in the language pack
(`packs/zh/grammar.py`), so the core only sees `pack.detect_grammar(tokens) -> list[point_id]`.

Detections feed three places:

- **Exposures.** Store them in the existing `exposure` table, keyed on the grammar unit. That gives weak evidence,
  exactly like words.
- **Generator.** The generator's JSON schema gets `grammar_points_used`. The claim is accepted only if the
  detector agrees, the same "trust the text, not the list" rule the journal uses. The brief gets "practise 把 this
  week" when a point is weak.
- **Reader.** A small underline or chip on matched spans, tap → the grammar point sheet with the English
  explanation and a Grammar Wiki link.

### Cloze generation

- **First choice: human sentences.** Scan Tatoeba sentences (already imported, CC BY 2.0 FR) with the detectors.
  Keep those at or above your level's coverage and gap the marker (了/过/着, 把, 被, 的/得/地, a complement).
- **Distractors come from a contrast set, not random words:**
  - 了 / 过 / 着 / 在;
  - 的 / 得 / 地;
  - 把 / 被 / 给;
  - 就 / 才;
  - 再 / 又 / 还;
  - 不 / 没;
  - 比 / 跟…一样 / 没有.

  Contrasts are exactly what English speakers get wrong ("aspect, not tense" in the design).
- **Fallback: the LLM.** If Tatoeba has too few sentences for a point, generate them in batch (#5). Run the same
  detector and coverage check, and mark them `generated`.
- **Card shape.** Reuse the existing cloze facet (`cloze:<id>`, `Card.cloze` JSON), so the review screen needs only
  a "choose from the contrast set" variant. Keep one grammar card per point (`facet="cloze"`), drawing a different
  sentence each review, so FSRS schedules the *point*, not the sentence. Journal cloze cards stay
  sentence-specific, as now.

### Journal and tutor errors → grammar priority

`journal.record_sentence` already verifies each error and makes a cloze card. Extend it:

1. **Tag errors with a point.** Add an optional `grammar_point` field to the correction schema. Its enum is the
   point IDs (with short English names) at or below your level plus one level. The prompt grows by about 2 KB.
2. **Verify the tag.** Accept it only if the point's detector matches the corrected span and doesn't match, or
   matches differently, in the original. Otherwise fall back to a category-based guess:
   - `aspect_particle` → the 了/过/着 point detected in the corrected sentence;
   - `measure_word` → the measure word's word unit.
3. **Raise priority without bending FSRS.** Log an **unscheduled failed review** on the point's card, the same
   rule the reader already uses when you tap a carded word. If the point has no card yet, create it (it was
   evidently "in play"). Then add the point to the generator's target list for the next few texts, and to "Real
   sentences" selection.
4. **Show it.** The journal page currently counts categories. Add "points you've missed most this month", linked
   to the point sheet.

**Data.** krmanik grammar JSON (fetch in `ops/fetch-data.sh`), Tatoeba (have), English explanations (generated in
batch, about 200 calls' worth at most), Grammar Wiki URLs (a hand-made mapping of about 150 lines; Wiki pages are
organized by CEFR-like levels A1–C1, not HSK).

**Effort.** M–L, 4–5 sessions:
- importer and unit model: 1;
- 40 detectors with tests: 1–2;
- cloze builder and review variant: 1;
- journal/tutor linkage and generator targeting: 1.

**Risks.**
- **Detector precision.** 了1 vs 了2 is genuinely ambiguous: in 我吃了 the 了 is both. Accept "either" where the
  syllabus does, and test detectors on a hand-labeled set.
- **Inventory drift.** The November 2025 revision moved points between levels; it's version-tagged like the word
  lists.
- **Card bloat.** Create grammar cards only when a point is due by level and has been seen in at least two texts,
  or when you make an error on it.

**Testing.**
- A gold file of about 300 sentences labeled with point IDs. Report detector precision and recall per point in
  pytest, and fail if precision for a point drops below 0.9.
- Journal tests with canned model output where the tag is right, wrong (rejected) and missing (fallback).
- Cloze distractor tests: the answer is never among the distractors; the distractors come from the contrast set.

---

## 3. Listening mode and dictation

**Goal.** Audio-first practice: listen to a text without the transcript, then reveal it; dictation of sentences
built from words you know.

**Evidence.**
- Shadowing has the better Mandarin-specific support. A 2024 study in the *Journal of Second Language
  Pronunciation* had beginners shadow either textbook audio or authentic video. Both groups improved tone accuracy
  in spontaneous sentence-level speech, with no difference between materials (Lu et al., 2024).
- A 2025 systematic review finds shadowing reliably helps L2 listening and probably helps pronunciation control.
- I found no good study of dictation for L2 Chinese specifically. Treat dictation as an integrative check
  (sound → word → character) rather than a proven intervention, and keep sessions short.
- The design already plans "shadow a few sentences from today's text" in the daily session.

### Listening mode (in the reader)

- A "Listen" toggle on any text: sentences play one by one from the **server TTS cache** (`speech.get_clip`; new
  texts are already pre-rendered sentence by sentence). Speed 0.8 or 1.0. The transcript is hidden.
- Per sentence there are three buttons:
  - **Replay**;
  - **Reveal**, which shows the sentence with pinyin over new words;
  - **Got it**.
- Revealed or replayed-three-times sentences are listed at the end as "tricky sentences" with one-tap mining.
- When a text is finished in listening mode, log exposures with `mode=listening` (a new column, default
  `reading`), so listening knowledge gets its own weak evidence.
- Several Kokoro voices, rotated per text, give talker variability. As the design notes, that helps only after
  explicit tone teaching.

### Dictation

- **Sentence source.** "Real sentences" (Tatoeba) at 100% known-word coverage, or the current text's sentences.
  Start at 4–8 characters.
- **Answer.** Type with the system IME. Beginners can toggle "answer in pinyin".
- **Scoring.** Split the scores so feedback is honest:
  1. **Normalize** both strings: strip punctuation and spaces, convert full-width to half-width, Arabic numerals
     and Chinese numerals both ways (2 ↔ 二/两), and fold traditional characters to simplified.
  2. **Character score.** Levenshtein alignment at the character level (`diff.ts` already does a character diff).
  3. **Listening score.** Map both strings to toneless and toned pinyin per word with the pack. Compare
     syllable-aligned.
     - A character wrong but its syllable and tone right is a **homophone slip**: you heard it right and picked
       the wrong IME candidate. It counts as a listening success and a character miss.
     - Right syllable, wrong tone is a **tone miss**.
     - Wrong syllable is a **listening miss**.
  4. **Rating.** Map to a suggested rating for the sentence's words: listening misses → an unscheduled failed
     *listening* review on that word's card, if there is one; homophone slips → nothing on listening, optionally
     a note to the meaning or production card.
- **Tolerance for homophones** is therefore built in, but surfaced, never silent. Accept known variant pairs as
  correct: 那里/那儿, 哪里/哪儿, 一点/一点儿, 他/她/它 (the audio can't tell them apart). Keep this as a small pack
  data file.
- **Daily writing link.** The handwriting track's "write two or three sentences from today's text from dictation"
  can reuse the same player with Hanzi Writer as the input.

**Open components.** Kokoro (Apache-2.0, already used). Nothing new.

**Data.** Tatoeba (have), cached audio (have), variant pair list (small, hand-made).

**Effort.** M, 2–3 sessions: listening mode 1, dictation scoring and UI 1–1.5, exposure mode and stats 0.5.

**Risks.**
- **TTS errors.** TTS mistakes in tones or polyphones become listening "truth". Only Kokoro voices that pass the
  tone check are used. Polyphone errors (行, 长) need g2pM, the README's next item, or the speech service's
  phoneme input if the engine supports it.
- **Audio unlock on iOS.** iOS needs a user gesture to start audio. Unlock one shared `<audio>` element on the
  first tap.

**Testing.**
- Scorer unit tests covering exact match, homophone slip (在/再), tone miss, numerals, traditional input,
  punctuation, missing and extra characters, and variant pairs.
- An end-to-end test that a dictation result writes the expected unscheduled reviews.

---

## 4. Minutes read and listened; estimated coverage of typical texts

**Goal.** Two honest progress numbers from the design's Progress module. "No streak guilt", so the numbers report
and never nag.

### Minutes, measured honestly

A PWA can't see your eyes, so count **active time** and say how it's counted:

- **When the clock runs.** The reader or listener is in an *active* state when all of these hold:
  - the page is visible (`document.visibilityState === "visible"`; the `visibilitychange` event works in Safari);
  - the window has focus;
  - there was input in the last *T* seconds.
- **What counts as input.** Scroll, tap, keypress, audio playing or pointer movement.
- **The idle timeout T.** It adapts: the estimated time to read what's on screen, at your measured
  characters-per-minute, capped at 90 seconds, with a 30-second minimum. Some guess is unavoidable. One that scales
  with the amount of text is fairer than a fixed 60 seconds.
- **No Idle Detection API.** It's Chromium-only (no Safari) and needs a permission. Use input events instead.
- **Listening.** Count only time the audio is actually playing, with no idle rule.
- **Storage.** The PWA keeps segments `{text_id, mode, start, end}` locally and sends them through the same offline
  outbox as reviews (client UUIDs, idempotent). The server merges overlaps and caps a segment at 30 minutes without
  input.
- **Display.** "Minutes read (active)" for the week and month, characters read, and a one-line note in Progress on
  how it's measured. Characters read already exists. Make it count only sentences that entered the viewport
  (IntersectionObserver) during active time, not the whole text on Finish.

### Estimated coverage of typical texts

"Of the running words in typical subtitles, you'd know about X%". This is the same token coverage the generator
uses, applied to reference corpora:

1. Keep a few **reference samples**, each segmented once with the zh pack and stored as `(unit_id, count)`:
   - **Subtitles:** SUBTLEX-CH frequencies (have; the word list, not running text, so restrict to words the pack
     knows and weight by frequency).
   - **Everyday sentences:** all of Tatoeba cmn (have).
   - **News:** the Leipzig Corpora Collection news sample. Its download terms say CC BY *(unverified for the
     Chinese files; one catalog lists CC BY-NC)*. Alternatively, your own imported articles.
   - **Your own imports**, so the number reflects what you actually read.
2. **Coverage.** `Σ count(known units) / Σ count(countable units)`, excluding proper nouns and numbers, as in the
   design. Also show an **expected** version, `Σ count × p_recall` (FSRS retrievability, 1.0 for marked-known).
   It moves smoothly instead of jumping at the 0.9 threshold.
3. **Thresholds.** Show them as dial marks: 95% (listening, Webb et al.) and 98% (unassisted reading, Hu & Nation),
   with the design's caveat that these are dials, not laws.
4. **Schedule.** Recompute nightly in the worker; the numbers change slowly.

**Effort.** S–M, 2 sessions: activity tracker and outbox segments 1, reference coverage job and Progress cards 1.

**Risks.** Time inflation from a phone left open on the reader. The adaptive idle cap bounds it, and the method is
shown. SUBTLEX segmentation differs from jieba's, so subtitle coverage is approximate; say so in the label.

**Dependency note.** Do this **early**. Review logs can be replayed, but minutes that weren't recorded can't be
reconstructed.

**Testing.**
- Pure-function tests of the activity state machine with fake timers: hidden tab, idle, audio playing, iOS
  `pagehide`.
- Server merge and overlap tests.
- Coverage on a toy corpus with known answers; the binary and expected variants agree when recall is 0 or 1.

---

## 5. Batch enrichment (examples and usage notes)

**Goal.** Example sentences and short English usage notes for HSK 1–4 words, and English explanations for grammar
points (#2), made slowly in the background through the ChatGPT plan, which has no batch discount.

### Volume

HSK 1–4 is 2,000 words (November 2025 lists). Most already have Tatoeba sentences. Enrich only words with fewer
than two Tatoeba sentences at your level, plus words you've mined, plus the ~200 grammar points. Batched 15–20
words per call, that is **about 100–150 calls in total**. That fits easily in a week of nightly runs.

### Throttling

The design's gateway already has a daily cap (`BHASHA_LLM_MAX_CALLS_PER_DAY`, default 300) and a `PlanLimitError`.
Add:

- A **separate budget** for background jobs, for example 40 calls a day, so interactive features (journal, tutor,
  generator) always keep headroom.
- A **time window**: the worker runs enrichment only between 01:00 and 06:00 local time and never while you're
  active (an API request in the last 10 minutes).
- **Backoff.** On `PlanLimitError`, stop the batch until the next window. Don't retry in a loop. OpenAI's consumer
  terms forbid circumventing rate limits, and Sign in with ChatGPT is a preview program, so be a polite client.
- **LM Studio as an alternate.** The gateway can route the `enrichment` feature to LM Studio on the GPU PC when it's
  online. A local Qwen-class model writes acceptable simple Chinese, and its output still goes through the same
  checks.

### Quality

The model writes; code checks:

1. **Structure.** JSON schema per word: `sentences[{zh, en}]` and `note`.
2. **Hard checks.**
   - The target word must appear **as a segmented token**, not just as a substring.
   - Every other word must be within your level pool plus one.
   - Length must be 6–20 characters.
   - No duplicate of an existing Tatoeba sentence.
   - The pack supplies pinyin, never the model.
3. **Soft checks.** A second, cheap model call isn't worth it on a capped plan. Instead, **sample**: one in ten
   accepted items goes into a small "Check these" list in Progress, with ✓ and flag buttons.
4. **Per-batch acceptance rate.** Track it. If more than 10% of a batch is flagged, pause the job and show the
   rate.
5. **Flags.** Flagged sentences are excluded everywhere, like the reader's "flag as unnatural".
6. **Storage.** Put generated examples in `example_sentence` with `source="generated"`, the model name and the date.
   Tatoeba stays first in ranking; generated sentences fill gaps.

### Licensing of outputs

- OpenAI's consumer Terms of Use (January 2026) say you own the output, to the extent the law allows. They also say
  outputs may not be unique, and output may not be used to develop competing models.
- For personal use that's fine. Keep provenance on every row, so that if the app or a dataset were ever shared,
  generated content can be separated or dropped.
- CC-CEDICT glosses sent in prompts are fine. Don't present generated sentences as Tatoeba's.

**Effort.** S–M, 2 sessions: job type, budget and window 1, checks and sampling UI 1.

**Risks.** Unnatural Chinese that passes the checks. Sampling plus flags plus Tatoeba-first ranking limit it. Plan
limits changing under a preview program is a second risk: the job just waits.

**Testing.**
- Checks with canned outputs: target missing, target only as a substring (e.g. 天 inside 天气), out-of-level word,
  duplicate.
- Budget and window logic with a frozen clock.
- Pause at the flag threshold.

---

## 6. Speech recognition and tone scoring

**Goal.** Score spoken answers: "did you say the right syllables, and were the tones right?" Also transcribe free
speech for the voice tutor (#7). These are **two different jobs**, and the key design decision is to keep them
apart:

- **Transcription** ("what did you mean?") wants a strong ASR with a strong language model. It reconstructs your
  intent from imperfect speech, which is what a tutor needs.
- **Pronunciation scoring** ("what did you actually say?") is *hurt* by that same strength. Studies on L2 English
  find large ASR models transcribe what a native listener would understand, masking errors. Smaller models'
  "mistakes" are better evidence of learner errors (ICNLSP 2023 on Whisper). Recent work calls this "intent bias"
  *(abstract only seen)*. So for scoring, use the **known target text**, force-align it, and judge each syllable
  acoustically, rather than trusting what an ASR printed.

### Candidate models (as of November 2026)

| Model | Size | License (weights) | Mandarin accuracy (reported) | Timestamps | Runs on |
|---|---|---|---|---|---|
| **SenseVoice-Small** (FunAudioLLM) | 234M, non-autoregressive | FunASR Model License v1.1 (see below); code MIT | AISHELL-1 CER ≈ 3.0 | Yes (`output_timestamp`) | CPU fine; ONNX via sherpa-onnx (Apache-2.0); GGUF build |
| **Paraformer-zh** (FunASR) | 220M | FunASR Model License | Strong on read speech | Yes, character-level | CPU fine; sherpa-onnx; FunASR CPU runtime Docker |
| **Fun-ASR-Nano-2512** | 0.8B, LLM-based | Apache-2.0 per its model card *(per the repo's README)* | AISHELL-1 1.80, FLEURS-zh 2.56 | Character timestamps with the ModelScope checkpoint only | GPU best; llama.cpp/GGUF CPU binary exists |
| **Qwen3-ASR 0.6B / 1.7B** (Jan 29, 2026) | 0.6B / 1.7B | Apache-2.0 | 1.7B: AISHELL-1 ≈ 1.5; avg ≈ 3.8 across 4 Mandarin sets (FireRed's table) | Via **Qwen3-ForcedAligner-0.6B** (Apache-2.0, Chinese included) | GPU (CUDA); vLLM for streaming; Transformers support since June 2026 |
| **FireRedASR2-AED / -LLM** (Feb 2026) | ~1.1B (AED) | Code Apache-2.0; weights license not confirmed (Hugging Face blocked) | Claims best Mandarin avg CER ≈ 3.05 (AED) / 2.89 (LLM), self-reported | AED: word timestamps and confidence | GPU; TensorRT-LLM / vLLM |
| **Whisper large-v3-turbo** via faster-whisper / whisper.cpp | 809M | MIT (weights and both runtimes) | AISHELL-1 CER ≈ 8.6 untuned (BELLE's table); BELLE's zh fine-tune ≈ 3.1 | Word timestamps | CPU slow-ish, GPU fine |

**Reading of the table.** For Mandarin, Whisper is now clearly behind the Chinese-native models. It also mixes
simplified and traditional output (one `zh` token for all variants) and hallucinates on silence. Keep it only as a
fallback engine.

**FunASR model license.** I checked the text (v1.1).
- It permits use, copying, modification and sharing, but requires attribution and keeping model names.
- Its terms update automatically when the repo publishes new ones.
- Oddly, all rights are forfeited for "unjustified denigration, malicious smearing, or baseless insults" of the
  software.
- It doesn't address commercial use directly, though SenseVoice maintainers have said commercial use of the
  official weights is allowed under it.

For a personal homelab this is acceptable. It is, however, the least clean license in the table. Fun-ASR-Nano and
Qwen3-ASR (Apache-2.0) avoid it.

### Recommended stack

**CPU tier (homelab, always on).**
- Add an `asr` engine to the existing speech service (`speech/bhasha_speech/engines/`), alongside Kokoro.
- Use **sherpa-onnx + SenseVoice-Small int8** for transcription with character timestamps, plus Silero VAD (MIT)
  to trim.
- Short utterances (2–10 s) should take well under a second on a modern CPU. Non-autoregressive SenseVoice is
  reported >5× faster than Whisper-Small. *Benchmark on the homelab before committing.*

**GPU tier (Windows PC, when on).**
- **Qwen3-ASR-0.6B** (or 1.7B) for transcription and **Qwen3-ForcedAligner-0.6B** for alignment; both Apache-2.0.
  In bf16 they need roughly 2–5 GB of VRAM together *(estimate)*.
- vLLM doesn't run natively on Windows. Use the Transformers backend in the same Python service the Kokoro GPU
  setup uses (`speech/windows/`), or WSL2.
- Hosts are tried in order, as for TTS (`BHASHA_SPEECH_URLS`).

**Tone and syllable scoring pipeline** (`POST /speech/score`, already in the design's API list):

1. **Expected syllables.** From the card or sentence, take the expected syllables with **surface** tones from the
   zh pack (sandhi applied; neutral tones marked).
2. **Alignment.** Align the recording to those syllables:
   - GPU: Qwen3-ForcedAligner.
   - CPU: SenseVoice or Paraformer character timestamps when the recognized text matches the target; otherwise
     CTC forced alignment of the target text.
   - Montreal Forced Aligner's Mandarin model (CC BY 4.0, HMM-GMM) is a heavier offline alternative, not needed if
     the above works.
3. **Segment check.** Did the ASR's pinyin for each aligned span match the expected toneless syllable? Use the ASR
   here only as a *weak* witness, because of intent bias. A phone-level model would be better. The 2026
   phonological-wav2vec2 work on Mandarin mispronunciation detection shows the way, but no released checkpoint was
   found; revisit later.
4. **Pitch.** Track F0 per syllable with pYIN (librosa, ISC license) or the existing YIN. Convert to semitones
   relative to the speaker's own range, estimated from the utterance or a 3-second calibration ("say 妈麻马骂").
5. **Classify each syllable's tone** with a small classifier:
   - Start with tonara's approach (pYIN contour + MLP; MIT; about 93.7% leave-one-speaker-out on isolated
     syllables).
   - Train on **Tone Perfect** (9,840 isolated syllables, six native speakers; CNNs report about 99.8% in
     distribution, which overstates real-world accuracy).
   - For syllables in context, add synthetic multi-syllable speech from the passing TTS voices, with sandhi labels.
     Context features matter: one study went from 79.5% to 92.6% on AISHELL-3 by adding neighboring syllables.
6. **Output.** Per syllable: expected tone, heard tone, confidence and the contour. The UI shows the contour against
   the target, colors syllables, and suggests a rating that you confirm. The design's risk table already says
   "scores as hints until validated on your own recordings".

**Validation data.**
- **OMPAL** (Interspeech 2025): 1,768 Mandarin utterances by French L1 learners, word-level ratings for consonant,
  vowel and tone by four experts, available for commercial and non-commercial use. It is the best open learner set
  found. Use it to measure the scorer against expert judgments.
- **LATIC** (IEEE DataPort, about 4 hours of non-native speech, login needed; license not seen) and a small
  CC BY-ND Australian learner set are secondary options.
- **iCALL** isn't open.
- Keep **your own recordings**: opt-in, stored in the `recording` table the design lists, labeled when a native
  speaker checks a sample.

**Effort.** L, 6–8 sessions:
- ASR engine in the speech service (CPU and GPU) with a benchmark script: 2;
- alignment and per-syllable pitch: 1.5;
- classifier training and evaluation: 1.5–2;
- the scoring endpoint and the UI on tone and reading cards: 1–1.5.

**Risks.**
- **Feedback validity.** Wrong tone feedback teaches wrong tones. Ship scores as hints, show the contour always,
  and publish the measured agreement on OMPAL in the UI.
- **Weak creaky third tones.** Pitch trackers fail on them; classify a mostly unvoiced 3rd as "low", which is what
  matters.
- **GPU PC availability.** The CPU tier must be good enough alone.
- **License drift.** FunASR's license changes automatically on publication; pin the model version and keep a copy
  of the license text with it.

**Testing.**
- Golden-file tests: Tone Perfect syllables and TTS sentences through the pipeline must reproduce the expected
  tones (≥ 95% on TTS, which is clean speech).
- Evaluation on OMPAL with a report (tone agreement, kappa) checked into `docs/`.
- Latency benchmark per host in CI-skippable tests, like the FSRS-fit tests that skip without PyTorch.

---

## 7. Voice tutor

**Goal.** Speak to the existing tutor: ASR in, TTS out, with the same scenarios, vocabulary limits and mistake
pipeline.

### Flow

1. **Record.** Use **push-to-talk** (tap to start, tap to stop) by default, not an open mic.
   - Beginners pause long mid-sentence, and the usual 0.5–0.8 s end-of-turn silence would cut them off.
   - An open mic also hears the tutor's own TTS on a phone speaker.
   - Optional auto-stop uses Silero VAD in the browser (`@ricky0123/vad-web` + onnxruntime-web; Silero is MIT, the
     wrapper's license is to be checked) with a long hangover of 1.5–2 s.
2. **Upload** the clip to `POST /api/speech/asr`.
   - The PWA sends whatever MediaRecorder produced: `audio/mp4` (AAC) on Safari, `audio/webm` (Opus) in Chrome.
     Feature-detect with `MediaRecorder.isTypeSupported`; never hard-code webm.
   - The server converts to 16 kHz mono with ffmpeg/PyAV.
3. **Confirm.** Show the transcript in the input box, **editable**, before sending. ASR errors on learner speech
   are common, and you shouldn't be "corrected" for the recognizer's mistake. The confirmed text goes through the
   existing `POST /tutor/{session}/turn`, so corrections and cloze cards work unchanged.
4. **Reply.** The tutor's reply is synthesized sentence by sentence (`speech.get_clip`), and the first sentence
   plays as soon as it's ready.
5. **Afterwards**, not in the loop: run #6's tone scoring on your utterances against the *corrected* text and show
   a short "tones this session" panel.

### Latency budget (typical, from end of speech)

| Step | CPU homelab | With GPU PC |
|---|---|---|
| End of turn (push-to-talk: 0; VAD: hangover) | 0 / 1.5 s | 0 / 1.5 s |
| Upload and decode | 0.1–0.2 s | 0.1–0.2 s |
| ASR (5 s clip) | 0.3–1 s *(to measure)* | 0.1–0.3 s |
| You confirm the transcript | ~1 s (human) | ~1 s |
| LLM reply (ChatGPT plan, streamed) + coverage check | 2–5 s; a rewrite doubles it | same |
| TTS of the first sentence (Kokoro) | 0.3–1 s | 0.1–0.3 s |
| **To first audio** | **about 4–8 s** | **about 3.5–7 s** |

The LLM dominates. That's acceptable for a learner, who needs think time anyway, but not for natural
conversation. Two ways to cut it:

- **Stream the reply** and synthesize the first sentence while the rest arrives. The coverage check then runs per
  sentence.
- **Use LM Studio on the GPU PC** for the tutor when it's on.

A full-duplex speech-to-speech model isn't worth it here. The vocabulary check and corrections need text in the
middle.

### Safari and iOS quirks to handle

- **Microphone.** `getUserMedia` needs HTTPS and a user gesture. Stop all tracks after each turn, so the mic
  indicator goes off. There are reports that home-screen web apps re-prompt for the microphone or behave
  differently from Safari tabs *(anecdotal; test on the real devices)*.
- **Audio playback.** It needs a prior gesture. Unlock one shared `<audio>` element (or AudioContext) on the
  push-to-talk tap and reuse it for TTS.
- **Backgrounding.** The AudioContext suspends when the app goes to the background; resume it on `visibilitychange`.
- **Offline.** Without the server, show the text tutor only.

**Effort.** M, 3 sessions: recording, upload and decoding 1; turn UI with editable transcript and streaming TTS 1;
VAD option, iOS hardening and the post-session tone panel 1.

**Risks.**
- Latency feels slow. The editable transcript doubles as think time, and streaming helps.
- iOS PWA microphone flakiness: test on iPhone and iPad early, in the first session.

**Testing.**
- Server: ASR endpoint with fixture clips in mp4 and webm. The turn pipeline with a mocked ASR and gateway.
- Manual device matrix: iPhone and iPad installed PWAs, Safari on Mac, Chrome.
- Timing logs per step (`llm_call` already logs model calls; add ASR and TTS timings).

---

## 8. Medical Chinese track

**Goal.** Prepare for the Medical Chinese Test and for history-taking and examination in Mandarin, once the core
reaches HSK 3–4.

### What the MCT is (as of November 2026)

- **Who runs it.** The Center for Language Education and Cooperation and Chinese Testing International (the HSK
  organizers), through chinesetest.cn. The official syllabus, 《医学汉语水平考试（MCT）大纲》, was published by Higher
  Education Press and announced in January 2021.
- **Who it's for.** International medical students in China, students abroad studying medicine in Chinese, and
  non-native clinicians working in Chinese.
- **Format.** One test with three sections: listening, reading and writing, each 100 points, 300 in total.
  - 101 items in about 120–125 minutes (sources differ).
  - **No speaking section.**
  - The level is set by score: Level 1 at 100–149, Level 2 at 150–199, Level 3 at 200–300 *(cut-offs from one
    third-party guide)*.
- **Level descriptions** (official wording, paraphrased):
  - L1: understands basic language in everyday hospital situations and can communicate simply about a condition.
    Enough for a hospital internship.
  - L2: understands more specific material and can discuss a condition in more depth.
  - L3: understands nearly all hospital communication.
- **Vocabulary.** About **400 / 800 / 1,500** medical terms for L1 / L2 / L3. The syllabus's medical vocabulary list
  has 1,500 terms with part of speech and pinyin.
- **What the syllabus contains.** A test introduction, level standards, a **topic syllabus** (organized by
  communicative pairs such as doctor–doctor and doctor–patient), a **task syllabus**, the **medical vocabulary
  syllabus**, test procedures and a **sample paper**.
  - It's a printed book, not a free PDF; I found no download. It's sold by Higher Education Press and listed on
    Google Books.
  - Commercial aids built on it exist: an MCT vocabulary book on Amazon, and the textbook series 《我是医学生》.
- **Dates and where.**
  - Third-party guides say 2026 sittings are in **May and November** *(unverified)*.
  - The official MCT page lists both an **internet-based test at a test center** and an **internet-based test at
    home**, and a notice about adding the home edition in more countries.
  - **I could not confirm whether the home edition or any US test center is open to US candidates.**
    chinesetest.cn was unreachable from the sandbox. Check "Find a Test Center" and the home-edition notice there
    before planning around a date.
  - Registration is through a chinesetest.cn account, with a photo upload.

### What this means for the app

- **Two parts of the curriculum.** The **MCT vocabulary list** (buy the syllabus) and the **clinical skills** the
  exam doesn't test but you need: speaking, history-taking, exam commands. Because MCT has no speaking section,
  speaking practice comes from the standardized-patient tutor, not from exam prep.
- **The MCT list is copyrighted.** Don't commit it to the repo. Add an importer for a **user-supplied CSV**
  (`term, pinyin, pos, level, english`), tagged `mct-2020:L1..3`, entered from your own copy. The same pattern
  works for any purchased list.

### Open data for medical vocabulary

| Source | What it gives | License | Use |
|---|---|---|---|
| CC-CEDICT (have) | Entries with domain labels in glosses ("(medicine)", "(anatomy)", "(TCM)"…) | CC BY-SA 4.0 | Seed list and glosses; filter by label. The count of tagged entries isn't verified (mdbg download blocked); tagging is inconsistent, so expect a few thousand with gaps |
| **Chinese Consumer Health Terms (CHT)**, Hou et al. 2018 | **Lay ↔ professional pairs**: consumer expressions mapped to 480 professional terms (endocrine, cardiology, GI, dermatology), from health-forum questions and patient-education articles; 93.9% inter-annotator agreement | Released for research (phoc.org.cn/cht); terms and current availability *unverified* | Best open seed for clinical/lay pairs; personal use |
| MMeSH (NaCTeM) | 369,028-term Chinese–English ontology on MeSH 2008 | No download or license found; demo "coming soon" | Contact NaCTeM; not a dependency |
| CMeSH (CAMS) | Official Chinese MeSH | Copyrighted, restricted | Don't ingest (as the design says) |
| MedDialog-zh | 3.4M real doctor–patient dialogues (Chinese) | License unknown ("Unknown" on its loader) | Frequency of lay expressions and realism checks only, kept locally, never redistributed |
| IMCS-21 | Annotated pediatric consultation dialogues (symptoms, dialogue acts, reports) | Not confirmed | Same as above; good model for case-card fact categories |
| UBC Digital Emergency Medicine phrasebook (Zhuang & Tran) | Clinician phrasebook: Mandarin, pinyin, simplified | No license stated on the page | Link only; use personally |
| Wisc-Online "making an appointment" | One interactive dialogue | CC BY-NC 4.0 | Link only |

No openly licensed medical Mandarin curriculum was found. The phrasebooks and courses (Mount Sinai's packet,
commercial audio courses, 《医用汉语》 textbooks) are all copyrighted. So the curriculum spine is: the MCT list from
your purchased syllabus, plus CC-CEDICT, plus CHT pairs, plus content we write (cases and drills) with LLM help.

### Clinical and lay pairs

The schema already has the pieces: `unit.register` (`lay | clinical`) and `unit_relation.kind="lay_equivalent"`.

- **Seeding.** Seed pairs from CHT. For terms without a pair, the batch job (#5) proposes lay phrasings, for
  example 腹痛 → 肚子疼 and 呼吸困难 → 喘不上气.
- **Checks.** The lay phrase must segment into HSK-level words and must not be the clinical term again. It then
  goes into the sampling queue.
- **Cards.** Both directions: clinical → lay ("say it to a patient") and lay → clinical ("what is the patient
  describing?"). Production of the clinical term matters less, except for case notes.

### Standardized-patient tutor

Build on the existing tutor (scenarios, coverage-checked replies, `record_sentence`). Add a `case_card` table, as in
the design:

```text
case_card: id, title, setting, level, persona {age, sex, occupation, education → register, temperament},
  chief_complaint (lay Chinese), facts[], exam_findings[], red_flags[], differential[], debrief_en
fact: id, category (HPI: onset/location/duration/character/aggravating/relieving/timing/severity;
  PMH, meds, allergies, FHx, SHx, ROS:<system>), content_zh (lay), disclosure ("volunteer" | "if asked" |
  "if asked specifically"), key (bool, counts for scoring)
```

**One turn, in two model steps:**

1. **Classify.** Which fact IDs does your question ask for, and which communication acts does it perform (open
   question, empathy, summarizing, consent)? Structured output, with the fact list visible to the model.
2. **Reply.** Generate the patient's answer from **only the disclosed facts** plus the persona. The reply prompt
   never sees hidden facts, so it can't leak them.

The coverage check on the reply still applies, at a lay register. EasyMED (2025) uses this kind of
intent-conditioned disclosure. LLM standardized-patient studies from 2025–26 (MedSimAI, a JMIR 2025 study of
ChatGPT as a standardized patient, an RCT in gastroenterology) report checklist scoring that agrees reasonably with
faculty raters when cases are instructor-authored.

**Scoring at the end of an encounter:**
- history coverage: key facts elicited out of total, by category, listing the missed questions in Chinese;
- communication items;
- language errors through the journal pipeline (cloze cards as usual).

Then the model writes a short Chinese case note (主诉、现病史、既往史、体格检查、初步诊断). It's saved as a
`generated` reader text for read-back, which also builds written medical vocabulary for the MCT's reading and
writing sections.

**Case authoring.** Write about 20 cases in English, using what you learn in med school (cases where you know the
answer key). The LLM drafts the lay Chinese facts, and the vocabulary check flags anything above level. Start with
common presentations: chest pain, abdominal pain, headache, fever and cough, diabetes follow-up, low back pain.

### Neurology exam command set

A drill deck (`track_tags=["medical"]`, scenario "neuro exam"). Cards: English → say the command (production with
voice after #6), and audio command → do or understand it. A first draft follows. **It's unsourced and must be
checked by a native-speaking clinician before use.**

| Exam step | Command (draft) |
|---|---|
| Orientation | 你叫什么名字？今天是几月几号？我们现在在哪里？ |
| Extraocular movements (CN III, IV, VI) | 请看着我的手指，头不要动，眼睛跟着手指看。有没有看到两个（重影）？ |
| Visual fields | 请看着我的鼻子。看到我的手指动的时候告诉我。 |
| Pupils | 我用手电筒照一下你的眼睛。 |
| Facial strength (CN VII) | 请抬眉毛。请用力闭眼，不要让我打开。请鼓起腮帮子。请笑一下，露出牙齿。 |
| Facial sensation (CN V) | 这样有感觉吗？两边感觉一样吗？ |
| Hearing (CN VIII) | 能听到这个声音吗？哪边听得清楚？ |
| Palate and tongue (CN IX, X, XII) | 请张嘴，说"啊"。请把舌头伸出来，左右动一动。 |
| Shoulder shrug (CN XI) | 请耸肩，用力往上顶。 |
| Grip and strength | 请用力握住我的手指。用力推我的手。用力拉。 |
| Pronator drift | 请把两只手平举，手心向上，闭上眼睛，保持不动。 |
| Lower-limb strength | 请把脚往上勾。往下踩，像踩油门一样。 |
| Sensation | 是尖的还是钝的？有没有麻木或者刺痛的感觉？ |
| Coordination | 请用手指碰一下我的手指，再碰你的鼻子。请快速翻转手掌。请把脚后跟放在另一边膝盖上，顺着小腿往下滑。 |
| Romberg and gait | 请站起来，两脚并拢，闭上眼睛。请走几步，转身走回来。用脚尖走，用脚跟走。 |
| Reflexes | 放松，我要敲一下你的膝盖。 |

### Safety line

Keep the design's statement in the track's intro: this is a learning tool, and real encounters with limited shared
language need a professional interpreter.

**Effort.** L, 6–8 sessions plus content time:
- MCT CSV importer and medical tags: 1;
- clinical/lay pairs and cards: 1;
- case-card model and two-step SP tutor: 2;
- scoring and case-note read-back: 1;
- neuro drill deck: 1;
- 20 cases: content work over weeks, not code.

**Risks.**
- **Clinical phrasing.** Errors in clinical Chinese are high-stakes. Get the drill deck and case language checked
  by a native-speaking clinician.
- **Fact leakage.** The SP model could leak hidden findings. The two-step design prevents it by construction; test
  it.
- **Exam logistics.** US availability and dates are unconfirmed.

**Dependencies.** Core at HSK 3–4 (the design's gate), the grammar track, the voice tutor for spoken history-taking,
batch enrichment for lay pairs.

**Testing.**
- Leakage test: with a mocked model, the reply prompt contains only disclosed facts.
- Coverage scoring on scripted transcripts.
- Importer tests with a sample CSV in `tests/fixtures` (made-up terms, not the copyrighted list).
- Pair checks.

---

## 9. Family logins

**Goal.** More than one learner on one install. Each per-learner table already has `user_id`, and
`api/deps.py:current_user` is the one seam to change.

### Options

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. Built-in sessions** | Username and password (argon2id via `argon2-cffi`, MIT), httpOnly SameSite=Lax session cookie, sliding 90-day expiry, sessions in a table | Works everywhere, including plain-HTTP LAN and offline-first PWA; no extra service | Passwords to manage (it's family; keep it simple) |
| **B. Passkeys (WebAuthn)** | `py_webauthn` (BSD-3-Clause) + `@simplewebauthn/browser` (MIT) on top of A's sessions | No passwords; Face ID / Touch ID | Needs HTTPS with a stable domain (RP ID); behavior inside iOS home-screen web apps not verified; recovery path still needed |
| **C. Forward-auth (Authelia / Authentik)** | Traefik `forwardAuth` middleware; the app trusts `Remote-User` (Authelia) or `X-authentik-username` only from Traefik's IP | Reuses the SSO many homelabs already run; MFA for free | Breaks plain-LAN use; SSO-session expiry turns API fetches into cross-origin redirects the service worker and outbox must survive; header spoofing if the port is reachable directly |

### Recommendation

- **A as the base.** Add an **optional C mode** (`BHASHA_AUTH=header`, `BHASHA_TRUSTED_PROXIES=<traefik ip>`) for
  homelabbers who already run Authelia or Authentik.
  - In header mode, the app maps the header to an `AppUser`, auto-creating it if allowed, and ignores the header
    from any other source IP.
  - API calls must answer **401 JSON, not a redirect**, when the session is gone. The outbox keeps queued reviews
    and the UI shows "sign in again". Exclude `/api/` from the forward-auth redirect, or handle the opaque redirect
    in `api.ts`.
- **Add B later** as a sign-in method inside A.
- **Shared iPad.** A "Who's studying?" profile picker with an optional 4-digit PIN per profile. Each profile keeps
  its own long-lived session cookie, so switching doesn't mean typing passwords.

### Migration of the default user

1. Leave the row. Its `id` owns all existing data.
2. On first start with auth enabled and no credentials set, the first-run screen asks you to set a name and
   password for that existing user (rename `default` → your name) and makes it the **admin**.
3. The admin adds family members, who start empty, at placement.

No data moves, so the migration is one Alembic revision: `app_user` gets `password_hash`, `is_admin`, `pin_hash`,
and there's a new `session` table.

### Per-user settings

`AppSetting` is install-wide today (voice, tone-check results). Add `user_setting(user_id, key, value)` and sort
the settings:

- **Per user:** daily caps, desired retention per card type, text size, pinyin mode, tone colors, HSK target,
  tracks (everyday or medical), handwriting caps, background-enrichment opt-in. `UserFsrs` is already per user.
- **Install-wide (admin only):** speech hosts and voice, the tone check, the import allow-list, Jellyfin, and the
  LLM daily cap ceiling.
- **LLM connection: per user.** Sign in with ChatGPT is tied to one person's plan, and sharing one person's plan
  across the family may conflict with OpenAI's terms. Let the admin share an LM Studio or API-key connection with
  everyone instead. `LlmConnection` gets a `user_id`, nullable for shared.

### Client side

- Key the outbox and IndexedDB by user ID, and refuse to sync another user's queue.
- On switching profiles, clear the service worker's cached API reads (`sw.js` caches recent API responses).
- The audio cache is content-addressed and can stay shared.

**Effort.** M, 3 sessions: A plus migration plus the profile picker 1.5; per-user settings split 1; header mode
0.5. Passkeys are +1 later.

**Risks.**
- Data leaking across users through cached API responses: clear on switch, and add a test.
- Forgotten admin password: a CLI reset command (`python -m app.admin reset-password`).

**Testing.**
- Every API router under an "other user" fixture must return 404 or empty for someone else's IDs. Generate the test
  from the router list so new endpoints are covered automatically.
- Header mode rejects the header from untrusted IPs.
- Migration test on a copy of a single-user database.

---

## 10. Vidya integration: a generic progress export

**Goal.** Let another study app (vidya, a study hub) show this app's progress, without knowing its internals.

### Endpoints (read-only, per user)

| Endpoint | Returns |
|---|---|
| `GET /api/export/v1/summary` | `{schema: "bhasha.progress/1", user, generated_at, languages: [{code, known_words, known_characters, level_coverage: {"hsk3-2025:1": 0.98, …}, typical_text_coverage: {subtitles, news}, reviews_due, reviews_7d, minutes_read_7d, minutes_listened_7d, days_studied_30d, tracks: {medical: {...}}}]}` |
| `GET /api/export/v1/events?since=<cursor>&limit=500` | An append-only, xAPI-shaped feed with a `next` cursor |
| `GET /api/export/v1/schema` | JSON Schema for both, so a consumer can validate |

### Event shape

xAPI's actor / verb / object / result / context / timestamp, simplified, with verbs mapped to ADL URIs, so an xAPI
Learning Record Store could ingest it with a thin adapter:

```json
{"id": "uuid", "timestamp": "2026-11-05T08:12:00Z",
 "actor": {"account": {"homePage": "https://bhasha.example", "name": "abe"}},
 "verb": {"id": "http://adlnet.gov/expapi/verbs/answered", "display": "reviewed"},
 "object": {"id": "bhasha:unit/zh/word/银行", "type": "word", "language": "zh", "facet": "meaning"},
 "result": {"rating": 3, "success": true, "duration": "PT6S"},
 "context": {"source": "queue"}}
```

**Verbs:**
- `reviewed` (answered);
- `read` and `listened` (experienced, with duration);
- `wrote` (journal);
- `talked` (tutor session);
- `mastered`, emitted when a unit first counts as known;
- `completed` (text finished).

Leave out text bodies and journal content; the feed carries progress, not your writing. Events derive from the
existing tables (`review_log`, `exposure`, activity segments from #4, `journal_entry`, `tutor_session`), so there's
no new write path.

### Auth and push

- **Auth.** Per-user API tokens with a `progress:read` scope, created in Progress → Connections, hashed at rest,
  revocable. They depend on #9's user model, but can be built against the single user first.
- **Optional push.** A webhook URL per token that gets `{cursor}` pings so a consumer can pull. Don't push the data
  itself.

**Language-agnostic by design.** Everything carries `language`, and level keys are the pack's tags, so a Bengali
pack slots in.

**Effort.** S, 1–2 sessions.

**Risks.** Schema churn. Version the path (`/v1`) and the `schema` field.

**Testing.**
- Schema validation of the outputs in pytest.
- Cursor pagination stays stable under inserts.
- Token scope: no access to other endpoints.

---

## What the core needs to stay language-agnostic (for the Bengali pack)

The Bengali pack is researched separately. These features should keep its door open:

- **Facets are pack-declared.** The pack lists which facets it supports: tone only where it has a prosody module,
  component only where it has sub-units, production everywhere. The review screen renders by facet, not by
  language.
- **Grammar inventories load through the pack** (`pack.grammar_inventory()`, `pack.detect_grammar(tokens)`). A
  CEFR-style self-defined list works the same way.
- **Dictation and production compare through `pack.normalize()` and `pack.reading_key()`.** For zh that's toneless
  and toned pinyin; for Bengali it's a romanization or a grapheme normalization. Homophone tolerance is then
  generic.
- **Speech engines are keyed by language** in the speech service (TTS and ASR). Tone scoring is a zh-only module
  behind the pack's prosody capability.
- **Reference corpora** for typical-text coverage are per language.
- **Medical-style tracks** are just track tags plus a CSV importer, not zh-specific code.

---

## Recommended order

1. **Minutes and typical-text coverage (#4).** Small, and the time data can't be backfilled.
2. **Card types (#1).** Production, tone perception and component cards use what's already built and pay off daily.
3. **Grammar track (#2).** The HSK 1–2 aspect points (了, 过, 着, 是…的) are what you're meeting now, and the
   journal's error pipeline is waiting for it.
4. **Batch enrichment (#5).** Feeds grammar explanations and examples, and later the medical lay pairs. Can overlap
   with #2.
5. **Listening and dictation (#3).** Uses the cached TTS. Natural next step once grammar cloze exists.
6. **Family logins (#9).** Before a second person uses the app and before per-user settings multiply. If family
   use is real sooner, move it to position 2.
7. **Speech recognition and tone scoring (#6).** Start with a one-session **spike**:
   - record 50 of your own utterances with known text;
   - run SenseVoice on CPU and Qwen3-ASR plus the aligner on the GPU PC;
   - measure latency and alignment quality;
   - then build.

   Speaking is mandatory from HSK 3, so this should land in the first year.
8. **Voice tutor (#7).** Right after #6.
9. **Progress export (#10).** Whenever vidya is ready to consume it. It's small and can slot in anywhere after #4
   and #9.
10. **Medical track (#8).** Gated on HSK 3–4, as the design says. Two things can start early as non-code prep: buy
    the MCT syllabus, and start writing case cards in English during clinical rotations.

## What couldn't be verified

- **MCT.** chinesetest.cn was unreachable. Not confirmed:
  - exact 2026 dates;
  - fees;
  - US test centers or home-edition availability in the US;
  - the score cut-offs per level (from a third-party guide);
  - the full topic and task lists (the syllabus is a printed book).
- **Hugging Face model cards** were blocked:
  - FireRedASR2 weight license;
  - the exact Fun-ASR-Nano weight license (taken from the GitHub README's statement that its cards list
    Apache-2.0);
  - BELLE Whisper license.
- **Sign in with ChatGPT developer page** (developers.openai.com) was blocked. Plan usage limits and any rules on
  background use come from the existing design doc, not re-checked.
- **CC-CEDICT medical entry count**: the mdbg download was blocked.
- **CHT (Chinese Consumer Health Terms)**: current availability and terms at phoc.org.cn.
- **MMeSH**: no download or license found. **UBC phrasebook**: license not stated.
- **Leipzig Chinese news corpus license**: CC BY on the site's terms, but one catalog says CC BY-NC.
- **`@ricky0123/vad-web` license**: not shown on the repo page.
- **Passkeys inside iOS home-screen web apps**, and whether **installed iOS PWAs re-prompt for the microphone**:
  anecdotal only.
- **CPU latency figures** for SenseVoice and VRAM for Qwen3-ASR are estimates; the #6 spike measures them.
- **The neuro command list** is drafted, not sourced.

## Sources

**Grammar and curriculum**
- krmanik/HSK-3.0 (2025 grammar JSON and License.md): https://github.com/krmanik/HSK-3.0
- Chinese Grammar Wiki (CC BY-NC-SA; link only): https://resources.allsetlearning.com/chinese/grammar/

**Listening and pronunciation evidence**
- Lu et al. 2024, shadowing and Mandarin tones, *J. Second Language Pronunciation*: https://doi.org/10.1075/jslp.22033.lu
- Systematic review of shadowing for L2 pronunciation (2025): https://www.tandfonline.com/doi/full/10.1080/29984475.2025.2546827
- Whisper and L2 learner errors (ICNLSP 2023): https://aclanthology.org/2023.icnlsp-1.30.pdf
- Phonological-level wav2vec2 for Mandarin mispronunciation detection (2026): https://arxiv.org/abs/2606.22022
- OMPAL learner corpus (Interspeech 2025): https://www.isca-archive.org/interspeech_2025/hsieh25b_interspeech.pdf
- LATIC: https://ieee-dataport.org/open-access/latic-non-native-pre-labelled-mandarin-chinese-validation-corpus-automatic-speech

**Speech models and tools**
- FunASR (toolkit MIT; MODEL_LICENSE): https://github.com/modelscope/FunASR
- SenseVoice: https://github.com/FunAudioLLM/SenseVoice
- Fun-ASR (Nano): https://github.com/FunAudioLLM/Fun-ASR
- Qwen3-ASR and ForcedAligner (Apache-2.0): https://github.com/QwenLM/Qwen3-ASR · report: https://arxiv.org/abs/2601.21337
- FireRedASR2S: https://github.com/FireRedTeam/FireRedASR2S · report: https://arxiv.org/abs/2603.10420
- faster-whisper (MIT): https://github.com/SYSTRAN/faster-whisper
- sherpa-onnx (Apache-2.0): https://github.com/k2-fsa/sherpa-onnx
- Montreal Forced Aligner Mandarin model (CC BY 4.0): https://mfa-models.readthedocs.io/
- tonara (MIT): https://github.com/dima-xd/tonara
- ToneNet (Interspeech 2019): https://doi.org/10.21437/Interspeech.2019-1483
- Mandarin tone CNN on Tone Perfect: https://github.com/alicex2020/Mandarin-Tone-Classification
- Tone classification in context (Tang & Li 2021): https://arxiv.org/abs/2104.05657
- Tone Perfect: https://tone.lib.msu.edu
- Silero VAD in the browser: https://github.com/ricky0123/vad
- WebKit MediaRecorder: https://webkit.org/blog/11353/mediarecorder-api/

**Medical Chinese**
- MCT official page: https://www.chinesetest.cn/MCT
- MCT syllabus announcement (People's Daily, Jan 2021): http://yn.people.com.cn/n2/2021/0108/c372458-34518294.html
- MCT syllabus book (Google Books): https://books.google.com/books/about/?id=1DvzzgEACAAJ
- Chinese Consumer Health Terms, Hou et al. 2018: https://link.springer.com/article/10.1186/s12911-018-0695-6
- MMeSH, NaCTeM: https://nactem.ac.uk/chinese
- MedDialog: https://aclanthology.org/2020.emnlp-main.743
- UBC DigEM medical Mandarin phrasebook: https://digem.med.ubc.ca/?p=11748
- MedSimAI (LLM standardized patients): https://arxiv.org/abs/2503.05793
- ChatGPT as standardized patient (JMIR 2025): https://jmir.org/2025/1/e59435
- EasyMED: https://arxiv.org/abs/2511.14783

**Auth, export, terms**
- Authelia trusted-header SSO: https://www.authelia.com/integration/trusted-header-sso/introduction/
- Authelia with Traefik: https://www.authelia.com/integration/proxies/traefik/
- py_webauthn (BSD-3-Clause): https://github.com/duo-labs/py_webauthn
- xAPI statements: https://xapi.com/statements-101/
- OpenAI Terms of Use (Jan 2026): https://openai.com/policies/terms-of-use/
- Leipzig Corpora terms: https://wortschatz.uni-leipzig.de/en/usage
