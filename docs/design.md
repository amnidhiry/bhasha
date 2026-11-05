# Mandarin Learning App — Design Doc

Nov 4, 2026 · Abe Nidhiry

> Converted from the original doc. Source links were not carried over; the
> citations are kept by name in **Sources**. Implementation status lives in the
> top-level `README.md`.

## Summary

We are building a self-hosted Mandarin app that knows every word, character and grammar point you know, and uses that to generate reading and listening at exactly your level. Generic apps teach everyone the same curriculum; this one builds the input around you.

- **For whom:** a native English speaker (you), then family, starting from zero Mandarin, with all explanations and translations in English, aiming at HSK 3.0 levels 1–4 and real-world reading and conversation.
- **Core bet:** a precise learner model (FSRS state per word, character and component) plus LLM generation gives personalized comprehensible input that no off-the-shelf app offers.
- **Core loop:** read or listen to level-matched content, tap to look up and mine unknown words, review them with FSRS, then use them in writing and speaking that feeds errors back into review.
- **Stack:** FastAPI + Postgres backend on the homelab and one installable PWA for iPhone, iPad and Mac (no native apps planned), built on open data (CC-CEDICT, Make Me a Hanzi, HSK 3.0 lists) and open libraries (FSRS, jieba, pypinyin). Model calls use your ChatGPT plan through Sign in with ChatGPT, not a paid API key.
- **First milestone:** HSK 1–2 vocabulary with tones and characters, a graded-reader generator, and an FSRS review queue, all usable on your phone.

Three goal tracks sit on the core: daily handwriting practice, everyday communication, and medical Chinese aimed at the Medical Chinese Test. Language-specific logic lives in swappable language packs, so Bengali and Arabic can follow Mandarin without rebuilding the core.

## Learning science

The evidence supports a simple split: acquire language from large amounts of understandable input, and use spaced retrieval to make the words in that input stick. Every feature in this doc traces back to one of the principles below.

| Principle | What the evidence says | Design commitment |
|---|---|---|
| Retrieval beats rereading | A meta-analysis found practice tests beat restudying and every other comparison condition (Adesope et al., 2017). | Every card asks you to produce or recognize before it reveals. No passive "study" screens. |
| Spacing, scheduled by a model | FSRS is benchmarked on about 1.7 billion reviews from 20,000 Anki users (srs-benchmark), and FSRS-6 scored best in a head-to-head with SuperMemo's SM-17 (fsrs-vs-sm17). | FSRS-6 schedules every reviewable item, with parameters optimized on your own review log once it is large enough. |
| Comprehension needs high word coverage | The classic figure is 98% known words for unassisted reading (Hu & Nation, 2000), with about 95% possibly enough for listening (Webb et al.). A 2023 replication could not fully reproduce the original (Kremmel et al.). | Generated and imported texts target 95–98% known-word coverage, computed from your learner model. Treat the target as a tunable dial, not a law. |
| Reading alone is slow for vocabulary | Gains from reading graded readers are real but modest, and retention decays without further encounters (Waring & Takaki, 2003). | Pair reading with one-tap mining into FSRS, and recycle new words across later generated texts. |
| Extensive reading builds confidence | An extensive reading program for L2 Chinese significantly raised learners' confidence and commitment (Zhou & Day, 2023). | The reader is the home screen, not a side feature. Track minutes and characters read, not just cards. |
| Tones need explicit teaching first | Explicit instruction on tone contours improved production; talker variability helped only in combination with it (Wiener et al., 2020). Another study found no generalization benefit from high-variability training (Dong et al., 2019). | Start with explicit pitch-contour lessons and visual feedback, then widen to multiple voices. Do not oversell multi-speaker drills. |
| Characters are mostly decomposable | About 80–90% of modern characters are semantic-phonetic compounds, and early radical knowledge predicts later reading comprehension (Chen, Ke & Koda, 2021). Radical awareness helps less for characters whose parts don't hint at meaning (Chen & Feng, 2020). | Teach components and show decompositions on every character, but flag "opaque" characters where the parts mislead. |

Two further principles are standard in second language acquisition and shape the output features. Learners notice gaps in their knowledge when they try to produce language, and corrective feedback on their own errors is more memorable than generic drills. The journal and tutor exist to create that noticing, then turn each error into a review item.

## Mandarin-specific challenges

Mandarin forces the app to track three linked layers per word (sound with tone, characters, meaning), plus a segmentation step that alphabetic languages never need. Each challenge below changes the data model or adds a feature.

| Challenge | Why it is hard | What the app does |
|---|---|---|
| Tones | Four tones plus neutral are phonemic, and English speakers have no native category for them. | Tone is a separate, scored field on every word card. Pitch-contour visualizer for your recordings. Tone-pair drills, since tones are harder in two-syllable words than in isolation. |
| Tone sandhi | Written tones differ from spoken ones (third-tone sandhi, 一 and 不 changes, neutral tones). | Store citation tone and surface tone separately. Show sandhi in the reader and use surface tone when grading speech. |
| No spaces between words | Text must be segmented into words before any lookup, coverage calculation or mining. | A segmentation service with a custom dictionary built from your known words and HSK lists, so the learner model counts words, not characters. |
| Polyphonic characters | Characters like 行, 长 and 了 have several readings decided by context. | Context-aware pinyin conversion, with reading stored per word, never per character. |
| Two scripts | Simplified is standard in mainland China; Traditional in Taiwan and Hong Kong. | Simplified first. Keep a traditional form field on every entry so a later toggle costs nothing. |
| Reading vs writing | Recognizing a character is far easier than writing it, and most daily writing is pinyin input. | Recognition cards for all characters. A daily handwriting track covers the official handwriting list first, then characters you choose. |
| HSK 3.0 transition | The 2021 proposal set high word counts; the November 2025 syllabus cut levels 1–5 back down. The first official new-format sitting is announced for 13 December 2026 (HSK Lord guide). | Use the November 2025 lists as the curriculum spine, version-tagged, so a future revision is a data update. |

