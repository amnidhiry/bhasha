# Bengali language pack — research and design

Nov 5, 2026 · research for the second bhasha language pack

> **Target:** Standard Colloquial Bengali (চলিত ভাষা) as spoken and written in Kolkata and West Bengal, for a
> native English speaker, at rough parity with the Mandarin features in `README.md`. Where Indian and
> Bangladeshi usage differ, Kolkata wins and the Bangladeshi form is taught as "also heard".
>
> **How this was researched:** in a sandbox where huggingface.co, kaikki.org, tatoeba.org, Wikipedia, OPUS,
> Leipzig, arXiv and the GitHub API were blocked. GitHub raw files, PyPI and web search worked. Facts checked
> against a primary file are marked ✔; facts only from search summaries or secondary pages are marked
> *(unverified)*. Section 0 lists the measurements I ran myself.

## Summary

- **Bengali can reach rough parity with Mandarin.** The sound and script work is different, but the core loop of
  reading, lookup, mining, FSRS, generation, journal and tutor carries over almost unchanged once the core stops
  assuming Chinese. The core assumes Chinese in about 30 places (section 11).
- **The reading aid works like pinyin with sandhi.** Show a learner romanization of how the word is *said*
  (schwa deletion, ô/o, e/æ, phala gemination). The letter-by-letter transliteration sits beside it the way
  citation tones sit beside surface tones. The pronunciation source is Google's 65k-entry Bengali pronunciation
  lexicon (CC BY 4.0 ✔), with rules for words it doesn't have. Off-the-shelf transliterators get
  schwa deletion wrong (section 2, measured).
- **A unit is a lemma, not a surface form.** Bengali inflects heavily (a verb has 40+ common forms), so
  word units are lemmas. Case endings, classifiers and verb endings become grammar-point units with cloze cards.
- **Data is the hard part.** The open Bengali–English dictionary data is small: English Wiktionary has about
  9.3k Bengali words ✔, against CC-CEDICT's 124k. The open corpora, the subtitle frequency list and LLM training data all lean
  Bangladeshi. I measured পানি used about 7 times as often as জল in the OpenSubtitles list. A curated Kolkata
  layer (survival list, regional tags, a register check) is needed, not optional.
- **Speech exists, but for the GPU PC.** Indian-Bengali TTS comes from AI4Bharat: Indic Parler-TTS
  (Apache-2.0), Indic-TTS FastPitch (MIT, CPU-friendly) and IndicF5. Bengali ASR comes from IndicConformer
  (MIT). Apple lists a Bengali (India) voice *(VoiceOver list, via search)*. There are no tones, so
  "tone check" becomes a voice check on schwa, aspiration and ô/o, and "Say it" plots intonation and vowel quality.
- **Handwriting needs data we write ourselves.** No open stroke-order dataset exists for Bengali. Hanzi Writer
  accepts custom stroke data, so about 70 letters and signs plus about 100 conjuncts can be traced from Noto Sans
  Bengali (OFL) outlines with hand-drawn medians.

---

## 0. Measurements made for this doc

Run in the sandbox on the files named. Scripts were throwaway and are not committed.

| What | Result |
|---|---|
| hermitdave/FrequencyWords `content/2018/bn/bn_full.txt` (OpenSubtitles 2018) | 99,994 types, **2.64M tokens** in total: small next to SUBTLEX-CH's 33M. The top "word" is the danda `।` (157k), so the list was tokenized naively |
| Kolkata vs Bangladesh word pairs in that list (count WB / count BD) | জল 106 / পানি 717 · স্নান 15 / গোসল 92 · কাকা 25 / চাচা 137 · বৌদি 1 / ভাবি 148 · সঙ্গে 977 / সাথে 10,611 · পিসি 6 / ফুফু 25 · আম্মা 68, আব্বা 106 (Kolkata uses মা/বাবা) · নমস্কার 52 / সালাম 58 · মাসি 22 / খালা 20 · ঈশ্বর 621 / খোদা 667. **The subtitle corpus is mostly Bangladeshi fansubs** |
| Spelling variants in the top 100 | ভালো 4,782 and ভাল 4,509 (same word); কি 27,254 and কী 8,060 (different words in the reformed spelling standard, often confused) |
| Unicode encoding of য় in the subtitle list | 10,172 lines use precomposed U+09DF, 1,825 use য + nukta (U+09AF U+09BC). NFC turns both into the decomposed form; the Google lexicon uses the decomposed form throughout |
| Google `bn/data/lexicon.tsv` | 65,037 entries, 64,968 spellings, 67 homographs labelled (বল noun /bɔl/ vs verb /bɔlo/; হল noun /hɔl/ vs verb /holo/) |
| Lexicon coverage of subtitle frequency list | top 1,000 types 95.4% (98.4% of their tokens); top 5,000 85.1% (95.7%); top 20,000 67.1% (92.8%). Some common words are missing (ভয় "fear") |
| Conjunct clusters (C + ্ + C…) by token weight in the subtitle list | 394 distinct. Top 25 cover 57%, **top 100 cover 93.4%, top 150 cover 98.6%**, top 200 cover 99.7% |
| Most frequent 60 conjuncts | ন্য প্র চ্ছ ন্ত ক্ষ হ্য ব্য স্য ত্য ন্দ স্ত ক্ত ত্র ষ্ট স্ট ন্ধ ন্ট ন্ড গ্র শ্ব স্থ দ্ধ স্ব ধ্য ম্প ঙ্গ র্ক ক্র ম্য র্ত ত্ত শ্য ক্য র্ট র্য র্ড ক্স চ্চ শ্চ স্ক প্ল য্য র্ব জ্ঞ ম্ব র্ম র্থ ন্স ট্র দ্র গ্য ম্ভ ন্ন ব্র ল্প ত্ব ল্য ন্ত্র প্ত ম্ম |
| Transliterators on 29 test words (installed from PyPI) | see the table in section 2 |

Not run: the bkit/BanLemma lemmatizer. It installed, but running it was blocked by the sandbox's permission
policy, so its quality on Kolkata forms is **unverified**.

---

## 1. Script and phonology for an English speaker

