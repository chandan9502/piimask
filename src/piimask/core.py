"""Find, mask and restore UK personal data in text.

Each kind of data has a pattern and, where one exists, a checksum or rule
check. A number that looks right but fails its check (for example an NHS number
with a wrong check digit) is left alone, which keeps false alarms down.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _compact(text: str) -> str:
    return re.sub(r"[\s-]", "", text).upper()


# --- checks -------------------------------------------------------------------


def luhn_valid(number: str) -> bool:
    """Payment card check digit (Luhn), for 13-19 digit numbers."""
    digits = _digits(number)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:  # double every second digit from the right
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def nhs_number_valid(number: str) -> bool:
    """NHS number modulus-11 check digit."""
    digits = _digits(number)
    if len(digits) != 10:
        return False
    total = sum(int(d) * weight for d, weight in zip(digits[:9], range(10, 1, -1), strict=True))
    check = 11 - total % 11
    if check == 11:
        check = 0
    return check != 10 and check == int(digits[9])


def iban_valid(iban: str) -> bool:
    """IBAN modulus-97 check (ISO 13616)."""
    value = _compact(iban)
    if not 15 <= len(value) <= 34 or not value.isalnum():
        return False
    rearranged = value[4:] + value[:4]
    return int("".join(str(int(char, 36)) for char in rearranged)) % 97 == 1


def ni_number_valid(number: str) -> bool:
    """UK National Insurance number prefix rules (HMRC)."""
    value = _compact(number)
    if value[:2] in {"BG", "GB", "NK", "KN", "TN", "NT", "ZZ"}:
        return False
    return value[0] not in "DFIQUV" and value[1] not in "DFIOQUV"


def uk_phone_valid(number: str) -> bool:
    """UK numbers: 11 digits starting 01, 02, 03, 07 or 08 (or +44 with the 0 dropped)."""
    digits = _digits(number)
    if number.lstrip().startswith("+44"):
        digits = digits[2:]
        national = digits if digits.startswith("0") else "0" + digits  # "+44 (0)20 ..."
    else:
        national = digits
    return len(national) == 11 and national[1] in "12378"


@dataclass(frozen=True)
class Detector:
    kind: str
    pattern: re.Pattern[str]
    check: Callable[[str], bool] | None
    canonical: Callable[[str], str]


# Order matters: earlier kinds win when two matches overlap.
DETECTORS: tuple[Detector, ...] = (
    Detector(
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"),
        None,
        str.lower,
    ),
    Detector("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"), iban_valid, _compact),
    Detector("CARD", re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), luhn_valid, _digits),
    Detector("NHS_NUMBER", re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{4}\b"), nhs_number_valid, _digits),
    Detector(
        "NI_NUMBER",
        re.compile(r"\b[A-Z]{2} ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b", re.IGNORECASE),
        ni_number_valid,
        _compact,
    ),
    Detector("UK_PHONE", re.compile(r"(?<![\w+])(?:\+44|0)[\d ()-]{8,16}\d\b"), uk_phone_valid, _digits),
    Detector(
        "UK_POSTCODE",
        re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?|GIR) ?\d[A-Z]{2}\b", re.IGNORECASE),
        None,
        _compact,
    ),
)
KINDS = tuple(d.kind for d in DETECTORS)
_PLACEHOLDER = re.compile(r"<(?:" + "|".join(KINDS) + r")_\d+>")


@dataclass(frozen=True)
class Match:
    """One piece of personal data found in the text."""

    kind: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class MaskResult:
    """Masked text plus the mapping needed to restore it. Keep the mapping secret."""

    text: str
    mapping: dict[str, str] = field(default_factory=dict)
    matches: list[Match] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for match in self.matches:
            counts[match.kind] = counts.get(match.kind, 0) + 1
        return counts


def _selected(kinds: Iterable[str] | None) -> tuple[Detector, ...]:
    if kinds is None:
        return DETECTORS
    wanted = {k.upper() for k in kinds}
    unknown = wanted - set(KINDS)
    if unknown:
        raise ValueError(f"unknown kinds {sorted(unknown)}; choose from {list(KINDS)}")
    return tuple(d for d in DETECTORS if d.kind in wanted)


def find_pii(text: str, kinds: Iterable[str] | None = None) -> list[Match]:
    """Return non-overlapping matches, sorted by position."""
    taken: list[Match] = []
    for detector in _selected(kinds):
        for m in detector.pattern.finditer(text):
            if detector.check is not None and not detector.check(m.group()):
                continue
            if any(m.start() < t.end and t.start < m.end() for t in taken):
                continue  # an earlier, more specific kind already covers this text
            taken.append(Match(detector.kind, m.start(), m.end(), m.group()))
    return sorted(taken, key=lambda match: match.start)


def mask(text: str, kinds: Iterable[str] | None = None) -> MaskResult:
    """Replace personal data with placeholders such as ``<EMAIL_1>``.

    The same value always gets the same placeholder (``07700 900123`` and
    ``07700900123`` are one phone number), so an LLM can still tell people apart.
    """
    detectors = {d.kind: d for d in DETECTORS}
    matches = find_pii(text, kinds)
    placeholders: dict[tuple[str, str], str] = {}
    mapping: dict[str, str] = {}
    pieces: list[str] = []
    cursor = 0
    for match in matches:
        key = (match.kind, detectors[match.kind].canonical(match.text))
        if key not in placeholders:
            number = sum(1 for kind, _ in placeholders if kind == match.kind) + 1
            placeholders[key] = f"<{match.kind}_{number}>"
            mapping[placeholders[key]] = match.text
        pieces += [text[cursor:match.start], placeholders[key]]
        cursor = match.end
    pieces.append(text[cursor:])
    return MaskResult("".join(pieces), mapping, matches)


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put the original values back. Unknown placeholders are left as they are."""
    return _PLACEHOLDER.sub(lambda m: mapping.get(m.group(), m.group()), text)