**HSK 3.0 targets** (November 2025 syllabus, cumulative) — the curriculum spine, per the HSK Lord guide, which cites the CTI syllabus. Verify against the official list when importing.

| Level | Words | Characters to recognize | Characters to handwrite | Speaking test |
|---|---|---|---|---|
| HSK 1 | 300 | 246 | 100 (shared with HSK 2) | No |
| HSK 2 | 500 | — | 100 | No |
| HSK 3 | 1,000 | 655 | 250 | Yes |
| HSK 4 | 2,000 | — | 400 | Yes |
| HSK 5 | 3,600 | — | 550 | Yes |
| HSK 6 | 5,400 | 1,940 | 700 | Yes |
| HSK 7–9 | 11,000 | 3,088 | 1,200 | Yes, plus translation |

Dashes mark recognition counts the source did not give. Because speaking becomes mandatory at HSK 3, speech practice belongs in the first year of the roadmap, not as a late add-on.

## Where English speakers struggle

The learner is a native English speaker, so the app targets known transfer problems directly rather than teaching Mandarin as if from a neutral start.

| Area | Typical English-speaker problem | What the app does |
|---|---|---|
| Tones | No lexical tone in English; intonation habits flatten or override tones, especially at sentence end. | Tone is scored on every spoken answer; drills put words in sentence-final and question positions. |
| Sounds | Confusing zh/ch/sh/r with j/q/x and z/c/s; ü and the vowel in -i; aspiration (b/p, d/t, g/k) carries meaning. | Minimal-pair listening drills for exactly these contrasts before vocabulary ramps up. |
| Pinyin spelling | Reading pinyin with English letter sounds (q, x, c, zh). | Pinyin bootcamp teaches pinyin as its own sound system, with audio on every syllable. |
| Measure words | No equivalent for 个, 本, 张, 条 and the rest. | Every noun card shows its measure word; cloze cards test the pairing. |
| Aspect, not tense | Treating 了 as past tense; misusing 过 and 着. | 了 gets its own grammar track with many contrastive examples, explained in English. |
| Word order | Putting time and place phrases at the end of the sentence as in English. | The journal flags word-order errors as a category, and cloze cards drill time-place-verb order. |
| False friends from translation | Mapping one English word to one Chinese word (for example 知道 and 认识 both translate as "know"). | Dictionary popups show near-synonym notes; the LLM explains the difference on request. |

## Landscape

No existing tool combines a per-word learner model with generated, level-matched content. Learners today stitch together a reader, a dictionary and an SRS app, and none of them share knowledge state. That gap is the product.

| Tool | Type | What it does well | Gap we fill | Borrow |
|---|---|---|---|---|
| Du Chinese | Commercial reader | Polished graded stories with tap-for-pinyin, audio and translation; integrates with Pleco, Skritter and Hack Chinese. | Fixed library, same text for everyone, no knowledge of what you already know. | Reader UX: pinyin toggle, sentence audio, tap lookup. |
| The Chairman's Bao | Commercial reader | Graded news from HSK 1 to 6+. | Few features beyond reading. | Topical, news-style content as a generation mode. |
| Pleco | Commercial dictionary | Deep dictionaries, OCR, handwriting input, flashcards. | Dictionary first; review and reading are add-ons. | Lookup depth and handwriting recognition as the quality bar. |
| Migaku | Commercial immersion tool | Browser extension turns sites, Netflix and YouTube into mining sources with SRS. | Proprietary and cloud-only; mining, not generation. | Mine-from-anywhere: browser and subtitle import. |
| Anki + Hack Chinese + Skritter | SRS | Best-in-class scheduling, tone-focused vocab and handwriting practice. | Cards live apart from the texts they came from. | FSRS, handwriting grading, card-to-context links. |
| LinguaCafe | Open source, GPL-3.0, PHP/Vue | Self-hosted reader with lookup, word status tracking, review, Jellyfin subtitle and ebook import, 27 languages including Chinese. | Single user only; no tones, characters or generation. | Import pipeline ideas (Jellyfin, ebooks, YouTube); word-status colors. |
| Lute v3 | Open source, MIT, Python/Flask | Learning through texts with terms, multi-word terms and a Mandarin plugin using jieba and pypinyin (lute3-mandarin). | Generic per-language model; no FSRS-first design or speech. | Parser-exception rules for fixing bad segmentation; same Python stack, MIT license allows code reuse. |

**Build vs fork:** forking Lute is tempting since it is MIT-licensed Python, but its data model is text-centric and has no notion of characters, components or tones. We build a new backend and borrow specific modules and ideas, chiefly Lute's segmentation-correction approach and LinguaCafe's import sources.

## Open-source building blocks