Primary references: Thompson, *Bengali: A Comprehensive Grammar* (Routledge); Hayes & Lahiri (1991), "Bengali
intonational phonology", *NLLT* 9; the phoneme inventory and transcription guide in google/language-resources
`bn/` ✔; [Wikipedia: Bengali phonology](https://en.wikipedia.org/wiki/Bengali_phonology) and
[Bengali alphabet](https://en.wikipedia.org/wiki/Bengali_alphabet) *(via search)*;
[r12a's Bengali script notes](https://r12a.github.io/scripts/beng/bn) (Radice's vowel-harmony table, via search).

### The writing system

- **Abugida.** Each consonant letter carries an inherent vowel /ɔ/ (romanized ô). Other vowels are written as
  vowel signs (কার) attached to the consonant: া a, ি i, ী i, ু u, ূ u, ৃ ri, ে e/æ, ৈ oi, ো o, ৌ ou.
  ি, ে and ৈ are written *before* the consonant they follow in speech; ো and ৌ wrap around it. Unicode stores them in spoken
  order, and ো is canonically ে + া.
- **Inventory to teach.** 11 vowel letters (স্বরবর্ণ: অ আ ই ঈ উ ঊ ঋ এ ঐ ও ঔ) and about 35 consonants in
  everyday use (ব্যঞ্জনবর্ণ, traditionally 39 with ং ঃ ঁ ৎ). The consonant grid is the five
  places × (plain, aspirated, voiced, voiced-aspirated, nasal) table from Sanskrit; it's the best mnemonic, so
  teach it as a grid.
- **Diacritics.** ং anusvar /ŋ/; ঃ visarga (rare: gemination or /h/); ঁ chandrabindu marks a nasal vowel
  (চাঁদ chãd "moon"); ৎ khanda ta, a final /t/ with no vowel (হঠাৎ hôṭhat); ্ hôsôntô (virama) kills the
  inherent vowel and forms conjuncts.
- **Conjuncts (যুক্তাক্ষর).** C + ্ + C. Many are stacked or ligated past recognition (ক্ষ kkh, জ্ঞ gg/gæ,
  ঙ্গ ngg, ত্র tr, হ্ম mh). **About 100 cover 93% and 150 cover 98.6% of conjunct occurrences** (section 0), so
  the "common conjuncts" list should be the top 100, then 150.
- **Phalas** are reduced second members, and each changes the sound:
  - **য-ফলা** (্য): after an initial consonant with no other vowel it gives /æ/ (ব্যাপার bæpar, ব্যবসা
    bæbsha). Medially it doubles the consonant (অন্য onno, সত্যি shotti).
  - **ব-ফলা** (্ব): initially silent (স্বামী shami), medially it doubles the consonant (বিশ্ব bishsho), and it
    is pronounced only in some loans and compounds (উদ্বেগ udbeg).
  - **ম-ফলা** (্ম): usually silent with gemination (পদ্ম pôddo, আত্মা atta), and sometimes nasalizes.
  - **র-ফলা** (্র, as in ক্র kr) and **reph** (র্ above the next letter: কর্ম kôrmo) are both /r/.
- **Numerals** ০১২৩৪৫৬৭৮৯. Kolkata uses Bengali and Western digits side by side. The number words 1–100 are
  irregular (একুশ 21, বাইশ 22, …) and must be learned like vocabulary. They matter for prices and times.
- **Spelling standard.** Kolkata follows the Paschimbanga Bangla Akademi spelling rules; Dhaka follows the Bangla
  Academy. They mostly agree since the reforms, but variants are everywhere in real text (ভালো/ভাল, খাবো/খাব,
  কী "what" vs কি yes/no particle). *(I could not fetch either rule book; the variants are measured in section 0.)*

### Where spelling and sound part ways (the pinyin-bootcamp equivalent)

| Spelling | Kolkata pronunciation | Teach as |
|---|---|---|
| শ ষ স | all /ʃ/ ("sh"), except /s/ in clusters with dentals, ন, ল, র and in loans (স্টেশন sṭeshon, স্কুল skul) | "three letters, one sound" |
| জ য | both /dʒ/ ("j"). Dhaka speech often uses /z/; teach /dʒ/ | spelling-only distinction |
| ন ণ | both /n/ | spelling-only |
| ই ঈ, উ ঊ | no length contrast (vowel length is not phonemic) | spelling-only |
| ঋ ৃ | /ri/ (বৃষ্টি brishṭi) | |
| Inherent অ | /ɔ/ (ô), raised to /o/ before a following i/u (অতি oti, বলছি bolchhi), in initial clusters with র/য-ফলা (প্রথম prothôm) and elsewhere by lexical rule; **deleted** word-finally after a single consonant (জল jôl, মন môn) and at many medial syllable boundaries (কলকাতা kolkata); kept after conjuncts and in many verb forms (বলো bôlo, করব kôrbo) | the hardest single thing. Rules get you roughly 85–92%, the lexicon the rest |
| এ ে | /e/ or /æ/: এক æk "one", দেখা dækha "to see" but দেখি dekhi "I see" (vowel harmony) | |
| ো vs inherent | /o/ vs /ɔ/ is phonemic (কাল kal; বল bôl "ball" vs বলো bôlo "say!") | minimal-pair drills |
| ড় ঢ় | retroflex flap /ɽ/ (গাড়ি gaṛi). Careful Kolkata speech keeps it distinct from র /r/; East Bengali and the Google lexicon merge them | contrast drill ড়–র |
| জ্ঞ | /gg/ or /gæ/ (জ্ঞান gæn, বিজ্ঞান biggæn) | conjunct with an irregular sound |
| ক্ষ | /kkh/ medially (লক্ষ্মী lokkhi), /kh/ initially (ক্ষমা khôma) | |
| হ্য, হ্ম, হ্ন | /dʒʰ/-like or metathesis (সহ্য shojjho, ব্রাহ্মণ brammhon) | rare; lexicon |

### Contrasts that are hard for English speakers

1. **Aspiration in four series**, two of which English lacks: voiceless unaspirated (ক) vs aspirated (খ) is
   like *skin* vs *kin*. Voiced breathy (ঘ ঝ ঢ ধ ভ) has no English equivalent. ফ is [pʰ] or [f] in Kolkata.
2. **Dental vs retroflex:** ত থ দ ধ are dental (tongue on the teeth, softer than English t). ট ঠ ড ঢ are
   retroflex (tongue curled back). **English /t d/ is alveolar and Bengalis hear it as retroflex**, which is why
   loans like টেবিল use ট. Learners must move *their* t forward for ত.
3. **ô /ɔ/ vs o /o/** and **e vs æ**: phonemic, and the spelling often hides them.
4. **ড় flap vs র tap.**
5. **Nasal vowels** (chandrabindu): বাঁশ bãsh "bamboo" vs বাস bash "dwelling".
6. **Gemination** (closure length): পাকা paka "ripe" vs পাক্কা pakka "proper, thorough".
7. **Prosody:** stress on the first syllable, light and even. **Intonation** carries yes/no questions, which
   often have no other marker beyond optional কি. Hayes & Lahiri describe a final rise-fall (L* H L%)
   on yes/no questions, against a fall on statements. English rising question intonation sounds wrong.

### Grammar points an English speaker needs (for the grammar track and journal categories)

SOV order with postpositions; no grammatical gender; three-way second-person register **তুই** (intimate) /
**তুমি** (familiar) / **আপনি** (polite), each with its own verb agreement; **classifiers** -টা -টি -খানা
-জন and plural -গুলো -রা (the closest thing to measure words); case markers -কে (object/dative), -র/-এর
(genitive), -তে/-এ/-য় (locative/instrumental); **experiencer genitive** (আমার ভালো লাগে "I like it", literally
"to me it feels good"; আমার জ্বর হয়েছে "I have a fever"); no copula in the present (আমি ডাক্তার); negation with
না after the verb, perfect negative -নি (করিনি "I didn't do"), and নেই "there isn't"; **compound and conjunct
verbs** (খেয়ে ফেলা "eat up", মনে পড়া "remember", ভালো লাগা "like"), which are multi-word lexical units; the
emphatic clitics -ই and -ও; echo words (জল-টল "water and such").

**Kolkata specifics vs Dhaka:** /dʒ/ not /z/ for জ য; /tʃ tʃʰ/ for চ ছ, where much Bangladeshi speech has /ts s/;
aspiration and breathy voice kept (East Bengali dialects reduce them); ড়/র usually distinct; the older first-person
past -লুম (গেলুম "I went") as a colloquial variant of -লাম; Kolkata vocabulary (section 5).

---

## 2. Romanization and the reading aid

### What plays pinyin's role

| Option | Fits? |
|---|---|
| ISO 15919 / Library of Congress (letter-faithful: কলকাতা *kalakātā*) | Exact and reversible, but **it is a transliteration of the spelling, not the sound**: it writes the inherent vowel everywhere. Good as the secondary "spelling" line, misleading as the main aid |
| Learner phonetic romanization with schwa deletion (কলকাতা *kolkata*) | **Yes.** This is what pinyin does for Mandarin: it shows the sound. It must come from a pronunciation source, not the letters |
| IPA | Precise; too heavy for the reader, fine in the lookup sheet |

**Recommendation:** two layers, mapped onto the existing `Syllable` citation/surface split.

- **Surface (shown by default above or under unfamiliar words): bhasha phonetic romanization** from the
  phonemic transcription. ô = /ɔ/, o, a, æ = /æ/, e, i, u; aspirates written with h (kh gh chh jh ṭh ḍh th dh
  ph bh); retroflexes with an underdot (ṭ ḍ ṛ) and dentals plain (t d); শ/ষ/স as sh or s as pronounced;
  geminates doubled; nasal vowels with a tilde (chãd). Examples: জল jôl, বলো bôlo, এক æk, দেখা dækha, লক্ষ্মী
  lokkhi, স্বাস্থ্য shastho, জ্ঞান gæn, গাড়ি gaṛi, নমস্কার nômoshkar, ধন্যবাদ dhonnobad.
- **Citation (lookup sheet, and a "spelling" toggle): ISO 15919.** A small table of our own, because
  `indic_transliteration`'s ISO output uses Sanskrit conventions (ব → v) and mishandles decomposed ড় (output
  `gāḍa়i`, measured).
- **"Spelling traps" highlight (the tone-colour equivalent):** mark the letters where sound ≠ letters, such as a
  deleted or kept inherent vowel, ô→o, e→æ, a silent or doubling phala, or শ/ষ/স. Where pinyin colours tones,
  this colours the places a spelling-based guess goes wrong. It falls out of comparing the two layers.

### Tools, tested

All MIT-licensed unless noted. Licenses from PyPI metadata ✔.

| Tool | License | What it does for us | Measured on 29 words |
|---|---|---|---|
| **google/language-resources `bn/data/lexicon.tsv`** ✔ | **CC BY 4.0** | 65k expert phonemic transcriptions with syllable breaks, built for Google's **Bangladeshi** Bangla TTS (Gutkin et al., SLTU 2016) | Correct on every test word in it: জল `j O l`, কলকাতা `k o l . k a . t a`, বলো `b O . l o`, এক `E k`, জ্ঞান `g E n`, ব্যাপার `b E . p a r`, স্বাস্থ্য `sh a s . th o`. **Gaps:** no ɽ (ড় written as r), no nasal vowels (চাঁদ `c a d`), a few East Bengali colloquial entries (অইছে). Both gaps can be restored from the spelling |
| Epitran `ben-Beng`, `ben-Beng-red` ✔ | MIT | Rule maps to IPA | **Wrong on schwa:** জল → d͡ʑɔl̪ɔ, মন → mɔn̪ɔ, কলকাতা → kɔl̪ɔkat̪a; phalas broken (ব্যাপার → bd͡zapar, স্বাস্থ্য → s̪bas̪t̪ʰd͡zɔ); no e→æ; ঘ output with stray diacritics |
| indic-transliteration (sanscript) | MIT | Script ↔ ISO/IAST/ITRANS | Letter-faithful only (কলকাতা → kalakātā); ব → v; decomposed nukta breaks it |
| Aksharamukha | **AGPL-3.0** | Script conversion | Not needed, and AGPL besides |
| espeak-ng `bn_rules`/`bn_list` ✔ | GPL-3.0 | Rule-based G2P and a robotic voice; the header says "improvement input by Him Prasad Gautam (Nepal)" | Has some phala and æ rules; not tested here. Use only as a fallback |
| IndicXlit / Aksharantar ([paper](https://arxiv.org/abs/2205.03018)) | MIT code, CC BY data | **Roman → Bengali** (input), top-k candidates | Input helper, not a reading aid |
| Johny & Jansche, "Brahmic schwa-deletion with neural classifiers: experiments with Bengali" (SLTU 2018) ✔ | paper | Trained on the Google lexicon | Over 85% with small models, **about 97.5% with a large model**; ô vs o realization predicted at 92.5% |

**G2P design:** normalize → lexicon lookup (with Kolkata overrides) → lemma + suffix composition (the lexicon
has the lemma, and suffixes have fixed pronunciations) → rule fallback (schwa deletion, ô/o raising, e/æ
harmony, phala rules) → optional small classifier trained on the lexicon, following Johny & Jansche, for
words still unresolved. **Kolkata override layer:** restore ɽ from ড়/ঢ় spellings, restore nasal vowels from ঁ,
and add a hand-checked patch list for East Bengali entries. **Evaluation:** hold out 5% of the lexicon and report
word accuracy and per-schwa accuracy. Target ≥ 90% words and ≥ 95% schwa decisions for the rules, with
the lexicon covering about 98% of running text in practice (section 0).

---

## 3. Tokenization and morphology

**Tokenizing** is easy: split on whitespace and punctuation (। ॥ , ? ! ; : — quotes ‘ ’ “ ”), keep whitespace
tokens (the reader re-joins tokens without a separator), treat ০–৯ and 0–9 runs as numbers, and treat Latin runs
as OTHER. Before anything else, normalize to NFC and repair the common encoding variants: nukta forms
(য় ড় ঢ়), ো/ৌ composed vs split, ZWJ/ZWNJ (ক্‌ষ with an explicit hôsôntô is legitimate), hôsôntô followed by
a stray space, and legacy khanda ta written ত্‍. `bnunicodenormalizer` (MIT) and `bkit`'s normalizer (MIT)
exist; a 60-line normalizer of our own with golden tests may be simpler. Akshara (grapheme) segmentation for
the script screen: Unicode 15.1's Indic conjunct break rule (UAX #29 GB9c) treats C+্+C as one cluster for
Bengali *(from memory)*. Use the `regex` module's `\X` with a current Unicode version, or our own splitter.

**Morphology** is the real work. Nouns take classifier, then plural, then case, then emphatic
(ছেলেটাকেও = ছেলে-টা-কে-ও "the boy too (obj.)"). Verbs inflect for person ×
register (1; 2-intimate; 2-familiar; 2/3-polite; 3) × tense and aspect (present simple, continuous, perfect;
past simple, continuous, perfect, habitual; future; imperative; plus conditional -লে, conjunctive -এ, infinitive
-তে, verbal noun -আ/-ওয়া). A regular verb such as করা has 40+ common forms. Stems alternate (কর- / কর্‌-,
দেখ- de/dæ, খা- / খে-, যা- / গে- for যাওয়া's past).

**What a "word" unit should be: the lemma.** Surface-form units would split the learner model into dozens of
cards per verb, and coverage would treat গেলাম and যাব as unrelated words. So:

- `unit(type="word")` is the dictionary form, with the verbal noun for verbs (করা, যাওয়া), as Bengali
  dictionaries and Wiktionary list them.
- Each token carries `lemma` and `morph` (features such as `{"person": "1", "tense": "past"}`, plus the suffix
  segments). The reader maps a token to its lemma's unit. Coverage counts the token as known if its lemma is known.
- Inflectional morphemes are **grammar-point units** (`type="grammar"`, e.g. `-ছি present continuous 1st
  person`, `-কে object/dative`, `-টা/-টি classifier`), carded with cloze sentences. This is the "了 / measure word"
  machinery reused.
- **Multi-word expressions** (মনে পড়া, ভালো লাগা, খেয়ে ফেলা) are `type="phrase"` units, merged by the
  pack when the parts are adjacent, the way Lute handles multi-word terms. Jieba never needed this; Bengali does.
- **Spelling variants** (ভালো/ভাল) map to one unit through `extra.variants`.

**Lemmatizers:**

| Tool | License | Notes |
|---|---|---|
| **BanLemma** ([EMNLP Findings 2023](https://aclanthology.org/2023.findings-emnlp.240)), packaged in **bkit** (PyPI 0.0.9, Mar 2025 ✔) | MIT (bkit) | Rules plus dictionary. 96.36% on its own human-annotated test set, but that assumes gold POS tags; with automatic POS it scored 80% on one cross-dataset test (Chakrabarty et al.). Built by a Bangladeshi team (EBLICT) from Bangladeshi text. **Kolkata forms such as -লুম and Kolkata vocabulary are untested** (my test was blocked) |
| BNLP (`bnlp-toolkit` 4.4.1, Apr 2026 ✔) | MIT | Tokenizers, embeddings, POS, NER, cleaning. **No lemmatizer.** Its models come from Bangladeshi data |
| banglanltk 0.0.4 (2020) ✔, bangla-stemmer 1.0 (2020) ✔ | MIT / Apache-2.0 | Suffix strippers. Stale and lossy (no stem alternation) |
| Indic NLP Library 0.92 ✔ | MIT | Normalizer, sentence splitter, unsupervised morph segmenter. Generic |
| Stanza 1.15 ✔ | Apache-2.0 | **I found no Bengali model** *(unverified: the model pages were blocked)*; to my knowledge Universal Dependencies has no sizeable Bengali treebank |

**Recommendation:** a **paradigm-generating analyzer of our own** for the closed set that matters (verb
endings, noun suffix stack, pronoun forms, which run to a few hundred rules), plus a lemma list from Wiktionary and
the frequency list. The result is a `form → (lemma, features)` table built offline and loaded like jieba's
dictionary. Use bkit/BanLemma as a fallback for unknown forms and as an evaluation baseline. The generator
also gives the bootcamp and grammar track their conjugation tables for free. Tests: golden paradigms for
করা, যাওয়া, খাওয়া, দেওয়া, আসা, হওয়া, থাকা, and Kolkata variants (-লুম, -চ্ছিস).

---

## 4. Dictionary data

| Source | Direction | Size | License | Verdict |
|---|---|---|---|---|
| **English Wiktionary via kaikki.org / wiktextract** | bn → en (POS, senses, inflection tables, some regional labels) | **9,258 Bengali words** in tdulcet/compact-dictionaries' weekly build ✔ (kaikki itself was blocked) | CC BY-SA 3.0 / GFDL | **Primary gloss source.** Small but clean; keep it in its own table like CC-CEDICT |
| Google pronunciation lexicon | spelling → phonemes | 65k ✔ | CC BY 4.0 | Readings, not meanings, and a headword list |
| Shobdo / ProjectShobdo (PyPI `shobdo`) ✔ | bn → en | 45,630 entries | Apache-2.0 (package) | **Check its provenance before use.** The package doesn't say where its definitions come from; they may be scraped from a copyrighted dictionary |
| MinhasKamal/BengaliDictionary ✔ | en → bn | "large collection" | GPL-3.0 | Usable in a separate table for production (English cue → Bengali); quality unknown; last updated 2020 |
| Facebook MUSE ground-truth en–bn ✔ | en ↔ bn word pairs | about 10–20k pairs *(unverified count)* | **CC BY-NC 4.0** | Acceptable for a personal self-hosted app (the design doc says licenses matter only if this leaves personal use); noisy, single-word only |
| IndicTrans2 (MIT) used as a gloss *suggester* | both | model | MIT | Not a dictionary; see the guardrail below |
| Samsad Bengali–English (Biswas), on DSAL Chicago | bn → en | large | © Sahitya Samsad | **No.** Lookup link only |
| Bangla Academy, Paschimbanga Bangla Akademi dictionaries | — | — | copyrighted | **No** |
| Ankur project wordlists | — | — | GPL *(unverified)* | Mostly spellcheck lists, no glosses |

**Gap and guardrail:** about 9k Wiktionary words leaves a long tail. The design doc's rule that glosses never
come from the model can be kept by splitting the problem. Readings stay local and deterministic (the lexicon).
For meanings with no dictionary entry, a **batch-enrichment job** asks the LLM for short glosses, checks them
against MUSE/IndicTrans2 back-translation, stores them in a separate table with `source="generated"`, and shows
a "machine gloss" badge. Each gloss is promoted to trusted after the learner confirms it from context. Contributing confirmed glosses
back to Wiktionary is a nice side effect.

---

## 5. Frequency, levels and Kolkata vs Bangladesh

**Frequency sources:**

| Source | Size | License | Bias |
|---|---|---|---|
| hermitdave FrequencyWords bn (OpenSubtitles 2018) ✔ | 2.64M tokens, 100k types | content CC BY-SA 4.0, code MIT ✔ | **Strongly Bangladeshi** (section 0), conversational. Good for spoken register |
| IndicCorp v2 bn ([card](https://huggingface.co/datasets/ai4bharat/IndicCorpV2)) | hundreds of millions of tokens (836M listed for bn, perhaps v1) *(unverified)* | **CC0** (datasets), MIT (code) | News and web from India and Bangladesh. **Can be split by source domain** (.in sites such as Anandabazar, Ei Samay and Sangbad Pratidin vs .bd sites) to build a West-Bengal-weighted list |
| Bengali Wikipedia | — | CC BY-SA | Formal and written; editors are mostly Bangladeshi |
| Leipzig Corpora Collection (ben) | — | *(unverified; blocked)* | — |

**Levels.** There is no HSK, no official CEFR list for Bengali (I found none), and UK GCSE/IGCSE Bengali
(AQA 8638, Pearson 4BE0) vocabulary lists are copyrighted and Bangladesh-diaspora oriented. Proposed scheme,
version-tagged like `hsk3-2025:N`:

| Tag | Content | Size (cumulative lemmas) |
|---|---|---|
| `bn-kol:survival` | Hand-curated Kolkata survival list: greetings (নমস্কার, আসছি "bye"), kin terms (মা বাবা দাদা দিদি মাসি পিসি কাকা মামা), numbers 1–100, money and prices, food (ভাত ডাল মাছ জল চা মিষ্টি), transport (ট্যাক্সি অটো মেট্রো বাস, বাঁদিকে/ডানদিকে), shops and markets, time, health basics. Written once, reviewed by a Kolkata speaker | ~300 |
| `bn-freq-2026:A1` | Top lemmas by a blended frequency (IndicCorp-India 0.6 + subtitles 0.4, after lemmatization, with Bangladesh-tagged variants pushed down) | 500 |
| `…:A2` | | 1,200 |
| `…:B1` | | 2,500 |
| `…:B2` | | 5,000 |
| `bn-gram:A1…B2` | Grammar points (suffixes, constructions) in teaching order, written by hand from Thompson's grammar | ~120 |

The level pool in the generator and the placement marks in Progress work unchanged on these tags once
`hsk_version` becomes a pack-provided level framework.

**Kolkata vs Bangladesh vocabulary** (Kolkata form first; checked against the subtitle counts and
[Wikipedia's Bengali vocabulary dialect table](https://en.wikipedia.org/wiki/Bengali_vocabulary), via search):
জল/পানি "water", নমস্কার/(আস)সালামু আলাইকুম "hello" (Kolkata Muslims also use the latter), স্নান/গোসল "bath",
মাসি/খালা "maternal aunt", পিসি/ফুফু "paternal aunt", কাকা/চাচা "paternal uncle", কাকিমা/চাচি, দিদি/আপা
"elder sister", বৌদি/ভাবি "brother's wife", জামাইবাবু/দুলাভাই, ঠাকুমা/দাদি "paternal grandmother",
**দাদা** = elder brother in Kolkata but paternal grandfather in Bangladesh (a false friend), লঙ্কা/মরিচ "chilli",
নিমন্ত্রণ/দাওয়াত "invitation", নুন/লবণ "salt", রবিবার/রোববার "Sunday", সঙ্গে/সাথে "with" (both occur in
Kolkata speech; সাথে dominates Bangladeshi text), খিদে/খিদা "hunger", মা বাবা/আম্মা আব্বা. No open, citable list
of more than about 30 pairs exists that I could find, so **we write the list (~150 pairs)**. Wiktionary
sense tags ("Bangladesh", "India", "West Bengal") seed it *(the presence of such tags is unverified)*.

**Tagging:** `unit.extra.region ∈ {"wb", "bd", "both"}` plus `extra.region_pair` → the other form's unit
id (a `unit_relation(kind="regional_variant")`). The lookup sheet shows "Kolkata: জল · Bangladesh: পানি". The
generator and tutor lint flags `bd` words in their output (section 9). Imported Bangladeshi texts still
work: `bd` words are minable and labelled.

---

## 6. Example sentences

| Source | Size (bn) | License | Register and variety |
|---|---|---|---|
| Tatoeba `ben` | a few thousand *(unverified; tatoeba.org blocked)* | CC BY 2.0 FR | Mixed contributors, many Bangladeshi; short and conversational. Import with the existing importer (parameterized) and tag the region with the variant lint |
| **IN22-Conv** (AI4Bharat) | ~1.5k conversational sentences per language *(unverified count)* | **CC BY 4.0** ✔ (per AI4Bharat's license table, via search) | Human-translated by Indian translators; conversational. Best seed for Kolkata-style dialogue examples |
| **BPCC-H-Daily** (IndicTrans2's seed corpus) | thousands *(unverified)* | CC BY 4.0 | Human-translated everyday sentences, India-centric |
| FLORES-200 `ben_Beng` | 2,009 sentences | CC BY-SA 4.0 | Wikipedia-style formal written prose; only useful for B2 reading |
| Samanantar en–bn ([page](https://indicnlp.ai4bharat.org/samanantar)) | 8.52M pairs (v0.2) | CC0 for the packaging per AI4Bharat; the HF card says CC BY-NC 4.0 | Mined, noisy, news register. Usable for frequency and examples only after filtering |
| BanglaNMT (csebuetnlp) | 2.38M pairs | *(unverified)* | Bangladeshi sources |

Plan: Tatoeba + IN22-Conv + BPCC-H-Daily, each sentence passed through the bn pack, the variant lint and a sadhu-form
filter, then ranked by the existing "how much can you read" score. Generated sentences fill the gaps, labelled as
generated. Expect thin coverage for B1+ words; that is where imported texts take over.

---

## 7. TTS and ASR

| Engine | Bengali voices | License | Hardware | Verdict |
|---|---|---|---|---|
| Kokoro / misaki | none | Apache-2.0 | — | Not usable for bn |
| **AI4Bharat Indic Parler-TTS** ([card](https://huggingface.co/ai4bharat/indic-parler-tts)) | 69 named speakers across 18 languages; Bengali voices include "Arjun" (m) and "Aditi" (f) *(names via third-party pages)*; style controlled by a text description | **Apache-2.0** (per the card, via search) | ~0.9B params (Parler Mini v1.1 fine-tune, 8,385 h) → **GPU PC**; slow on CPU *(speed unverified)* | **First choice on the GPU PC.** Trained on IndicVoices-R and Indian studio data, so Indian Bengali |
| **AI4Bharat Indic-TTS** FastPitch + HiFi-GAN ([repo](https://github.com/AI4Bharat/Indic-TTS)) ✔ | Bengali male and female (13 languages) | **MIT** (repo LICENSE.txt ✔); runs on Coqui TTS (MPL-2.0) | non-autoregressive → **CPU-feasible on the homelab** | **First choice on the homelab CPU**, two voices. Trained on the IIT Madras IndicTTS database (Indian speakers; Kolkata accent unverified) |
| **IndicF5** ([repo](https://github.com/AI4Bharat/IndicF5)) ✔ | any voice, cloned from a reference clip and transcript; 11 languages, 1,417 h | MIT *(per secondary sources; the repo README states no license)* | GPU | Many voices for multi-speaker listening, using reference clips from OpenSLR-37 bn_in |
| MMS-TTS `ben` | one voice | **CC BY-NC 4.0** | VITS, fast on CPU | Personal-use fallback; variety unclear (Bible recordings) |
| Piper | **no Bengali voice** in the official VOICES.md ✔ (Hindi only) | GPL-3.0 (`piper-tts` 1.8) | CPU | Could train a bn_IN voice from **OpenSLR-37 bn_in** (Google, 416 MB, CC BY-SA 4.0 ✔ via search) on the GPU PC. Later stage |
| espeak-ng bn ✔ | robotic | GPL-3.0 | CPU | Test only (the `synth` engine's role) |
| **Apple device voice** | **Bengali (India)** is listed for VoiceOver, Live Speech and Read & Speak ([Apple](https://support.apple.com/en-hk/111748), [feature availability](https://www.apple.com/ios/feature-availability/)) | — | device | Fallback, as zh-CN is now. **Check that Safari's `speechSynthesis.getVoices()` exposes `bn-IN`**; it isn't guaranteed that every VoiceOver voice is exposed to the Web Speech API |

**Text normalization before TTS:** numbers and dates to words (`indic-numtowords`, MIT ✔, has bn), ৳/₹ and
abbreviations; every engine misreads digits otherwise.

**ASR:**

| Model | License | Bengali quality |
|---|---|---|
| **IndicConformer** bn hybrid CTC/RNNT large, 120M ([repo](https://github.com/AI4Bharat/IndicConformerASR)) | **MIT** (via search) | Mean WER 22.7% across six Bengali test sets in the SraVaani 1.0 paper (arXiv 2608.08235, via search). Needs AI4Bharat's NeMo fork; a sherpa-onnx int8 export exists (community) |
| Whisper large-v3 | MIT | Weak on Bengali: 71% WER (Dataocean) and 77% (Common Voice 17) as reported in the Dolphin paper (arXiv 2503.20212, via search) |
| MMS-1B ASR | CC BY-NC 4.0 | Usable for alignment and phoneme posteriors |

**What replaces the tone check:** Bengali has no lexical tone, and vowel length isn't phonemic. Feedback
that matters, in order:

1. **Intelligibility:** say a sentence, run IndicConformer, diff against the target, highlight missed words.
2. **Vowel quality** for ô/o, e/æ and a: the F1/F2 point of each stressed vowel plotted against target regions
   calibrated from TTS and OpenSLR-37 bn_in speakers. Formant tracking works in the browser like the
   existing YIN pitch tracker (LPC).
3. **Aspiration:** voice onset time and post-release breath noise, scored on bootcamp minimal pairs (কাল/খাল,
   জাল/ঝাল, দান/ধান, বাত/ভাত).
4. **Intonation:** the existing pitch-contour UI reused for statement vs yes/no question (the L* H L% rise-fall)
   and focus.
5. Dental vs retroflex, and ড় vs র: hard to score reliably from audio; perception drills only, with no
   automated scoring.

**Voice check** (Progress → Voice, replacing "Check tones"): synthesize about 40 trap words (schwa: জল, মন,
কলকাতা, বলো, করব; phala: ব্যাপার, বিশ্ব, পদ্ম; ড়: গাড়ি; aspirates; nasal vowels: চাঁদ), run them through
IndicConformer, and listen. Score intelligibility, and let the learner mark a voice that drops schwas wrongly. The
voice's G2P is the risk here, not its pitch.

---

## 8. Writing practice

- **No open stroke-order dataset for Bengali exists** that I could find (searched; the hits are offline
  recognition sets such as BanglaWriting, 32,787 characters, [arXiv 2011.07499](https://arxiv.org/abs/2011.07499),
  and BengaliAI's grapheme set). Nothing like Make Me a Hanzi.
- **How to make one:** Hanzi Writer renders any glyph given `{strokes: [SVG paths], medians: [[x,y]…]}` in its
  1024-unit box through a custom `charDataLoader` *(from its docs, from memory)*, so the existing WritingPad,
  Pencil palm rejection and mistake→rating mapping carry over unchanged. Take outlines from **Noto Sans
  Bengali** (SIL OFL 1.1; any glyph modification keeps OFL). Split each glyph into strokes in a small
  authoring tool (draw medians on the glyph, cut the outline along them), then hand-check the order. Scope: 11 vowels + 35 consonants +
  10 vowel signs (written on ক) + ং ঃ ঁ ৎ ্ + 4 phalas and reph + 10 digits ≈ **75 items**, then the **top 100
  conjuncts** (section 0). Most letters are 1–4 strokes. Convention: the body first, the headline (মাত্রা) last;
  ি/ী/ে/ৈ strokes before the consonant in writing order. **A Kolkata primary-school teacher should check the
  stroke order**, since conventions vary and no authoritative open source exists (Vidyasagar's বর্ণপরিচয়, 1855, public
  domain, fixes letter order but not strokes). Effort: about 15–25 hours for the letters, as much again for the conjuncts.
- **Grading:** Hanzi Writer's median matching, as now. Free-form recognition (writing whole words) has no
  open browser-grade option (Google ML Kit digital ink supports bn but is a mobile SDK, not web). Out of scope.
- **Writing-specific content:** dictation of known words (spelling: শ/ষ/স, ই/ঈ, hôsôntô) is more valuable
  than letter shapes after week 2. Make it a "spelling" facet typed through the input helper (section 10).

---

## 9. LLM quality and register

- **Evidence:** Bengali is mid-resource for frontier models. Bhowmik et al. 2025 ([arXiv
  2507.23248](https://arxiv.org/abs/2507.23248)) find consistent gaps against English, worst for small models, and an
  inverse link between tokenization inefficiency and accuracy. BLUCK ([arXiv
  2505.21092](https://arxiv.org/abs/2505.21092)) puts GPT-4o and Claude 3.5 Sonnet at about 73% on Bangladeshi
  culture and language MCQs, with phonetics questions near 0.38–0.41. **I found no study of Kolkata vs Dhaka
  bias in generation**; the training data (web, Wikipedia, news) leans Bangladeshi, and section 0's corpus
  measurement shows how strongly.
- **Risks:** (1) drifting into **সাধু ভাষা** (করিয়া, করিতেছে, তাহার, যাহা, ইহা) in "literary" genres; (2)
  **Bangladeshi lexicon and kinship** (পানি, গোসল, আপা, ভাবি, দাওয়াত) and Dhaka colloquial (করতেছি); (3)
  register mismatch: mixing তুমি and আপনি verb forms in one dialogue; (4) unnatural calques from English;
  (5) spelling-variant churn (ভাল/ভালো), which harms coverage unless variants are unified.
- **Prompt profile for the bn pack:** "Write Standard Colloquial Bengali (চলিত ভাষা) as spoken in Kolkata,
  West Bengal, India. Never sadhu bhasha. Use Kolkata words: জল not পানি, স্নান not গোসল, দিদি not আপা,
  নমস্কার for greetings, মাসি/পিসি/কাকা for aunts and uncles. Keep one register per speaker (তুই/তুমি/আপনি)
  and conjugate to match. Follow Paschimbanga Bangla Akademi spelling: ভালো, কী for 'what'. Names and places
  from Kolkata (Gariahat, Esplanade, College Street, Salt Lake)." Plus three short few-shot sentences.
- **Deterministic register lint** (in the pack, run in the generator's repair loop and on tutor replies,
  as `off_level` is now): flag sadhu verb and pronoun forms by suffix and lemma table, flag `region="bd"`
  lemmas, flag register switches per speaker. Lint hits go into the same "replace these words" repair
  prompt as out-of-level words. Journal correction gains categories `sadhu_form`, `regional_variant` and
  `register_agreement`.

---

## 10. Input

- **iPhone/iPad:** Apple lists **Bangla InScript, QWERTY, Transliteration and Alphabetic** keyboards
  ([QuickType language support](https://www.apple.com/ios/feature-availability/), via search), and the iOS 18
  multilingual keyboard covers English + Bangla ([Apple](https://support.apple.com/en-au/121233)). The
  transliteration keyboard is Avro-like phonetic typing. **Mac:** macOS has Bangla input sources (InScript,
  QWERTY) *(a transliteration source on macOS is unverified)*. Dictation in Bengali: reportedly unavailable on iOS
  *(Apple Community, unverified)*.
- **In-app helper:** worth adding because the learner knows our romanization from the reader. Type `jol`,
  `bolo`, `kolkata` in our romanization and get candidates ranked from (1) the learner's own known and level
  words, matched on their stored readings (exact and fuzzy), then (2) Avro phonetic output. That avoids Avro's
  native-speller assumptions: I measured `kolkata` → কল্কাতা (wrong conjunct) and `tomake` → তমাকে (Avro
  needs `tOmake`).
- **Engines:** `avro.py` (MIT OR Apache-2.0 ✔, 2025) server-side; jsAvroPhonetic (MPL-1.1 ✔) client-side;
  OpenBangla Keyboard (GPL-3.0 ✔) for reference only. IndicXlit (MIT) gives model-based top-k candidates but needs
  fairseq. Put it in the speech container if ever.

---

## Parity table

Mandarin features from `README.md` and their Bengali equivalents. Feasibility: **ready** (core plus pack data,
no new research), **needs work** (known approach, real build effort), **not feasible yet**.

| Mandarin feature | Bengali equivalent | Data and tools | Feasibility |
|---|---|---|---|
| Reader with ruby pinyin over new and learning words, status colours, text size, tone colours | Reader with **phonetic romanization** over or under new and learning words, the same colours, "spelling traps" highlight in place of tone colours, `lang="bn-IN"`, Bengali font stack (Kohinoor Bangla / Bangla Sangam MN on Apple, Noto Sans Bengali fallback), taller line height for vowel signs, । kept on the line | bn pack (normalizer, tokenizer, analyzer, G2P), Google lexicon | needs work (pack), then ready |
| Tap lookup: tones, HSK level, measure words, meanings, character decomposition | Romanization + ISO + IPA, level tag, region (Kolkata/Bangladesh pair), **morph breakdown** (ছেলে + টা + কে = "the boy" + classifier + object), meanings, akshara/conjunct breakdown (ক্ষ = ক + ষ, "sounds kkh"), classifier preference (-টা/-টি/-জন/-খানা) | Wiktionary (9k), analyzer, conjunct table, machine-gloss table | needs work |
| Mining with context sentence; placement by level | The same; mines the **lemma** (and offers the grammar point the form showed) | — | ready after the core changes |
| FSRS facets: meaning, reading, listening, cloze; offline outbox | meaning, listening (both default), **reading** = see script → say or pick pronunciation (default for the first months and for words with spelling traps), **spelling** (English or audio → type Bengali; opt-in), cloze for grammar points | analyzer, G2P | ready (scheduler is language-agnostic) |
| Sound bootcamp: tones, initials/finals, minimal pairs, sandhi drill, Say-it pitch | **Script and sound bootcamp:** the consonant grid, vowel signs, inherent vowel and schwa deletion, phalas and conjuncts; drills: aspiration (4 series), dental/retroflex, ô/o, e/æ, ড়/র, nasal vowels, gemination; a **"how is it said" drill** (see the spelling, pick the romanization: the sandhi drill's twin); Say-it with intonation contour and vowel plot | TTS voices, lexicon, OpenSLR-37 bn_in clips as "recorded voices" (like Tone Perfect) | needs work |
| Handwriting track (Hanzi Writer, Pencil, official list, own daily session) | Letter and conjunct tracing with the same component; list = 75 letters/signs then top 100 conjuncts; then spelling dictation | **Self-authored stroke data** from Noto Sans Bengali | needs work (data authoring is the long pole) |
| Graded-reader generator with coverage check and repair | The same loop; pack prompt profile; coverage on lemmas; register and variant lint in the repair prompt | LLM, levels | ready after the core changes; quality risk (section 9) |
| Journal with categorized corrections → cloze | The same; bn categories: verb agreement (person/register), tense-aspect, case marker, classifier, postposition, word order, spelling (শ/ষ/স, ই/ঈ, hôsôntô), register (তুই/তুমি/আপনি), sadhu form, regional variant, word choice, missing/extra word | LLM | ready after the core changes |
| Tutor role-play | The same scenarios relocated to Kolkata (an adda at a tea stall, a yellow taxi, New Market, a Durga Puja pandal, a doctor's chamber); register choice is part of the task | LLM, scenario phrase lists | needs work (content) |
| Importer: paste, link, EPUB, SRT/VTT, Jellyfin, coverage preview | The same with a Bengali script detector (bn ratio in place of Han ratio), bn subtitle codes (`bn`, `ben`, `bn-IN`), `Accept-Language: bn-IN`; **legacy Bijoy/SutonnyMJ ASCII-font text** detection and conversion (common in older Bangladeshi and some Indian PDFs and sites; converter to be written or found) | — | needs work (small) |
| Characters screen (character page, component explorer, opaque notes) | **Script screen:** a page per letter and conjunct (animation, sound, "words you know with ক্ষ"); conjunct explorer grouped by first or second member; "opaque" notes for conjuncts whose sound misleads (জ্ঞ, ক্ষ, হ্ম, silent ব/ম-ফলা) | conjunct table, lexicon | needs work |
| Speech service (Kokoro, cache, pre-render, device fallback, host list) | Same service, **engine per language**: Indic-TTS FastPitch on the homelab CPU, Indic Parler-TTS / IndicF5 on the GPU PC, Bengali (India) device voice as the fallback | AI4Bharat models (huggingface.co must be reachable) | needs work |
| Tone check (voice scoring) | **Voice check** on schwa, phala, ড় and aspirate trap words via IndicConformer, plus listening | IndicConformer | needs work |
| SUBTLEX frequency rank in lookup | Blended West-Bengal-weighted lemma frequency | IndicCorp v2 (CC0), OpenSubtitles (CC BY-SA) | needs work |
| Tatoeba examples, "Real sentences" | Tatoeba + IN22-Conv + BPCC-H-Daily, variant- and sadhu-filtered | — | ready after the importer is generalized; thin data |
| Levels/progress (HSK 3.0 bars, placement) | `bn-freq-2026` A1–B2 bars + Kolkata survival list + grammar points; "letters and conjuncts known" in place of characters; words read in place of characters read | curated lists | needs work (content) |
| Nightly FSRS re-fit | Unchanged (per user, across languages; consider per-language parameters later) | — | ready |
| Medical track (future) | Kolkata clinical Bengali exists (doctors switch freely to English terms), but no open MCT-like syllabus | — | not feasible yet |
| ASR voice tutor (future in zh too) | IndicConformer | GPU or CPU | not feasible yet (no zh equivalent built either) |

---

## 11. Pack design

### Chinese assumptions in the code today, file by file

Core (must change for any second language):

| File | Assumption |
|---|---|
| `backend/app/packs/__init__.py` | `get_pack` knows only `"zh"`; `INSTALLED` has one entry |
| `backend/app/packs/base.py` | `Syllable` has tone-specific fields (citation/surface "bu4"/"bu2"); `Token` has no `lemma` or `morph`; no hooks for normalization, sentence joining, script detection, coverage matching, level framework, prompt profile, BCP-47 tag or TTS language |
| `backend/app/reader.py` | `resolve_units` maps by `headword == surface` and picks a reading from `syllables[].citation`; `sentence_map(language="zh")` default; comment "Pinyin is recomputed" |
| `backend/app/api/lookup.py` | Rejects `language != "zh"`; imports `app.packs.zh.pinyin` (sandhi, tone marks); queries `CedictEntry` and `CharacterInfo`; `sub_units` treated as characters; hard-coded attribution string |
| `backend/app/api/reviews.py` | `meanings_for` falls back to CC-CEDICT matched by pinyin; `reading_display` built with `numeric_to_marks`; `classifiers` field |
| `backend/app/units.py` | `ensure_character` is zh-only, with a pypinyin reading |
| `backend/app/generator.py` | Mandarin `SYSTEM` prompt; JSON keys `zh`/`question_zh`; Chinese terminators `。！？`; `"、"` list joiner; dialogue rule with a full-width colon; `"".join(sentences)` (Bengali needs a space); `_covered` substring DP (jieba merges; wrong for Bengali); `_hsk_level_pool` reads `settings.hsk_version` and `Unit.language == "zh"`; `get_pack("zh")` |
| `backend/app/journal.py` | Mandarin prompt; categories `measure_word`, `aspect_particle`, `wrong_character`; `ASPECT = {了, 过, 着}`; `citation_syllables` for phrase readings; `MAX_CLOZE_CHARS = 12` in code points (Bengali words are longer); `"".join` of corrected sentences; HSK level |
| `backend/app/tutor.py`, `backend/app/api/tutor.py` | Mandarin prompt, `zh` keys, `title_zh` scenarios with Chinese phrases, `get_pack("zh")`, `"、"` joins |
| `backend/app/api/progress.py` | `hsk_version` tags; `known_characters` = code points of headwords (meaningless for Bengali); `characters_read` = `length(surface)` |
| `backend/app/api/mine.py` | `ALLOWED_FACETS` is a fixed set including `tone`; `level_tag` bulk mark scans all units with no language filter |
| `backend/app/api/sentences.py` | `"zh"` hard-coded; title `例句 · Sentences`; `"".join`; key `zh` |
| `backend/app/api/texts.py`, `api/importing.py`, `api/progress.py`, `api/lookup.py` | `language: str = "zh"` defaults; the PWA never sends a language |
| `backend/app/models.py` | `WordFrequency` and `ExampleSentence` have **no language column**; `CedictEntry`, `CharacterInfo` and `CharacterStrokes` are zh-specific tables (fine as pack tables, but core code queries them); `AudioSyllable` keys are pinyin; `Unit.reading` comment says pinyin |
| `backend/app/config.py` | `hsk_version`, `audio_dir=/data/toneperfect` |
| `backend/app/speech.py` | One install-wide chosen voice (`setting("speech").voice`), with no language |
| `backend/app/importers/tatoeba.py` | `cmn` files, CJK and Traditional filters, `get_pack("zh")`, `record_version(db, "zh", …)` |
| `backend/app/importing/textutil.py` | `han_count`/`han_ratio`; `decode` tries GB18030/Big5 |
| `backend/app/importing/subtitles.py`, `epub.py`, `draft.py` | Chinese line detection by Han ratio; chapters with `han_count == 0` dropped; previews count Han "characters" |
| `backend/app/importing/jellyfin.py` | `CHINESE_CODES` and Chinese track names |
| `backend/app/importing/web.py` | `Accept-Language: zh-CN` |
| `backend/app/bootcamp/*`, `backend/app/tonecheck.py`, `backend/app/jobs.py` (`tone_check`) | Wholly Mandarin (tones, pinyin initials and finals, pypinyin soundbank, sandhi) |
| `backend/app/characters.py`, `api/characters.py`, `api/handwriting.py` | Make Me a Hanzi, pinyin and `Unit.language == "zh"` throughout |
| `speech/bhasha_speech/engines/kokoro_engine.py`, `synth.py`, `app.py` | Kokoro `lang_code="z"`, Mandarin voice list; `/tts` takes no language; the test engine uses pypinyin |
| `web/src/speech.ts` | Picks a `zh-CN` voice and sets `u.lang = "zh-CN"` |
| `web/src/views/*.tsx`, `components/*.tsx` | `lang="zh-CN"` on text (affects font choice and line breaking); Pinyin component and tone colours; ruby built from `syllables[].surface_display`; `NO_LINE_START` kinsoku regex lacks `।`; LookupSheet fields (tones, measure words, characters); WritingPad loads Hanzi Writer data by character; Progress and HandwritingProgress show HSK; Sounds tab is tones; `api.ts` types with `zh`/`title_zh`/`question_zh` keys; `settings.pinyin` |

### Interface changes (Python)

```python
# backend/app/packs/base.py (sketch)

@dataclass
class ReadingPart:            # replaces Syllable; zh keeps tones in `extra`
    text: str                 # written span (zh: one character; bn: the whole word or an akshara run)
    citation: str             # canonical stored form (zh "bu4"; bn ISO 15919 "kalakātā")
    surface: str              # canonical spoken form (zh "bu2"; bn phonemic "k o l . k a . t a")
    citation_display: str     # zh "bù"; bn ISO with diacritics
    surface_display: str      # zh "bú"; bn learner romanization "kolkata"
    traps: list[tuple[int, int, str]] = field(default_factory=list)  # bn: spans where sound != letters
    extra: dict = field(default_factory=dict)                        # zh: {"tone": 2}

@dataclass
class Morph:
    segment: str              # "কে"
    grammar_key: str | None   # "bn-gram:case-ke" -> a grammar unit
    features: dict

@dataclass
class Token:
    surface: str
    kind: str
    sentence_index: int
    syllables: list[ReadingPart] = field(default_factory=list)   # name kept for the API
    lemma: str | None = None  # bn: dictionary form; zh: None (= surface)
    morph: list[Morph] = field(default_factory=list)
    variant_of: str | None = None   # bn: ভাল -> ভালো

@dataclass
class LevelFramework:
    tag_prefix: str           # "hsk3-2025" | "bn-freq-2026"
    levels: list[str]         # ["1".."7"] | ["A1","A2","B1","B2"]
    labels: dict[str, str]
    extra_tags: list[str]     # ["bn-kol:survival"]

@dataclass
class PromptProfile:
    language_name: str        # "Mandarin Chinese (Simplified)" | "Standard Colloquial Bengali (Kolkata)"
    style_rules: str          # appended to the generator, journal and tutor system prompts
    list_joiner: str          # "、" | ", "
    error_categories: dict[str, str]
    dialogue_rule: str

class LanguagePack(ABC):
    code: str; name: str
    bcp47: str                       # "zh-CN" | "bn-IN" (lang attribute, device TTS)
    default_facets: tuple[str, ...]
    facets: frozenset[str]           # allowed facets (replaces ALLOWED_FACETS)
    sentence_joiner: str             # "" | " "
    terminators: str                 # "。！？" | "।?!"
    max_cloze_len: int               # in code points
    levels: LevelFramework
    prompts: PromptProfile
    subtitle_codes: frozenset[str]   # jellyfin: {"zh","chi",...} | {"bn","ben","bn-in"}
    accept_language: str

    def normalize(self, text: str) -> str: return text
    @abstractmethod
    def analyze(self, text: str) -> list[Token]: ...
    def unit_key(self, tok: Token) -> tuple[str, str, str]:
        """(unit type, headword, reading) a token maps to. zh: ("word", surface, citation pinyin);
        bn: ("word", lemma, lemma reading), or ("phrase", ...) for multi-word expressions."""
    @abstractmethod
    def reading(self, word: str) -> str: ...
    def reading_display(self, reading: str) -> str: ...      # replaces numeric_to_marks in core
    @abstractmethod
    def sub_units(self, word: str) -> list[str]: ...           # zh characters; bn letters/conjuncts
    def sub_unit_type(self) -> str: ...                        # "character" | "akshara"
    def covered(self, tok: Token, allowed: set[str]) -> bool:  # zh: the substring DP; bn: lemma in allowed
        return (tok.lemma or tok.surface) in allowed
    def script_ratio(self, line: str) -> float: ...            # importer language detection
    def script_count(self, text: str) -> int: ...              # "3,400 characters" / "620 words"
    def lint(self, tokens: list[Token]) -> list[dict]: return []   # bn: sadhu, region, register
    def lookup_extras(self, db, word: str) -> dict: return {}      # pack-specific lookup sections
    def meanings(self, db, unit) -> list[str]: ...                 # replaces CEDICT fallback in reviews
```

**Core changes that go with it:**

1. **Language threading:** a per-user active language (`app_user.active_language` or an `app_setting`),
   sent by the PWA on every call. API defaults read it instead of `"zh"`. `get_pack` uses a registry.
2. **Migrations:** add `language` to `word_frequency` (primary key `(language, word)`) and `example_sentence`; add a
   generic `dictionary_entry(language, source, headword, reading, pos, glosses, tags, license)` with one source per
   share-alike license (`cc-cedict` keeps its own table; `wiktionary-bn` goes here); generalize
   `audio_syllable` to `audio_item(language, key, speaker, path)`; make the voice setting per language
   (`setting("speech:bn")`).
3. **Move zh-only modules behind the pack:** `bootcamp/`, `tonecheck.py`, `characters.py`, `units.ensure_character`,
   the CEDICT parts of lookup/reviews and the HSK pool move to `packs/zh/` behind hooks. Core routes check
   `pack.has("bootcamp")` and similar.
4. **Generator, journal and tutor** build prompts from `pack.prompts`, use `pack.sentence_joiner`,
   `pack.covered`, `pack.lint` and `pack.levels`. The JSON keys `zh`/`question_zh` become `text`/`question` (keep
   reading the old keys from stored `meta` for old texts).
5. **Reader:** `resolve_units` calls `pack.unit_key(tok)` and creates lemma units; `serialize_text` adds `lemma`,
   `morph` and `traps` per token.
6. **Speech:** `/tts` takes `language`; the speech service loads engines per language (`SPEECH_ENGINES=zh:kokoro,bn:indictts`)
   and reports `voices` per language.
7. **PWA:** `lang={pack.bcp47}` everywhere; `ReadingAid` component (pinyin/tones for zh, romanization/traps for bn)
   chosen from pack metadata served by `/api/languages`; a kinsoku set from the pack; settings `pinyin` becomes
   `readingAid`.

### The `bn` pack

```
backend/app/packs/bn/
  pack.py            BnPack(LanguagePack)
  normalize.py       NFC + nukta, ো/ৌ, ZWJ/ZWNJ, hôsôntô spacing, khanda ta, digit handling
  tokenize.py        whitespace/punct split, danda sentences, numbers, Latin, MWE merge
  morph.py           paradigm generator + analyzer (form -> lemma, features, suffix segments)
  paradigms/         verb classes, noun suffix stack, pronouns, Kolkata variants (-লুম)  [data, hand-written]
  g2p.py             lexicon -> lemma+suffix -> rules -> (optional) classifier; Kolkata overrides
  romanize.py        phonemes -> learner romanization; spelling -> ISO 15919; trap spans
  akshara.py         grapheme/conjunct segmentation, conjunct table (members, sound, opaque notes)
  lint.py            sadhu forms, region="bd" lemmas, register agreement
  prompts.py         PromptProfile (Kolkata colloquial rules, few-shot)
  data/
    lexicon_overrides.tsv   Kolkata patches to the Google lexicon (CC BY 4.0 base, attributed)
    variants.tsv            spelling variants -> canonical
    regional_pairs.tsv      WB <-> BD lemma pairs (~150, hand-curated)
    survival.tsv            Kolkata survival list (~300)
    grammar_points.tsv      ~120 points with level, suffix keys, English explanations
```

**Importers** (`backend/app/importers/bn_*.py`, idempotent and version-recorded like the zh ones):
`bn_lexicon` (Google lexicon → G2P table, CC BY 4.0), `bn_wiktionary` (kaikki JSONL → `dictionary_entry` +
lemma units + inflection tables to seed `morph`), `bn_frequency` (OpenSubtitles list + IndicCorp-India counts →
lemma ranks → `bn-freq-2026:*` tags), `bn_curated` (survival list, regional pairs, grammar points), `tatoeba`
(parameterized `ben`), `bn_in22`/`bn_bpcc` (IN22-Conv, BPCC-H-Daily), `bn_strokes` (our stroke JSON → the generalized
`CharacterStrokes`), later `openslr37` (bn_in clips → `audio_item` for drills and IndicF5 reference voices).

**Unit types:** `word` (lemma; reading = phonemic string; `extra`: pos, glosses source, region, variants,
classifier preference, irregular-reading flag), `phrase` (MWE and set phrases), `grammar` (suffix or
construction; cloze cards), `letter` (vowels, consonants, vowel signs, diacritics), `conjunct` (with
`unit_relation(kind="contains")` to its letters, and words → conjuncts as zh words → characters).

**Level tags:** `bn-freq-2026:A1|A2|B1|B2`, `bn-kol:survival`, `bn-gram:A1…`, `bn-script:1…4` (letters in
teaching order, then conjunct bands by frequency).

**Reading-aid format sent to the PWA** (per word token; one `ReadingPart` spanning the word):

```json
{"surface": "ছেলেটাকে", "kind": "word", "lemma": "ছেলে", "unit_id": 812, "status": "learning",
 "syllables": [{"text": "ছেলেটাকে", "citation_display": "chēlēṭākē", "surface_display": "chheleṭake",
                "traps": [[0, 2, "e-not-æ"]]}],
 "morph": [{"segment": "টা", "grammar_key": "bn-gram:clf-ta"}, {"segment": "কে", "grammar_key": "bn-gram:case-ke"}]}
```

### Staged build plan

Each stage ends usable and keeps every Mandarin test green.

**Stage 0: language-agnostic core (no visible change for zh).**
Interface above; registry; language threading; migrations (language columns, `dictionary_entry`, `audio_item`,
per-language voice); move zh-only modules behind the pack; PWA reads pack metadata.
*Tests:* the whole existing suite; a **toy space-delimited pack** (`xx`, fixtures only) driven through
create_text → serialize → mine → review → progress → generator check with the fake OpenAI; an architecture test
that nothing outside `app/packs/zh/` imports `app.packs.zh` or `pypinyin`/`jieba`; API tests that `language=xx`
never touches CEDICT tables.

**Stage 1: readable and reviewable Bengali texts.**
Normalizer, tokenizer, `morph` with core paradigms, G2P (Google lexicon + rules + Kolkata overrides),
romanization and ISO, Wiktionary and lexicon importers, provisional frequency tags from OpenSubtitles, paste
import, reader with romanization and traps, lookup (glosses, romanization, morph breakdown, region),
mining of lemmas, meaning/listening/reading facets, device `bn-IN` voice.
*Tests:* normalization golden cases (U+09DF vs য+়, ো split, ZWNJ, ত্‍); tokenizer (danda, quotes, digits,
Latin, MWE merge); **G2P on a 5% held-out slice of the lexicon: ≥ 90% word accuracy and ≥ 95% schwa decisions for the rules
alone**, plus a 200-word Kolkata golden list checked by a native speaker (ড়, nasal vowels, æ); paradigm round-trip
(generate every form of করা/যাওয়া/খাওয়া/দেওয়া/আসা/হওয়া/থাকা, analyze back to the lemma); coverage on a fixed
paragraph; the reader serializes `lemma`/`morph`; lookup on a word without a dictionary entry still returns the reading.

**Stage 2: levels, examples and LLM features.**
Blended West-Bengal frequency (IndicCorp India split), A1–B2 tags, survival list, regional pairs, grammar
points, Tatoeba/IN22-Conv/BPCC import, generator/journal/tutor through `PromptProfile`, register lint in the repair
loop, bn journal categories, Kolkata tutor scenarios, machine-gloss enrichment with a badge.
*Tests:* lint flags each sadhu form and `bd` lemma in fixtures and passes Kolkata fixtures; the generator repair
prompt names lint hits (fake OpenAI); journal error verification works with space-joined sentences and longer
cloze spans; the level pool picks `bn-freq-2026` words; example ranking prefers readable sentences; progress
shows A1–B2 bars.

**Stage 3: speech and the sound bootcamp.**
Speech service per-language engines (Indic-TTS FastPitch on CPU; Indic Parler-TTS and IndicF5 on the GPU PC),
number normalization, pre-rendering, voice check; bootcamp lessons (consonant grid, vowel signs, schwa,
phalas) and drills (aspiration, dental/retroflex, ô/o, e/æ, ড়/র, nasal, gemination, "how is it said");
OpenSLR-37 bn_in clips as recorded voices; Say-it with intonation and vowel plot.
*Tests:* engine selection by language (with the `synth` engine extended to emit bn test audio); TTS text
normalization (১২৫ টাকা → একশো পঁচিশ টাকা); drill item generation from lexicon pairs; weighting and mastery as for zh;
formant tracker against synthetic vowels (like the YIN tests).

**Stage 4: script screen and handwriting.**
Stroke-authoring tool and data for 75 letters/signs then 100 conjuncts, reviewed by a teacher; letter and
conjunct pages; conjunct explorer; opaque-conjunct notes; handwriting session with the list in teaching order;
spelling dictation facet with the input helper.
*Tests:* stroke JSON schema and Hanzi Writer compatibility (medians inside outlines, stroke count matches);
akshara segmentation on fixtures; every top-150 conjunct has a table entry; the input helper ranks known words
first for `jol`, `kolkata`, `tomake`.

**Stage 5: authentic input and ASR.**
Importers with the bn script detector, Jellyfin `bn` tracks, `Accept-Language: bn-IN`, Bijoy-to-Unicode conversion;
IndicConformer intelligibility scoring in Say-it.
*Tests:* bilingual SRT keeps the Bengali lines; Bijoy fixture converts; EPUB chapter counts use words; ASR diff
highlights the missed word on a recorded fixture.

---

## Open risks

1. **No Kolkata-specific open corpus.** Frequencies, Tatoeba, the lemmatizer and the Google lexicon all lean
   Bangladeshi. The Kolkata layer (overrides, regional pairs, survival list, lint) is hand-made and needs a
   native Kolkata reviewer. Budget for it.
2. **Gloss coverage.** About 9k Wiktionary words; beyond that, glosses are machine-made unless a licensable
   dictionary appears. This bends the "model never supplies glosses" rule and needs the badge and confirmation flow.
3. **LLM register drift** (sadhu, Dhaka vocabulary, mixed তুমি/আপনি). The lint catches lexical drift, not
   unnatural syntax. Flags and Tatoeba/IN22 references matter more than for zh.
4. **Morphology.** Our own analyzer is the right call, but it's the biggest new code. Coverage numbers are only as good
   as lemma resolution, and errors look like "you don't know গেলাম" when you know যাওয়া.
5. **TTS on CPU.** Only Indic-TTS FastPitch is clearly CPU-friendly; Parler/IndicF5 want the GPU PC. Voice
   accents are unverified for Kolkata, and a voice's own G2P may drop schwas wrongly, which teaches wrong
   pronunciation (hence the voice check).
6. **Stroke data is invented by us.** Without a teacher's review it may teach a non-standard order.
7. **Not verified here** (blocked hosts): kaikki Bengali counts, Tatoeba `ben` size and quality, Hugging Face
   model cards (Indic Parler-TTS speakers and license text, IndicF5 license, MMS license), the IndicCorp per-language
   size, the Leipzig license, Safari's exposure of the Bengali (India) voice, bkit/BanLemma on Kolkata forms.
   Check these before Stage 1 and Stage 3 commit to them.

## Sources

- google/language-resources `bn/` (lexicon, phonemes, transcription guide; CC BY 4.0) · Gutkin et al.,
  "Building statistical parametric multi-speaker synthesis for Bangladeshi Bangla", SLTU 2016
- Johny & Jansche, "Brahmic Schwa-Deletion with Neural Classifiers: Experiments with Bengali", SLTU 2018,
  <https://www.isca-archive.org/sltu_2018/johny18_sltu.html>
- Epitran `ben-Beng` maps and postprocessors, <https://github.com/dmort27/epitran>; espeak-ng
  `dictsource/bn_rules`, `bn_list`
- hermitdave/FrequencyWords (OpenSubtitles 2018; content CC BY-SA 4.0), <https://github.com/hermitdave/FrequencyWords>
- tdulcet/compact-dictionaries (Wiktionary bn 9,258 words), <https://github.com/tdulcet/compact-dictionaries>;
  kaikki.org / wiktextract
- BanLemma, EMNLP Findings 2023, <https://aclanthology.org/2023.findings-emnlp.240>; bkit, BNLP, Indic NLP
  Library, indic-transliteration, Aksharamukha, Stanza, avro.py, bnunicodenormalizer, indic-numtowords,
  shobdo (PyPI metadata, Nov 2026)
- Aksharantar / IndicXlit, <https://arxiv.org/abs/2205.03018>; jsAvroPhonetic (MPL-1.1); OpenBangla Keyboard (GPL-3.0)
- AI4Bharat: Indic Parler-TTS <https://huggingface.co/ai4bharat/indic-parler-tts>, IndicF5
  <https://github.com/AI4Bharat/IndicF5>, Indic-TTS <https://github.com/AI4Bharat/Indic-TTS>, IndicConformer
  <https://github.com/AI4Bharat/IndicConformerASR>, IndicCorp v2, Samanantar
  <https://indicnlp.ai4bharat.org/samanantar>, IndicTrans2 / BPCC / IN22 <https://github.com/AI4Bharat/IndicTrans2>
- facebook/mms-tts-ben (CC BY-NC 4.0); Facebook MUSE dictionaries (CC BY-NC 4.0); Piper VOICES.md
  <https://github.com/rhasspy/piper/blob/master/VOICES.md>; OpenSLR 37 <https://www.openslr.org/37>
- SraVaani 1.0, arXiv 2608.08235; Dolphin ASR, arXiv 2503.20212
- Bhowmik et al., arXiv 2507.23248; Kabir et al. (BLUCK), arXiv 2505.21092
- Apple: VoiceOver languages <https://support.apple.com/en-hk/111748>; iOS feature availability
  <https://www.apple.com/ios/feature-availability/>; multilingual keyboard <https://support.apple.com/en-au/121233>
- BanglaWriting, arXiv 2011.07499; Hanzi Writer <https://hanziwriter.org>; Noto Sans Bengali (SIL OFL 1.1)
- Thompson, *Bengali: A Comprehensive Grammar*; Hayes & Lahiri (1991), "Bengali intonational phonology";
  Wikipedia: Bengali phonology, Bengali alphabet, Bengali vocabulary; r12a Bengali script notes
- DSAL (Samsad Bengali–English, copyrighted) <https://dsal.uchicago.edu/dictionaries/biswas-bangala>
