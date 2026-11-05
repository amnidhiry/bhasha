"""SRT and WebVTT subtitles to reading text.

Cue numbers, timestamps, VTT headers/NOTE/STYLE blocks and markup (<i>, <font>,
<c.x>, <v Name>, ASS {\\an8} overrides) go. Bilingual files keep their Chinese
lines (the target script's share of a line, see textutil.script_ratio). Cues are merged into
readable lines: rolling duplicates are dropped, and a cue that ends mid-clause
(a comma, an ellipsis) is joined to the next. Long files are split into parts
of about 1,500 characters."""

import re

from app.importing import ImportProblem
from app.importing.draft import Draft, number_parts
from app.importing.textutil import decode, language_adjective, script_count, script_ratio, split_parts

MAX_UPLOAD = 5 * 1024 * 1024
PART_CHARS = 1500

_TIMING = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}\s*-->")
_TAG = re.compile(r"<[^>]*>")
_ASS = re.compile(r"\{\\[^}]*\}")
_CONTINUES = ("，", ",", "、", "…", "...", "：", ":", "——", "-", "～")
_TARGET_LINE = 0.5  # share of a line in the target script to keep it


def _cues(text: str) -> list[list[str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        head = lines[0]
        if head.startswith("WEBVTT") or head.startswith(("NOTE", "STYLE", "REGION")):
            # The WEBVTT header block may carry the first cue only if a timing line follows.
            idx = next((i for i, ln in enumerate(lines) if _TIMING.search(ln)), None)
            if idx is None:
                continue
            lines = lines[idx:]
        timing = next((i for i, ln in enumerate(lines) if _TIMING.search(ln)), None)
        if timing is None:
            continue  # stray text that isn't a cue
        body = []
        for ln in lines[timing + 1:]:
            ln = _ASS.sub("", _TAG.sub("", ln))
            ln = ln.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            ln = ln.strip().lstrip("-–").strip()
            if ln:
                body.append(ln)
        if body:
            cues.append(body)
    return cues


def _clean_line(line: str) -> str:
    # Chinese subtitles mark pauses with spaces; make them commas so the reader
    # gets phrase boundaries (and sandhi stops at them).
    line = re.sub(r"(?<=[㐀-鿿，。！？])\s+(?=[㐀-鿿])", "，", line)
    line = re.sub(r"(?<=[㐀-鿿])\s+(?=[㐀-鿿])", "，", line)
    return re.sub(r"\s+", " ", line).strip()


_PUNCT_END = tuple("，。！？；：、…,.!?;:—～」』”）)")


def _join(lines: list[str]) -> str:
    """The lines of one cue (a wrapped line, or two speakers) as one line."""
    out = ""
    for ln in lines:
        out = ln if not out else out + (ln if out.endswith(_PUNCT_END) else "，" + ln)
    return out


def subtitle_lines(data: bytes) -> tuple[list[str], bool]:
    """Readable lines and whether the file looked bilingual."""
    cues = _cues(decode(data))
    if not cues:
        raise ImportProblem("Couldn't find any subtitle cues in that file.")
    all_lines = [ln for cue in cues for ln in cue]
    target = [ln for ln in all_lines if script_ratio(ln) >= _TARGET_LINE]
    if not target:
        raise ImportProblem(f"That subtitle file has no {language_adjective()} lines.")
    bilingual = len(target) < len(all_lines) * 0.9 and len(all_lines) - len(target) >= 2

    out: list[str] = []
    prev_cue = ""
    for cue in cues:
        text = _join([_clean_line(ln) for ln in cue if script_ratio(ln) >= _TARGET_LINE])
        if not text or text == prev_cue:
            continue  # English-only cue, or a rolling repeat
        prev_cue = text
        if out and out[-1].endswith(_CONTINUES) and len(out[-1]) < 60:
            out[-1] = out[-1] + text
        else:
            out.append(text)
    return out, bilingual


def draft_from_subtitles(data: bytes, title: str, kind: str = "subtitles", source_url: str | None = None,
                         meta: dict | None = None) -> Draft:
    if len(data) > MAX_UPLOAD:
        raise ImportProblem("That subtitle file is over 5 MB.")
    lines, bilingual = subtitle_lines(data)
    bodies = split_parts(lines, PART_CHARS)
    title = (title.strip() or "Subtitles")[:240]
    adj = language_adjective()
    warnings = [f"Bilingual file: kept the {adj} lines."] if bilingual else []
    if script_count("\n".join(lines)) < 20:
        warnings.append(f"Very little {adj} in this file.")
    return Draft(kind=kind, title=title, parts=number_parts(title, bodies), source_url=source_url,
                 meta={**(meta or {}), "bilingual": bilingual, "lines": len(lines)}, warnings=warnings)