Almost every hard subproblem already has a mature open component, so the build is mostly integration plus the learner model. The table lists what we reuse; licenses matter only if this ever leaves personal use, but share-alike data should stay in its own tables so that stays easy.

| Component | Use | License | Notes |
|---|---|---|---|
| py-fsrs | Scheduling on the server | MIT | Implements FSRS-6 with 21 parameters. The PWA mirrors it offline with ts-fsrs pinned to FSRS-6, checked by a parity test. |
| srs-benchmark | Evaluation | — | Reuse its metrics (log loss, RMSE bins) to check our parameters once the review log grows. |
| jieba | Word segmentation | MIT | Supports custom dictionaries. Add Lute-style split rules to fix over-merged words. |
| pypinyin | Pinyin, tone numbers | MIT | Fast default. Scored 86.1% on polyphone disambiguation in the CPP benchmark (g2pM). |
| g2pM / g2pW | Polyphone disambiguation | Verify | g2pM reached 97.3% on the same test with a 1.7 MB model. g2pW (BERT-based) is stronger but heavier. Run only on polyphonic characters. |
| CC-CEDICT | Dictionary | CC BY-SA | About 124,000 entries. Share-alike: keep it in its own table and attribute it. |
| Make Me a Hanzi | Stroke order, decomposition, radicals, etymology | Graphics: Arphic Public License; dictionary file separately licensed | Over 9,000 characters with IDS decompositions and per-stroke component mapping, PRC stroke order. |
| Hanzi Writer | Stroke animation and writing quizzes in the PWA | MIT (code), Arphic PL (data) | Drop-in for handwriting cards, with Apple Pencil through Safari's pointer events. |
| complete-hsk-vocabulary | HSK 2.0 and 3.0 word lists in JSON | MIT | Includes radicals, classifiers and parts of speech. Check it reflects the November 2025 syllabus before relying on level tags. |
| krmanik/HSK-3.0 | HSK 3.0 character, handwriting and grammar lists | See repo | OCR of the 2021 Ministry of Education PDF; use for grammar points and handwriting list, cross-checked against 2025 changes. |
| SUBTLEX-CH | Word and character frequency | Research dataset | Subtitle-based frequencies (Cai & Brysbaert, 2010), used to order words beyond the HSK lists. |
| Tatoeba | Human-written example sentences | CC BY 2.0 FR | Ground-truth sentences to mix with generated ones; keep per-sentence attribution links. |
| Tone Perfect | Tone audio | Open access, cite on use | 410 syllables in all four tones from six speakers, 9,840 files. Ideal for tone-perception drills and training a tone classifier. |
| Chinese Grammar Wiki | Grammar reference by level | Creative Commons, non-commercial with attribution | Link to points from cards and explanations; don't copy the content in. |
| CosyVoice | Self-hosted Mandarin TTS | Apache-2.0 | Zero-shot voice cloning gives multiple voices for multi-speaker listening. Needs a GPU for reasonable speed. |
| FunASR (Paraformer-zh, SenseVoice) | Mandarin speech recognition | Toolkit MIT; models under a separate model license | Mandarin ASR with timestamps, CPU deployment supported. Whisper is the fallback. |
| OwlLuna | Reference for Apple Pencil handwriting UX (writing surface, Pencil gestures, zoom window) | MIT | An open-source iPad notes app on Apple frameworks. With the app PWA-only, it is a design reference for the handwriting screen, not code we ship. |
| tonara, ToneNet, tone.me | Tone classification references | tonara MIT | tonara uses pYIN pitch tracking plus a small MLP, reporting about 93.7% on single syllables. Port the approach to Python for per-syllable tone feedback. |

"Verify" marks licenses not confirmed from a primary page; check them before copying code.

### Reuse plan: what we install, fork or import

Every module starts from an existing repo; we write only the glue, the learner model and the UI. Nothing in this table gets reimplemented.

| Module | Reuse | How | What we write |
|---|---|---|---|
| Server scheduling and optimizer | py-fsrs | `pip install "fsrs[optimizer]"`; its Optimizer fits your parameters and optimal retention from review logs | Mapping our card and review tables to its Card and ReviewLog objects; nightly re-fit job |
| PWA offline scheduling | ts-fsrs (MIT) | npm dependency, loaded with the server's fitted parameters | Sync queue; server stays the source of truth |
| PWA reference code | ts-fsrs-demo and spaced | Read for review-screen and data-layer patterns; borrow what fits | Our own UI |
| Segmentation | jieba | pip; load HSK lists and your known words as a user dictionary | Adapt Lute's split-rule file format for over-merged words |
| Pinyin | pypinyin (MIT) | pip; supports heteronyms and custom phrase dictionaries | Tone-sandhi rules layered on top (third tone, 一, 不) |
| Polyphones | g2pM | pip; call only for polyphonic characters | Nothing beyond the call site |
| Dictionary | CC-CEDICT | Data import script into its own table | Parser (small; format is one line per entry) |
| Characters and strokes | Make Me a Hanzi | Data import (dictionary.txt and graphics.txt) | Component index ("characters containing X") |
| Handwriting on web | Hanzi Writer | npm; its quiz mode already grades strokes | Map its mistake counts to an FSRS rating |
| Handwriting on iPad and iPhone | Hanzi Writer quiz mode in the PWA, Make Me a Hanzi stroke data | npm; pen input via Pointer Events (`pointerType: "pen"`, pressure, tilt) | Ignore touch while a pen is down for palm rejection; map Hanzi Writer's mistake counts to an FSRS rating. OwlLuna's iPad writing surface is the UX reference |
| HSK lists | complete-hsk-vocabulary (MIT) + krmanik/HSK-3.0 | Data import | Reconcile against the November 2025 syllabus |
| Example sentences | Tatoeba per-language export (cmn sentences file) plus links file for translations | Data import with per-sentence attribution | Join script |
| Reader import ideas | LinguaCafe (GPL-3.0) | Read only; GPL code is not copied into our codebase | Our own importers for EPUB, SRT and Jellyfin subtitles |
| Tone feedback | tonara approach (MIT) | Port pYIN + small MLP to Python; train on Tone Perfect | Training script and scoring endpoint |
| Speech | CosyVoice, FunASR | Their published Docker or Python setups, as a separate service | Thin HTTP wrapper |
| Arabic, Bengali packs | CAMeL Tools, BNLP | pip, inside each pack | Pack adapters only |

