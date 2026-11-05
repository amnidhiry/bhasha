"""Sound bootcamp content for a native English speaker (weeks 1-2).

Explicit tone-contour teaching first, then the initials and finals English
speakers confuse, then drills (see docs/design.md: tones need explicit
teaching first; minimal-pair drills before vocabulary ramps up).
"""

# Chao tone numbers (1 = lowest, 5 = highest) and the cue an English speaker can use.
TONES = [
    {"tone": 1, "name": "First tone", "chao": [5, 5], "mark": "ā",
     "how": "High and level, held like singing one note. Start higher than feels natural.",
     "english": "Like the held note of a doctor's 'ahhh', not the falling 'ah' of English speech.",
     "pitfall": "English speakers let it drift down at the end. Keep it flat to the last moment."},
    {"tone": 2, "name": "Second tone", "chao": [3, 5], "mark": "á",
     "how": "Rises from the middle to high.",
     "english": "Like a surprised question: 'What?' or 'Really?'",
     "pitfall": "Rise all the way. A half rise sounds like first tone."},
    {"tone": 3, "name": "Third tone", "chao": [2, 1, 4], "mark": "ǎ",
     "how": "Low. In isolation it dips and comes back up; in speech it mostly stays low (a 'half third').",
     "english": "Like a doubtful, low 'uh-huh...' or the bottom of a sigh.",
     "pitfall": "The low part is what matters. Don't overdo the rise inside sentences."},
    {"tone": 4, "name": "Fourth tone", "chao": [5, 1], "mark": "à",
     "how": "Falls sharply from high to low.",
     "english": "Like a firm 'No!' or 'Stop!'",
     "pitfall": "English sentence-final falls sound like it. Don't let every last word turn into fourth tone."},
    {"tone": 5, "name": "Neutral tone", "chao": [3, 3], "mark": "a",
     "how": "Short and light; its pitch follows the syllable before it.",
     "english": "Like the unstressed 'a' in 'sofa'.",
     "pitfall": "Make it short. Its length matters more than its pitch."},
]

# Initials, grouped as they're taught, with the English-speaker trap for each group.
INITIAL_GROUPS = [
    {"id": "labials", "initials": ["b", "p", "m", "f"], "examples": ["ba", "pa", "ma", "fa"],
     "tip": "b and p are both voiceless; the difference is a puff of air (aspiration). p has a strong puff, b has none, like the p in 'spin', not 'pin'."},
    {"id": "alveolars", "initials": ["d", "t", "n", "l"], "examples": ["da", "ta", "na", "la"],
     "tip": "Same pattern: d is unaspirated (like the t in 'stop'), t has a strong puff."},
    {"id": "velars", "initials": ["g", "k", "h"], "examples": ["ge", "ke", "he"],
     "tip": "g is unaspirated (like the k in 'skill'), k is aspirated. h is rougher than English h, close to the ch in Scottish 'loch'."},
    {"id": "palatals", "initials": ["j", "q", "x"], "examples": ["ji", "qi", "xi"],
     "tip": "Tongue tip down behind the lower teeth, lips spread as if smiling. q is NOT the English q: it's an aspirated 'ch' with a smile. x is between 's' and 'sh'."},
    {"id": "retroflexes", "initials": ["zh", "ch", "sh", "r"], "examples": ["zhi", "chi", "shi", "ri"],
     "tip": "Curl the tongue tip up toward the roof of the mouth. zh is unaspirated (like 'j' in 'jar' but harder), ch aspirated. r is between English 'r' and the 's' in 'measure'."},
    {"id": "dentals", "initials": ["z", "c", "s"], "examples": ["zi", "ci", "si"],
     "tip": "Tongue tip behind the upper teeth. z sounds like the 'ds' in 'kids', c like the 'ts' in 'cats' with a puff. Never like English c."},
]

FINAL_NOTES = [
    {"id": "u-umlaut", "title": "ü (written u after j, q, x, y)",
     "body": "Say 'ee' and round your lips without moving your tongue. After j, q, x and y it's written u (ju, qu, xu, yu) but is always ü."},
    {"id": "buzz-i", "title": "-i after z c s zh ch sh r",
     "body": "In zi ci si and zhi chi shi ri the i is not 'ee'. It's a buzzing continuation of the consonant. Hold the consonant position and voice it."},
    {"id": "e", "title": "e",
     "body": "Alone, e is an unrounded 'uh' from the back of the throat (like 'uh' with a smile). In ie and üe it's like the 'e' in 'yes'."},
    {"id": "nasals", "title": "-n vs -ng",
     "body": "-n ends with the tongue tip on the ridge behind the teeth (like 'sin'); -ng ends at the back with the mouth open (like 'sing'). an/ang and in/ing change meaning."},
    {"id": "spelling", "title": "Pinyin spelling is its own system",
     "body": "Read pinyin by its own rules, not English letters: q, x, c, zh and the vowels above all differ. Every syllable here has audio. Trust your ears over the letters."},
]

