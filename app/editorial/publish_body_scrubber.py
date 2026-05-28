"""Publish-time plain-text scrubber — remove pipeline/debug artifacts before formatting."""

from __future__ import annotations

import json
import re

# Section headers / labels that must never appear on the public channel.
_JSON_HEADER = re.compile(r"^(Источники|Sources)\s*\(JSON\)\s*$", re.I)
_INTERNAL_LINE = re.compile(
    r"^(Quality|Duplicates|Priority|Draft\s*#|ID\s+черновика|"
    r"Category\s+confidence|Governance|Качество|Дубликаты|Приоритет|"
    r"Редакционная\s+оценка)\b",
    re.I,
)
_JSON_ARRAY = re.compile(r"\[\s*\{[^\]]*\"channel\"[^\]]*\]", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{\s*\"channel\"\s*:\s*\"[^\"]+\"\s*,\s*\"message_id\"\s*:\s*\d+", re.I)
_PRE_BLOCK = re.compile(r"<pre[^>]*>.*?</pre>", re.I | re.DOTALL)
_HTML_TAGS = re.compile(r"<[^>]+>")
_PIPELINE = re.compile(
    r"\b(wrapper_exit|trace_id|PIPELINE_FATAL|pipeline_decision|execution_registry|"
    r"collect_cycle_timeout|summarize_exit)\b",
    re.I,
)
_METRIC_LINE = re.compile(r"^\s*[\w.]+\s*:\s*(0\.\d+|\d+%|true|false)\s*$", re.I)
_MESSAGE_ID_DUMP = re.compile(r"\bmessage_id\s*[:=]\s*\d+", re.I)
_EMPTY_PLACEHOLDER = re.compile(r"\(\s*empty\s*\)|\.\.\.\s*empty\s*\)", re.I)
_FAST_LANE = re.compile(r"Fast\s+lane\s*·", re.I)
_CTA_SPAM = re.compile(
    r"^Подписывайтесь\s+на\s+канал\s*[—-].*$",
    re.I | re.M,
)
_WS = re.compile(r"[ \t]{2,}")


def scrub_publish_plaintext(text: str) -> str:
    """Remove technical artifacts; normalize spacing. Safe on empty input."""
    t = _PRE_BLOCK.sub("", text or "")
    t = _HTML_TAGS.sub("", t)
    t = _JSON_ARRAY.sub("", t)
    t = _JSON_OBJECT.sub("", t)
    t = _PIPELINE.sub("", t)
    t = _MESSAGE_ID_DUMP.sub("", t)
    t = _EMPTY_PLACEHOLDER.sub("", t)
    t = _FAST_LANE.sub("", t)
    t = _CTA_SPAM.sub("", t)
    t = re.sub(r"^Источники\s*\(JSON\)\s*$", "", t, flags=re.I | re.M)
    t = re.sub(r"^Sources\s*\(JSON\)\s*$", "", t, flags=re.I | re.M)

    lines: list[str] = []
    skip_block = False
    for line in t.splitlines():
        s = line.strip()
        if not s:
            if not skip_block:
                lines.append("")
            continue
        if _JSON_HEADER.match(s):
            skip_block = True
            continue
        if _INTERNAL_LINE.match(s):
            skip_block = True
            continue
        if skip_block and (s.startswith("•") or _METRIC_LINE.match(s) or s.startswith("{")):
            continue
        if _METRIC_LINE.match(s):
            continue
        if s.startswith("[") and "channel" in s.lower():
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
        skip_block = False
        lines.append(line.rstrip())

    joined = "\n".join(lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
    joined = _strip_empty_tail_paragraphs(joined)
    joined = _WS.sub(" ", joined)
    joined = re.sub(r" *\n *", "\n", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
    return joined


def _strip_empty_tail_paragraphs(text: str) -> str:
    paras = [p.strip() for p in (text or "").split("\n\n")]
    while paras and not paras[-1]:
        paras.pop()
    while paras and len(paras[-1]) < 3 and not re.search(r"\w{3,}", paras[-1]):
        paras.pop()
    return "\n\n".join(paras).strip()