**Net new code:** the learner model and coverage calculation, the generation and repair loop, the language-pack interface, the import pipeline, the Sign in with ChatGPT client, and the UI.

### Design skills for the build sessions

Installing a few agent design skills before the UI work keeps the app from looking generic and saves revision rounds. Pick two or three per session; stacking many skills gives the agent conflicting rules.

| Skill | What it adds | Use for | License |
|---|---|---|---|
| Appllama skills | Study 20–30 real top-app screens before designing, plus anti-slop rules (no purple gradient CTAs, no glassmorphism everywhere) and a simulator check loop. Code guidance targets Expo/React Native; the research half needs the Appllama MCP, which runs on paid monthly credits. | Research phase: study screens from Duolingo, HelloChinese, Pleco and Du Chinese before designing the reader and review flows. Borrow its method and rules even without the MCP. | MIT (skills) |
| Anthropic frontend-design | Baseline rules for distinctive, non-templated web UI; the most-installed design skill. | PWA | — |
| Impeccable | Builds on frontend-design with seven references (type, color, spacing, motion and more) and commands like critique, audit and polish; writes a project DESIGN.md. | PWA critique and polish passes; DESIGN.md as the shared spec for web and iOS | Apache-2.0 |
| UI UX Pro Max | Generates a design system (style, palette, type) from a project description. | One-time design-system kickoff | MIT |

**Suggested setup:** frontend-design plus Impeccable, with one UI UX Pro Max run at the start to draft DESIGN.md. Use the Appllama research method, with or without its MCP. (The SwiftUI and Apple HIG skills dropped out with the native apps.)

## Product design

The app is organized around one daily loop: review, read, mine, produce. The reader is the home screen and everything else feeds it or is fed by it.

### Learner journey

1. **Sound bootcamp (weeks 1–2).** Pinyin initials and finals, then the four tones with explicit contour lessons, then tone-pair drills using Tone Perfect audio. Goal: hear and say tones before learning many words.
2. **First words (weeks 2–6).** HSK 1 core words introduced in tiny generated stories from the first day, so every word is met in context before it becomes a card.
3. **Steady state.** A daily session of roughly 30–45 minutes: due reviews, one reading or listening text, mining, then a short journal entry or tutor exchange.
4. **Toward authentic input.** As coverage rises, the reader shifts from generated texts to imported ones (articles, subtitles, books), with generated texts used to pre-teach their vocabulary.

### Daily session

1. Review due cards, capped so reviews never crowd out reading.
2. Read or listen to one level-matched text: generated, imported, or a pre-teaching text for something you plan to read later.
3. Mine unknown words with one tap; each card keeps the sentence it came from.
4. Produce: write a few sentences in the journal or talk to the tutor, using today's new words.
5. Tone practice: shadow a few sentences from today's text and see your pitch contour against the reference.

### Feature modules

| Module | What it does | Key details |
|---|---|---|
| Reader | Home screen for all text | Segmented text colored by word status (new, learning, known). Tap for surface-tone pinyin, gloss, decomposition and audio. Pinyin shown only over unknown words by default. Sentence audio. "Finished" logs an exposure for every word. |
| Generator | Level-matched texts on demand | Stories, dialogues, news-style pieces and pre-teaching texts. Target known-word coverage set by you (default 96%). Recycles due and recently learned words. |
| Importer | Bring outside text in | Paste, URL, EPUB and subtitles (SRT, Jellyfin) first; image OCR later. Shows coverage before you start, so you know whether a text is readable. |
| Review | FSRS queue | Several card types per word, each scheduled separately (see Learner model). Context sentence shown on every card. |
| Tone lab | Hear and produce tones | Minimal pairs, tone-pair drills, pitch-contour display of your recording against a reference, per-syllable tone feedback. |
| Characters | Learn the writing system | Component explorer ("every known character containing 氵"), stroke animation, handwriting cards for the official list, opaque-character warnings. |
| Journal | Guided writing | You write; the LLM corrects, explains each error briefly, and turns errors into cards. |
| Tutor | Conversation practice | Text first, voice later. Stays within your known vocabulary, logs errors into the same pipeline. |
| Listening | Audio-first practice | Play generated texts without the transcript, then reveal; dictation mode for sentences built from known words. |
| Progress | Honest metrics | Known words and characters, HSK 3.0 coverage by level, estimated coverage of typical texts, minutes read and listened. No streak guilt mechanics. |