# Minimal-pair contrasts English speakers struggle with. Each pair is two syllables
# (no tone); the drill picks a tone where both have a common character.
CONTRASTS = [
    {"id": "zh-j", "label": "zh vs j", "pairs": [("zhi", "ji"), ("zhu", "ju"), ("zhang", "jiang"), ("zhou", "jiu"), ("zhen", "jin"), ("zhong", "jiong")]},
    {"id": "ch-q", "label": "ch vs q", "pairs": [("chi", "qi"), ("chu", "qu"), ("chang", "qiang"), ("chou", "qiu"), ("chen", "qin"), ("chuan", "quan")]},
    {"id": "sh-x", "label": "sh vs x", "pairs": [("shi", "xi"), ("shu", "xu"), ("shang", "xiang"), ("shou", "xiu"), ("shen", "xin"), ("shuo", "xue")]},
    {"id": "z-zh", "label": "z vs zh", "pairs": [("zi", "zhi"), ("zu", "zhu"), ("zao", "zhao"), ("zai", "zhai"), ("zou", "zhou"), ("zeng", "zheng")]},
    {"id": "c-ch", "label": "c vs ch", "pairs": [("ci", "chi"), ("cu", "chu"), ("cao", "chao"), ("cai", "chai"), ("cong", "chong"), ("can", "chan")]},
    {"id": "s-sh", "label": "s vs sh", "pairs": [("si", "shi"), ("su", "shu"), ("sao", "shao"), ("san", "shan"), ("sang", "shang"), ("suo", "shuo")]},
    {"id": "b-p", "label": "b vs p (aspiration)", "pairs": [("ba", "pa"), ("bao", "pao"), ("bi", "pi"), ("bu", "pu"), ("ban", "pan"), ("bing", "ping")]},
    {"id": "d-t", "label": "d vs t (aspiration)", "pairs": [("da", "ta"), ("dao", "tao"), ("di", "ti"), ("du", "tu"), ("dong", "tong"), ("dian", "tian")]},
    {"id": "g-k", "label": "g vs k (aspiration)", "pairs": [("ge", "ke"), ("gao", "kao"), ("gu", "ku"), ("gai", "kai"), ("gong", "kong"), ("guan", "kuan")]},
    {"id": "u-v", "label": "u vs ü", "pairs": [("lu", "lv"), ("nu", "nv"), ("wu", "yu"), ("wan", "yuan"), ("wen", "yun"), ("wei", "yue")]},
    {"id": "an-ang", "label": "-an vs -ang", "pairs": [("fan", "fang"), ("ban", "bang"), ("man", "mang"), ("tan", "tang"), ("shan", "shang"), ("zhan", "zhang")]},
    {"id": "en-eng", "label": "-en vs -eng", "pairs": [("men", "meng"), ("fen", "feng"), ("gen", "geng"), ("ren", "reng"), ("shen", "sheng"), ("chen", "cheng")]},
    {"id": "in-ing", "label": "-in vs -ing", "pairs": [("xin", "xing"), ("jin", "jing"), ("min", "ming"), ("lin", "ling"), ("bin", "bing"), ("pin", "ping")]},
    {"id": "r-l", "label": "r vs l", "pairs": [("re", "le"), ("ru", "lu"), ("ran", "lan"), ("rang", "lang"), ("rou", "lou"), ("ruan", "luan")]},
]

LESSONS = [
    {"id": "tones", "title": "The four tones", "kind": "tones"},
    {"id": "initials", "title": "Initials: sounds that aren't English", "kind": "initials"},
    {"id": "finals", "title": "Finals and spelling", "kind": "finals"},
]

DRILLS = [
    {"id": "tone", "title": "Which tone?", "about": "Hear one syllable, pick its tone."},
    {"id": "pair", "title": "Tone pairs", "about": "Hear a two-syllable HSK word, pick both tones. Pairs are harder than single syllables."},
    {"id": "sandhi", "title": "Tone changes", "about": "See a word, pick how it's actually said (third-tone pairs, 不 and 一)."},
] + [{"id": f"contrast:{c['id']}", "title": c["label"], "about": "Hear one of a pair, pick which.", "group": "contrast"}
     for c in CONTRASTS]

MASTERY_WINDOW = 20      # attempts considered
MASTERY_ACCURACY = 0.85  # recent accuracy that counts as mastered
