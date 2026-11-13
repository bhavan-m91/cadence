"""Quotes must be checkable: the model's `source_quote` is located in the entry text and given character offsets."""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass(frozen=True)
class QuoteResult:
    verified: bool
    start: int | None = None
    end: int | None = None
    text: str = ""


def _loose_pattern(quote: str) -> re.Pattern[str] | None:
    words = re.findall(r"\w+", quote, flags=re.UNICODE)
    if len(words) < 2:
        return None
    return re.compile(r"\W+".join(re.escape(w) for w in words), re.IGNORECASE | re.UNICODE)


def verify_quote(text: str, quote: str) -> QuoteResult:
    quote = (quote or "").strip()
    if not quote or not text:
        return QuoteResult(False)
    i = text.find(quote)
    if i >= 0:
        return QuoteResult(True, i, i + len(quote), text[i:i + len(quote)])
    pat = _loose_pattern(quote)  # same words, different punctuation/case/spacing
    if pat and (m := pat.search(text)):
        return QuoteResult(True, m.start(), m.end(), m.group(0))
    if len(quote) >= 12:  # the model trimmed or lightly reworded: accept a close alignment
        al = fuzz.partial_ratio_alignment(quote.lower(), text.lower())
        if al and al.score >= 90:
            return QuoteResult(True, al.dest_start, al.dest_end, text[al.dest_start:al.dest_end])
    return QuoteResult(False)


_WORD_NUMBERS = {w: i for i, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"])}


def time_supported(hour: int, evidence: str) -> bool:
    """A spoken clock time is only usable if its hour actually appears in the quoted words (guards invented times)."""
    ev = evidence.lower()
    if hour == 12 and ("noon" in ev or "midnight" in ev):
        return True
    wanted = {hour, hour % 12 or 12}
    nums = {int(n) for n in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", ev)}
    words = {_WORD_NUMBERS[w] for w in re.findall(r"[a-z]+", ev) if w in _WORD_NUMBERS}
    return bool(wanted & (nums | words))