The reader is where new words enter the system, and the journal and tutor are where your mistakes do; both land in the same review queue.

## Learner model and scheduling

The learner model is the core asset: a per-skill estimate of whether you know each word, character, component and grammar point. FSRS supplies the estimate for anything you review; reading behavior supplies weaker evidence for everything else.

### Knowledge units and facets

A knowledge unit is something you can know: a word (headword plus reading), a character, a component, or a grammar point. Each unit has facets, the separate skills you can have for it. Each facet is its own FSRS card, because knowing what 银行 means does not mean you can say it with the right tones or write it.

| Card type | Prompt → answer | Applies to | Default |
|---|---|---|---|
| Meaning | Characters (with sentence) → meaning | Words | On for all mined words |
| Reading | Characters → pinyin with tones, spoken or typed | Words | On |
| Listening | Audio only → meaning | Words, sentences | On after the word reaches review state |
| Tone | Audio → tone pattern, or produce tones and get scored | Words with 2+ syllables | On during bootcamp and for words with repeated tone errors |
| Production | Meaning or English cue → characters (via pinyin input) | Words | Opt-in per word |
| Handwriting | Meaning + pinyin → write the character stroke by stroke | Characters on the official handwriting list, then any you add | On, as a daily track (see Goal tracks) |
| Component | Component → meaning or sound hint, plus example characters | Components | Introduced the first time a component appears in a mined character |
| Cloze | Sentence with a gap → missing word or grammar particle | Grammar points, function words | On for grammar points |

Sibling facets of the same unit are never shown on the same day, so one card does not give away another.

### Evidence and knownness

1. **Reviews are the strong signal.** FSRS-6 tracks stability and difficulty per card and gives a recall probability at any moment.
2. **Reading exposures are weak signals.** Seeing a word without looking it up is logged as an exposure but never counted as a successful review. Looking up a word you already have a card for is logged as an unscheduled failed review, since you could not recall it.
3. **Manual marks cover words you learned elsewhere.** A short placement check can bulk-mark HSK levels as known.

A word counts as known for coverage when its meaning facet's recall probability is at least 0.9, or it is marked known. Coverage for any text is the share of its tokens that are known, excluding proper nouns and numbers. That one number drives generation, import ratings and progress.

### Scheduling policy

- Desired retention defaults to 0.9 and is adjustable per card type, since listening and handwriting can tolerate lower targets.
- Start with FSRS default parameters, then fit your own with the FSRS optimizer once the review log is large enough, and re-fit monthly.
- Cap new cards per day and total reviews per day, with a "reading first" mode that skips new cards when the backlog is high.
- Leeches (cards failed repeatedly) trigger help instead of more drilling: show the decomposition, generate a mnemonic, add two fresh example sentences, or suggest suspending the card.
- New words enter the queue only after you meet them in a text, never from a bare list.

## LLM features

The LLM writes and explains; deterministic code checks and annotates. The model never supplies pinyin, tones or dictionary glosses, because those come from local data that cannot hallucinate.

### Graded reader generation

1. **Build the brief.** Pull your known words (recall probability at least 0.9), up to five target words (due soon or recently mined), the topic and genre, and a length.
2. **Generate.** Ask for structured JSON: title, sentences (Chinese plus a natural English translation), which target words were used, and three comprehension questions.
3. **Validate.** Segment the text with jieba, compute coverage against the learner model, and list every unknown word that is not a target word.
4. **Repair.** If coverage is under target, send one constrained rewrite request naming the exact words to replace. Allow two attempts, then accept and flag.
5. **Annotate locally.** Pinyin with surface tones, glosses, decompositions and audio are added by the backend, then the text is stored with its coverage score.

The known-word list and style rubric sit at the front of the prompt so prompt caching covers them across generations.

### Other LLM features

| Feature | What the model does | What code does |
|---|---|---|
| Journal correction | Returns the corrected text plus a list of errors, each with a category (word choice, measure word, word order, aspect particle, missing word), a one-line explanation and the corrected span. | Maps each error to a knowledge unit and creates a cloze card from your corrected sentence. Repeated categories raise that grammar point's priority. |
| Tutor | Holds a conversation inside your vocabulary, staying on a chosen scenario, and annotates your errors as it goes. | Enforces the vocabulary limit by checking coverage on each reply and regenerating if it drifts. Voice adds ASR in and TTS out later. |
| Explain this | "Why 了 here?" or "How is 才 different from 就?" on any sentence, answered at your level. | Links the answer to the relevant Grammar Wiki point. |
| Pre-teaching texts | Writes a short easy text that uses the hardest words of an imported article before you read it. | Picks those words by frequency and coverage gap. |
| Leech help | Writes a mnemonic tied to the character's actual components. | Supplies the decomposition from Make Me a Hanzi so the mnemonic matches the real parts. |
| Batch enrichment | Writes example sentences and short usage notes for HSK words, offline. | Runs slowly in the background within the plan's usage limits (the plan has no batch discount); results are reviewed by sampling. |

### Model choice and cost

Model calls go through **Sign in with ChatGPT**, OpenAI's program that lets open-source apps use a person's ChatGPT Plus or Pro plan instead of an API key (developers.openai.com/siwc/token-sharing-open-source). The implementation follows SurfSense's (Apache-2.0):

- **Sign-in:** OAuth with PKCE. The first sign-in registers the install dynamically; the redirect goes to a loopback address, and on the homelab you paste that address back into the app. Tokens are stored encrypted with `BHASHA_SECRET_KEY` and refreshed before expiry.
- **Calls:** the Responses API with `store: false`, streaming, and JSON-schema structured output. The plan refuses some fields (temperature, max output tokens, prompt-cache retention, previous response id and others), so the gateway never sends them.
- **Cost:** no per-token charge; usage counts against the plan's own limits. A daily call cap (default 300) guards against loops, and every call is logged to `llm_call` with its token counts.
- **Alternatives:** any OpenAI-compatible endpoint, such as LM Studio on the homelab or an API key, through the same gateway. Use one for bulk jobs if the plan's limits get in the way.
- **Status:** OpenAI calls this a preview. If a step starts failing, check its docs first.

### Guardrails

- Pinyin, tones, glosses and stroke data always come from local sources, never from the model.
- Every generated sentence has a "flag as unnatural" button; flagged sentences are excluded from future context and reviewed.
- Generated text is labeled as generated. Imported and Tatoeba sentences remain the reference for naturalness.
- Every model call goes through one gateway, so the ChatGPT plan, LM Studio or an API key can be swapped without touching features.

## Goal tracks

On top of the core loop, three tracks shape what gets taught and generated: handwriting, everyday communication, and medical Chinese. Each track is a filter on the curriculum plus its own scenarios, card types and tutor modes, so they share one learner model.

### Handwriting

Handwriting is a first-class daily practice, not an optional extra. Writing characters by hand also reinforces recognition, so the track serves reading and retention too.

- **Progression per character:** watch the stroke animation, trace, write with hints, then write from recall given only meaning and pinyin.
- **Grading:** strokes are compared to Make Me a Hanzi stroke medians for order, direction and shape. The score maps to an FSRS rating (Again, Hard, Good, Easy), so writing retention is scheduled like any other skill.
- **What to write:** the official handwriting list by HSK level first, then characters from your own known words, ordered by frequency. You can add any character.
- **Clients:** Hanzi Writer quizzes in the PWA on every device. On iPad, Apple Pencil arrives as pointer events with pressure and tilt; the handwriting screen ignores finger touches while a pen is down (palm rejection) and offers a zoomed writing box, taking OwlLuna's iPad writing surface as the UX reference.
- **Daily writing session:** 5–10 minutes of due handwriting cards plus writing two or three sentences from today's text from dictation.

### Everyday communication

The goal is to handle real situations: ordering food, directions, shopping, phone calls, messaging, small talk, and family conversation.

- **Scenario curriculum:** each scenario bundles the words, set phrases and grammar it needs, tagged by HSK level. Set phrases (like 麻烦你 or 不好意思) are knowledge units of their own, learned as chunks.
- **Role-play tutor:** the tutor plays the other party with a goal ("you are the waiter, the dish they want is sold out"), stays within your vocabulary, and scores whether you achieved the task.
- **Messaging practice:** type replies with pinyin input, since that is how most daily writing happens, with corrections and casual-register notes.
- **Natural-speed listening:** generated dialogues at native speed with fillers and reductions, after first hearing them slowed down.

### Medical Chinese

This track targets taking a history and examining Chinese-speaking patients. It starts once the core reaches roughly HSK 3 to 4, since clinical talk sits on everyday grammar.

- **Target standard:** the Medical Chinese Test (MCT) assesses communication with patients and medical staff in clinical settings, with three levels (CTI). Its syllabus includes topic lists, task lists and medical vocabulary lists, which make a ready-made curriculum spine. One prep provider puts Level 1 at about 400 medical terms.
- **Two registers per concept:** every medical term is linked to the lay phrase patients actually use, for example 腹痛 (clinical) and 肚子疼 (lay). Cards test both directions, because you need to understand patients and explain things simply.
- **Scenario set:** greeting and consent, chief complaint, history of present illness, past medical, medication and social history, review of systems, physical exam commands, explaining tests, diagnosis and plan, discharge instructions. US medical Mandarin electives cover similar topics, such as body parts, history taking, departments, medications and diagnostic tests.
- **Neurology exam pack:** the commands and questions for a neuro exam (follow my finger, squeeze my hands, any numbness) as a dedicated drill set.
- **Standardized-patient tutor:** the tutor plays a patient from a case card with hidden findings. You take the history in Chinese; it scores coverage of key questions and language errors, then writes the encounter as a short Chinese case note for you to read back.
- **Terminology sources:** CC-CEDICT medical entries; the MMeSH Chinese-English ontology built on MeSH (369,028 terms); clinician phrasebooks such as UBC's medical Mandarin phrasebook. CMeSH itself is copyrighted by the Chinese Academy of Medical Sciences and access-restricted, so we do not ingest it.
- **Safety line:** this is a learning tool. The app says plainly that real clinical encounters with limited shared language need a professional interpreter.

## Architecture

One FastAPI backend owns the learner model and all language logic; clients are thin and work offline for reviews. Everything language-specific lives in a language pack, so Mandarin is the first pack and Bengali and Arabic plug in later without touching the scheduler, reader or tutor.

```
  PWA (ts-fsrs offline) ─┐
                         ├──>  API (FastAPI) ──> Postgres
  (installed on iPhone, iPad, Mac) ───────┘
                                  │   ├──> Language pack (zh: jieba, pypinyin, CC-CEDICT, MMAH)
                                  │   └──> LLM gateway (ChatGPT plan / LM Studio / API key)
                                  └──> Worker (Redis) ──> Speech (CosyVoice, FunASR, pYIN)
```

Clients talk only to the API; the API calls a language pack for anything language-specific and the gateway for any model call.

### Services

| Service | Role | Tech |
|---|---|---|
| API | Auth, learner model, review sync, reader and generation endpoints | FastAPI, SQLAlchemy, Alembic |
| Database | All user and content state | Postgres (one instance; SQLite allowed for a single-user dev setup) |
| Worker | Generation jobs, imports, audio rendering, batch enrichment, nightly FSRS re-fit | Arq or Celery on Redis |
| Language pack: zh | Segmentation, pinyin and sandhi, dictionary, decomposition, HSK levels | jieba, pypinyin + g2pM, CC-CEDICT, Make Me a Hanzi |
| Speech | TTS for texts and cards; ASR and pitch tracking for speaking and tone feedback | CosyVoice, FunASR or Whisper, pYIN; GPU optional, CPU fallback for ASR |
| LLM gateway | One interface for every model call, with token refresh, usage logging and a daily call cap | Sign in with ChatGPT (plan usage, Responses API) first; any OpenAI-compatible endpoint (LM Studio, or an API key) as an alternative |
| Clients | Reader, review, tone lab, handwriting, tutor | One PWA (Preact + Vite) with ts-fsrs for offline reviews, installed to the home screen or Dock on iPhone, iPad and Mac |

### Language packs

Each pack implements the same interface, so the core never branches on language.

| Capability | Mandarin (first) | Bengali (later) | Arabic (later) |
|---|---|---|---|
| Tokenize | jieba with custom dictionary; no spaces in text | Space-delimited, but rich suffixes; BNLP tokenizers (MIT) | Clitics attach to words; CAMeL Tools tokenization and morphology (MIT) |
| Reading aid | Pinyin with surface tones | Romanization toggle | Diacritics (harakat) added by CAMeL's diacritizer, since most text omits them |
| Sub-word units | Characters and components | Letters, vowel signs and conjunct consonants | Letters (four positional forms) and three-letter roots |
| Decomposition | Make Me a Hanzi IDS trees | Conjunct breakdown | Root and pattern analysis |
| Writing practice | Stroke order on characters | Letter and conjunct tracing | Letter forms and joining |
| Prosody module | Tones and sandhi | None needed | Stress, long vs short vowels |
| Level framework | HSK 3.0 | CEFR-style, self-defined | CEFR-style; choose Modern Standard Arabic or a dialect up front, since they differ a lot |
| Rendering | Ruby annotation, CJK fonts | Bengali font, line breaking | Right-to-left layout, Arabic fonts |
| LLM quality | Strong | Weaker; more flagging and review | Good for MSA, weaker for dialects |

The pack boundary is the main reason not to fork a Mandarin-only tool. The data model below stores knowledge units as generic rows with a pack-defined type, so roots and conjuncts fit beside characters and components.

### Apple devices: one PWA

There are no native apps. The PWA installs to the Home Screen on iPhone and iPad and to the Dock on Mac (Safari, Share, then Add to Home Screen or Add to Dock), and covers each device's role:

| Device | Role | How the PWA covers it |
|---|---|---|
| iPhone | Daily driver: reviews, short reads, tone shadowing | Compact layout; offline reviews with ts-fsrs; microphone through `getUserMedia` for the tone lab; finger handwriting in Hanzi Writer |
| iPad | Handwriting and long reading | Apple Pencil as pointer events (`pointerType: "pen"`, pressure, tilt) feeding Hanzi Writer; touches ignored while a pen is down; the lookup panel centres on wide screens |
| Mac | Desk sessions: importing, long reads, journal, tutor | Keyboard review (space, 1–4), paste import, a wide reading column; the system pinyin input method for typing Chinese |

- **Requirements:** HTTPS through Traefik. Service workers, offline caching and installation need a secure context.
- **Storage:** the server is the source of truth. The device only caches the review queue and the offline outbox, so Safari clearing site data never loses reviews that already synced.
- **Revisit native only for a gap the web cannot close.** The likeliest is Pencil latency or prediction in fast handwriting; PencilKit (with OwlLuna as reference) would be the fallback.

### Data model (core tables)

- `language`, `pack_version`: which packs are installed and their data versions.
- `unit`: any knowledge unit (word, character, component, set phrase, grammar point, root). Columns: language, type, headword, reading, level tags, frequency rank, register (lay or clinical), track tags (everyday, medical).
- `unit_relation`: word contains character, character contains component, clinical term has lay equivalent, word derives from root.
- `dictionary_entry`: glosses per unit and source (CC-CEDICT kept in its own table for share-alike).
- `card`: one per unit facet, with FSRS state (stability, difficulty, due, state).
- `review_log`: every review, scheduled or not, with rating, duration and source (queue, reader lookup, handwriting score).
- `exposure`: unit seen in a text, looked up or not.
- `text`, `text_token`: imported or generated texts, segmented, with coverage at creation time and provenance (generated, imported, Tatoeba).
- `audio_asset`, `recording`: TTS output and your own recordings with pitch tracks and scores.
- `journal_entry`, `error_item`: your writing, the corrections, and the categorized errors linked to units.
- `scenario`, `case_card`: everyday and medical role-play definitions, including hidden findings for standardized patients.
- `llm_call`: model, tokens, cost and feature, for budgeting.

### API surface

- `GET /reviews/due`, `POST /reviews` (batch sync from clients, conflict-safe by review id)
- `POST /texts/import`, `POST /texts/generate`, `GET /texts/{id}` (tokens with status and annotations)
- `GET /lookup?q=` (dictionary, decomposition, audio)
- `POST /mine` (create cards from a token with its sentence)
- `POST /journal`, `POST /tutor/{session}/turn`
- `POST /speech/score` (recording to tone and pronunciation feedback)
- `GET /progress` (coverage, known counts by level and track)

### Deployment

Docker Compose with api, worker, postgres, redis and speech containers, behind your existing Traefik reverse proxy, with the repo on your Forgejo. The speech container can live on whichever host has a GPU; if none, run ASR on CPU and render TTS in the background so audio is ready before you study. Nightly Postgres dumps cover backups; the review log is the irreplaceable part.

## Roadmap

Build in six phases, each ending in something you use daily, with a gate before moving on. The MVP is phases 0 and 1: data, scheduler, reader, generator and sound bootcamp.

The medical track starts only after the core reaches HSK 3 to 4, and a second language waits until the Mandarin pack has proven the interface.

### MVP scope (phases 0–1)

- [ ] Repo on Forgejo, Docker Compose skeleton, Postgres schema with migrations
- [ ] Import CC-CEDICT, Make Me a Hanzi, HSK 3.0 lists, SUBTLEX-CH frequencies, Tatoeba sentences
- [ ] zh language pack: segmentation with custom dictionary, pinyin with sandhi, lookup, decomposition
- [ ] FSRS-6 scheduler with meaning, reading and listening cards; review sync endpoint
- [ ] PWA: review screen, reader with word-status colors and tap lookup, one-tap mining
- [x] Generator with coverage validation and repair loop, behind the LLM gateway with a daily call cap
- [ ] Sound bootcamp: pinyin lessons, Tone Perfect drills, English-speaker minimal pairs
- [ ] Progress page: known words and characters, HSK coverage

## Open questions

- Which homelab host has a GPU for TTS, if any? This decides whether audio renders live or in the background.
- Simplified only, or show traditional forms from the start for later travel or reading?
- Is family use real in the first months? If so, add multi-user auth in phase 0 rather than retrofitting.
- Which second language pack first, Bengali or Arabic, and for Arabic, MSA or a dialect?
- Should the study hub and vidya see this app's progress, for one dashboard across everything you study?

## Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Generated Chinese sounds unnatural | You learn odd phrasing | Flag button, Tatoeba and imported text as references, periodic spot checks with a native speaker |
| Segmentation errors | Wrong coverage, wrong cards | Custom dictionary, split rules, per-text manual fix that feeds the rules |
| Scope creep across tracks and languages | Nothing finished | Gates between phases; the medical track waits for the HSK 3–4 core |
| Tone scoring is noisy | Discouraging or wrong feedback | Show the pitch contour and let you judge; use scores only as hints until validated on your own recordings |
| Speech models need GPU | Slow or missing audio | Background rendering, CPU ASR, cache all audio |
| Review backlog after busy weeks | You quit | Review caps, reading-first mode, no streak penalties |

## Sources

**Learning science**
- Adesope et al., 2017 — practice testing meta-analysis
- Hu & Nation 2000, summarized by Kremmel et al., and Kremmel et al., 2023 replication
- Webb, Pellicer-Sánchez & Wang — lexical coverage revisited
- Waring & Takaki, 2003 — vocabulary from graded readers
- Zhou & Day, 2023 — extensive reading in L2 Chinese
- Wiener, Chan & Ito, 2020 — explicit instruction and HVPT for tones
- Dong et al., 2019 — talker variability in tone training
- Chen, Ke & Koda, 2021 — grapho-morphological knowledge and reading
- Chen & Feng, 2020 — radical awareness and opaque characters

**Spaced repetition:** srs-benchmark, FSRS vs SM-17, Open Spaced Repetition, py-fsrs

**Standards:** HSK Lord — HSK 3.0 guide (November 2025 syllabus); CTI — Medical Chinese Test, MCT syllabus announcement, MCT prep levels

**Tools and data:** OwlLuna (github.com/owaisazmal/OwlLuna); LinguaCafe, Lute v3, lute3-mandarin; jieba, g2pM, g2pW; CC-CEDICT, Make Me a Hanzi, Hanzi Writer; complete-hsk-vocabulary, krmanik/HSK-3.0; Tone Perfect, tonara, ToneNet; CosyVoice, FunASR; Chinese Grammar Wiki; MMeSH (NaCTeM), UBC medical Mandarin phrasebook; CAMeL Tools, BNLP; Claude API pricing

**Apps:** Du Chinese, The Chairman's Bao, Migaku and others

**Reuse and design skills:** pypinyin, ts-fsrs, py-fsrs optimizer docs; Appllama skills, Impeccable, UI UX Pro Max, Skillselion design ranking; SurfSense (Sign in with ChatGPT client, Apache-2.0)
