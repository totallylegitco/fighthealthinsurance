"""Which conditions and treatments people appeal most, made safe to show.

Two things read this module:

* the public rankings page (``public_rankings.py``), which lists the
  conditions and treatments that are appealed most often; and
* the chooser's synthetic scenarios (``chooser_tasks.py``), which seed a
  made-up case from a real (treatment, condition) pair so the drafts argue
  about something a real person has had to fight, and so the PubMed searches
  already run for that pair can be reused instead of spending NCBI calls.

Both are built from ``Denial.procedure`` and ``Denial.diagnosis``, which
people typed or confirmed about their own case, so the whole module is a
privacy filter first and a ranking second:

1. Denials flagged for exclusion and test accounts' denials are left out,
   the same base the de-identified export uses.
2. Each string is normalized (lower-cased, whitespace collapsed, edge
   punctuation dropped) and run through ``looks_like_medical_term``, which
   rejects anything shaped like free text or an identifier: sentences with
   pronouns, digit runs (claim numbers, dates, phone numbers), addresses,
   and the non-answers people type ("unknown", "see attached").
3. k-anonymity: a term must appear on at least
   ``CONDITION_RANKING_MIN_DENIALS`` distinct denials before it goes
   anywhere. Not to the page, not to the chooser, and not to an outside
   vocabulary service: a rare string is never sent off this server.
4. The term must name a real medical concept. Cheapest first: the microsite
   vocabulary in the repo, then RxNorm for drug-shaped treatments, then NCBI
   (a MeSH lookup, and for compound phrases MeSH cannot place, a quoted
   title/abstract search in PubMed). Verdicts persist in ``MedicalTermCheck``
   so a term costs outside lookups once, and each refresh spends at most
   ``CONDITION_RANKING_LOOKUP_BUDGET`` of them.
5. Counts shown in public are rounded down to a multiple of the k threshold.

Refreshing the verdicts is background work (``refresh_if_due``, run by the
chooser refill actor and the ``refresh_condition_rankings`` command); a page
load only reads verdicts already stored and never calls NCBI.
"""

import asyncio
import datetime
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, cast

import aiohttp
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Trim
from django.utils import timezone
from loguru import logger

from fighthealthinsurance.constants import TEST_ACCOUNT_EMAILS
from fighthealthinsurance.models import Denial, MedicalTermCheck, ModelHealthAlertState

# The fewest distinct denials a term needs before it is ranked, seeded into
# the chooser, or sent to an outside vocabulary service (the k in k-anonymity).
CONDITION_RANKING_MIN_DENIALS = getattr(settings, "CONDITION_RANKING_MIN_DENIALS", 5)
# Outside lookups (RxNorm, NCBI) one refresh may spend; the rest wait.
CONDITION_RANKING_LOOKUP_BUDGET = getattr(
    settings, "CONDITION_RANKING_LOOKUP_BUDGET", 30
)
# A stored verdict is asked again after this long.
CONDITION_RANKING_RECHECK_DAYS = getattr(
    settings, "CONDITION_RANKING_RECHECK_DAYS", 365
)
# For a phrase MeSH cannot place: the fewest PubMed title/abstract hits that
# make it a real medical phrase rather than a name or free text.
CONDITION_RANKING_MIN_PUBMED_HITS = getattr(
    settings, "CONDITION_RANKING_MIN_PUBMED_HITS", 20
)
# How often refresh_if_due actually refreshes, fleet-wide.
CONDITION_RANKING_REFRESH_SECONDS = getattr(
    settings, "CONDITION_RANKING_REFRESH_SECONDS", 60 * 60
)
# Rows per list on the public page.
CONDITION_RANKING_LIMIT = getattr(settings, "CONDITION_RANKING_LIMIT", 25)
# Pause between NCBI calls: 3 requests a second without an API key.
_NCBI_PAUSE_SECONDS = 0.4
_LOOKUP_TIMEOUT_SECONDS = 10.0
# Process-local cache of the computed lists; the page is cached longer.
_CACHE_SECONDS = 10 * 60

KIND_CONDITION = "condition"
KIND_TREATMENT = "treatment"
KINDS = (KIND_CONDITION, KIND_TREATMENT)
_FIELD = {KIND_CONDITION: "diagnosis", KIND_TREATMENT: "procedure"}

SOURCE_HEURISTIC = "heuristic"
SOURCE_MICROSITES = "microsites"
SOURCE_RXNORM = "rxnorm"
SOURCE_MESH = "mesh"
SOURCE_PUBMED = "pubmed"

_WS_RE = re.compile(r"\s+")
_EDGE_PUNCT = " \t\r\n.,;:!?\"'()[]{}-_/\\*#<>"
_DIGIT_RUN_RE = re.compile(r"\d{3,}")
_WORD_RE = re.compile(r"[a-z]+")
# Whole words that mark a sentence about oneself rather than a term.
_FREE_TEXT_WORDS = frozenset({"i", "me", "my", "mine", "we", "our", "you", "your"})
# The non-answers people type into a procedure or diagnosis field.
_NON_ANSWERS = frozenset(
    {
        "unknown",
        "unspecified",
        "n/a",
        "na",
        "none",
        "no",
        "yes",
        "not sure",
        "unsure",
        "other",
        "same",
        "test",
        "testing",
        "tbd",
        "pending",
        "various",
        "multiple",
        "not applicable",
        "not listed",
        "not provided",
        "idk",
        "don't know",
        "dont know",
        "see attached",
        "see letter",
        "see above",
        "see below",
        "see denial",
    }
)


def normalize_term(raw: Optional[str]) -> Optional[str]:
    """``raw`` as a comparison key: lower-cased, whitespace collapsed, edge
    punctuation dropped; None when nothing is left."""
    if raw is None:
        return None
    text = _WS_RE.sub(" ", str(raw).replace("\x00", "")).strip()
    text = text.strip(_EDGE_PUNCT).strip().lower()
    return text or None


def looks_like_medical_term(term: str) -> bool:
    """Whether a normalized term is shaped like a condition or treatment
    name, rather than free text, an identifier or a non-answer.

    A pass here is not a verdict: the vocabulary check (and k-anonymity)
    still stand between a term and the page. A fail is final, and costs no
    outside lookup.
    """
    if not 3 <= len(term) <= 80:
        return False
    if term in _NON_ANSWERS or term.startswith(("see ", "not ", "no ")):
        return False
    if "@" in term or "http" in term or "www." in term:
        return False
    if _DIGIT_RUN_RE.search(term):
        return False
    words = term.split(" ")
    if len(words) > 8:
        return False
    if any(w in _FREE_TEXT_WORDS for w in words):
        return False
    letters = _WORD_RE.findall(term)
    if not letters or max(len(w) for w in letters) < 3:
        return False
    # Mostly letters: "k9" style codes and symbol soup are not terms.
    return sum(len(w) for w in letters) * 2 >= len(term)


@dataclass(frozen=True)
class TermCount:
    """One normalized term: its most common spelling as people entered it,
    and how many distinct denials carry it."""

    term: str
    display: str
    denials: int


@dataclass(frozen=True)
class RankedTerm(TermCount):
    """A term that cleared every filter, with the count the public sees:
    rounded down to a multiple of the k threshold."""

    public_count: int


@dataclass(frozen=True)
class SeedPair:
    """A (treatment, condition) pair, in display spelling, that cleared
    every filter: safe to build a synthetic case around."""

    treatment: str
    condition: str
    denials: int


def _excluded_hashed_emails() -> List[str]:
    return [Denial.get_hashed_email(e) for e in TEST_ACCOUNT_EMAILS]


def _ranking_denials() -> "QuerySet[Denial]":
    """The denials the rankings count: not flagged for exclusion, and not a
    test account's."""
    return Denial.objects.exclude(hashed_email__in=_excluded_hashed_emails()).filter(
        Q(flag_for_exclude=False) | Q(flag_for_exclude__isnull=True)
    )


def _spelling_counts(fields: Tuple[str, ...]) -> Iterable[Dict[str, Any]]:
    """Rows of ``{spelled_<field>: str, ..., n: int}``: distinct denials per
    spelling (trimmed, case kept) of the fields together, for spellings on
    at least two denials. The database does the grouping; the one-denial
    spellings it drops are mostly the free text the heuristics would reject,
    and a term spelled a new way on every denial is not one the k threshold
    could keep anyway."""
    qs = _ranking_denials()
    for field in fields:
        qs = qs.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""})
    qs = qs.annotate(**{f"spelled_{f}": Trim(f) for f in fields})
    for field in fields:
        qs = qs.exclude(**{f"spelled_{field}": ""})
    return cast(
        Iterable[Dict[str, Any]],
        qs.order_by()
        .values(*[f"spelled_{f}" for f in fields])
        .annotate(n=Count("denial_id"))
        .filter(n__gte=2)
        .iterator(),
    )


def _best_spelling(spellings: Dict[str, int]) -> str:
    return max(spellings.items(), key=lambda kv: (kv[1], kv[0]))[0]


def count_terms(kind: str, min_denials: Optional[int] = None) -> List[TermCount]:
    """Every normalized ``kind`` term on at least ``min_denials`` distinct
    denials that looks like a medical term, most frequent first. Not yet
    vocabulary-checked: see ranked_terms for the list the public may see."""
    k = CONDITION_RANKING_MIN_DENIALS if min_denials is None else min_denials
    field = _FIELD[kind]
    by_term: Dict[str, Counter] = {}
    for row in _spelling_counts((field,)):
        spelled = str(row[f"spelled_{field}"]).strip()
        term = normalize_term(spelled)
        if term is None:
            continue
        by_term.setdefault(term, Counter())[spelled] += int(row["n"])
    out: List[TermCount] = []
    for term, spellings in by_term.items():
        total = sum(spellings.values())
        if total < k or not looks_like_medical_term(term):
            continue
        out.append(TermCount(term, _best_spelling(spellings), total))
    out.sort(key=lambda t: (-t.denials, t.term))
    return out


def _real_terms(kind: str) -> Dict[str, MedicalTermCheck]:
    """The stored verdicts saying a ``kind`` term is real, by term."""
    return {
        row.term: row
        for row in MedicalTermCheck.objects.filter(kind=kind, is_real=True)
    }


def ranked_terms(kind: str, limit: Optional[int] = None) -> List[RankedTerm]:
    """The ``kind`` terms the public may see: k-anonymous, shaped like a
    term, and vouched for by a vocabulary, most frequent first, with counts
    rounded down to a multiple of the k threshold. Reads stored verdicts
    only; a term no refresh has checked yet is left out, never looked up."""
    k = CONDITION_RANKING_MIN_DENIALS
    real = _real_terms(kind)
    out: List[RankedTerm] = []
    for counted in count_terms(kind, k):
        if counted.term not in real:
            continue
        out.append(
            RankedTerm(
                term=counted.term,
                display=real[counted.term].display or counted.display,
                denials=counted.denials,
                public_count=(counted.denials // k) * k,
            )
        )
    return out[:limit] if limit else out


def _cached(key: str, compute: Any) -> Any:
    """``compute()``, remembered for _CACHE_SECONDS in the process cache.
    A cache that cannot answer is not an error: the value is computed."""
    full_key = f"condition_rankings:{key}"
    try:
        hit = cache.get(full_key)
    except Exception as e:
        logger.debug(f"condition rankings cache read failed: {e}")
        hit = None
    if hit is not None:
        return hit
    value = compute()
    try:
        cache.set(full_key, value, _CACHE_SECONDS)
    except Exception as e:
        logger.debug(f"condition rankings cache write failed: {e}")
    return value


def ranked_terms_cached(kind: str, limit: Optional[int] = None) -> List[RankedTerm]:
    return cast(
        List[RankedTerm],
        _cached(f"ranked:{kind}:{limit}", lambda: ranked_terms(kind, limit)),
    )


def seed_pairs_sync(limit: int = 100) -> List[SeedPair]:
    """(treatment, condition) pairs on at least k distinct denials whose
    both terms the vocabularies vouch for, most frequent first. The chooser
    builds its synthetic cases around these."""
    k = CONDITION_RANKING_MIN_DENIALS
    real_treatments = _real_terms(KIND_TREATMENT)
    real_conditions = _real_terms(KIND_CONDITION)
    if not real_treatments or not real_conditions:
        return []
    by_pair: Dict[Tuple[str, str], Counter] = {}
    for row in _spelling_counts(("procedure", "diagnosis")):
        treatment = normalize_term(row["spelled_procedure"])
        condition = normalize_term(row["spelled_diagnosis"])
        if treatment is None or condition is None:
            continue
        if treatment not in real_treatments or condition not in real_conditions:
            continue
        spelled = (
            str(row["spelled_procedure"]).strip(),
            str(row["spelled_diagnosis"]).strip(),
        )
        by_pair.setdefault((treatment, condition), Counter())[spelled] += int(row["n"])
    out: List[SeedPair] = []
    for (treatment, condition), spellings in by_pair.items():
        total = sum(spellings.values())
        if total < k:
            continue
        best = max(spellings.items(), key=lambda kv: (kv[1], kv[0]))[0]
        out.append(
            SeedPair(
                treatment=real_treatments[treatment].display or best[0],
                condition=real_conditions[condition].display or best[1],
                denials=total,
            )
        )
    out.sort(key=lambda p: (-p.denials, p.treatment, p.condition))
    return out[:limit]


async def seed_pairs(limit: int = 100) -> List[SeedPair]:
    return cast(
        List[SeedPair],
        await database_sync_to_async(
            lambda: _cached(f"seed_pairs:{limit}", lambda: seed_pairs_sync(limit))
        )(),
    )


# --- the vocabulary check -------------------------------------------------


def _microsite_vocabulary() -> Dict[str, Set[str]]:
    """Normalized terms the microsites in the repo name: the conditions and
    the treatments (a procedure's parenthetical and slash alternatives are
    terms of their own: "Zepbound (tirzepatide)" names both)."""
    from fighthealthinsurance.microsites import get_all_microsites

    vocab: Dict[str, Set[str]] = {KIND_CONDITION: set(), KIND_TREATMENT: set()}

    def add(kind: str, raw: Optional[str]) -> None:
        if not raw:
            return
        for piece in re.split(r"[()/,]| or ", raw):
            term = normalize_term(piece)
            if term and looks_like_medical_term(term):
                vocab[kind].add(term)

    for microsite in get_all_microsites().values():
        add(KIND_CONDITION, microsite.default_condition)
        add(KIND_TREATMENT, microsite.default_procedure)
        for alternative in microsite.alternatives:
            # Alternatives are prose ("semaglutide, as formulary coverage
            # varies"): only the leading clause names a drug.
            head = re.split(r"[(,;:]", alternative, maxsplit=1)[0]
            if len(head.split()) <= 4:
                add(KIND_TREATMENT, head)
    return vocab


def offline_verdict(term: str, kind: str) -> Optional[Tuple[bool, str]]:
    """``(is_real, source)`` when no outside lookup is needed: the shape
    rules reject it, or the microsite vocabulary names it. None otherwise."""
    if not looks_like_medical_term(term):
        return (False, SOURCE_HEURISTIC)
    if term in _microsite_vocabulary_cached()[kind]:
        return (True, SOURCE_MICROSITES)
    return None


def _microsite_vocabulary_cached() -> Dict[str, Set[str]]:
    return cast(
        Dict[str, Set[str]], _cached("microsite_vocabulary", _microsite_vocabulary)
    )


async def _rxnorm_matched(term: str) -> Optional[bool]:
    """Whether RxNorm knows ``term`` as a drug; None when it could not say.
    Only asked for a term shaped like a single drug name."""
    from fighthealthinsurance.rxnorm_tools import (
        RxNormTools,
        looks_like_single_drug_query,
    )

    if not looks_like_single_drug_query(term):
        return False
    try:
        return (await RxNormTools().normalize(term)).matched
    except Exception as e:
        logger.debug(f"RxNorm lookup failed for a ranking term: {e}")
        return None


async def _esearch_count(
    db: str, term: str, session: aiohttp.ClientSession
) -> Optional[int]:
    """How many ``db`` records NCBI's esearch finds for ``term``; None when
    the lookup failed."""
    from fighthealthinsurance.pubmed_tools import _EUTILS_BASE, _EUTILS_PARAMS

    params = {
        **_EUTILS_PARAMS,
        "db": db,
        "term": term,
        "retmode": "json",
        "retmax": "0",
    }
    try:
        async with session.get(
            f"{_EUTILS_BASE}/esearch.fcgi",
            params=params,
            timeout=aiohttp.ClientTimeout(total=_LOOKUP_TIMEOUT_SECONDS),
        ) as resp:
            if resp.status != 200:
                logger.debug(f"esearch {db} returned {resp.status}")
                return None
            data = await resp.json(content_type=None)
        return int(data["esearchresult"]["count"])
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug(f"esearch {db} failed for a ranking term: {e}")
        return None


async def _mesh_count(term: str, session: aiohttp.ClientSession) -> Optional[int]:
    return await _esearch_count("mesh", term, session)


async def _pubmed_phrase_count(
    term: str, session: aiohttp.ClientSession
) -> Optional[int]:
    return await _esearch_count("pubmed", f'"{term}"[Title/Abstract]', session)


async def vocabulary_verdict(
    term: str, kind: str, session: aiohttp.ClientSession
) -> Optional[Tuple[bool, str]]:
    """``(is_real, source)`` from the outside vocabularies, or None when none
    of them could answer (the term stays unchecked and is asked again).
    Costs up to two NCBI calls, plus one RxNorm call for a drug-shaped
    treatment; the caller has already spent a budget slot on it."""
    if kind == KIND_TREATMENT:
        matched = await _rxnorm_matched(term)
        if matched:
            return (True, SOURCE_RXNORM)
    mesh = await _mesh_count(term, session)
    if mesh:
        return (True, SOURCE_MESH)
    await asyncio.sleep(_NCBI_PAUSE_SECONDS)
    hits = await _pubmed_phrase_count(term, session)
    if hits is None and mesh is None:
        return None
    if hits is not None and hits >= CONDITION_RANKING_MIN_PUBMED_HITS:
        return (True, SOURCE_PUBMED)
    return (False, SOURCE_PUBMED if hits is not None else SOURCE_MESH)


# --- refreshing the verdicts ---------------------------------------------


def _ensure_rows(kind: str, counted: List[TermCount]) -> int:
    """A MedicalTermCheck row for every counted term; returns how many were
    new. Only k-anonymous terms reach here (count_terms applied k)."""
    existing = set(
        MedicalTermCheck.objects.filter(
            kind=kind, term__in=[t.term for t in counted]
        ).values_list("term", flat=True)
    )
    new = [
        MedicalTermCheck(term=t.term, kind=kind, display=t.display)
        for t in counted
        if t.term not in existing
    ]
    MedicalTermCheck.objects.bulk_create(new, ignore_conflicts=True)
    return len(new)


def _rows_to_check(now: datetime.datetime) -> List[MedicalTermCheck]:
    """Unchecked rows first (oldest first), then verdicts older than the
    recheck window."""
    stale = now - datetime.timedelta(days=CONDITION_RANKING_RECHECK_DAYS)
    unchecked = list(
        MedicalTermCheck.objects.filter(is_real__isnull=True).order_by("created_at")
    )
    rechecks = list(
        MedicalTermCheck.objects.filter(
            is_real__isnull=False, checked_at__lt=stale
        ).order_by("checked_at")
    )
    return unchecked + rechecks


async def refresh_term_checks(budget: Optional[int] = None) -> Dict[str, int]:
    """Bring MedicalTermCheck up to date with the denials: a row for every
    k-anonymous term, offline verdicts for free, then outside lookups for up
    to ``budget`` terms. Returns counts of what it did."""
    if budget is None:
        budget = CONDITION_RANKING_LOOKUP_BUDGET
    stats: Counter = Counter()
    for kind in KINDS:
        counted = await database_sync_to_async(count_terms)(kind)
        stats["new_rows"] += await database_sync_to_async(_ensure_rows)(kind, counted)
    now = timezone.now()
    rows = await database_sync_to_async(_rows_to_check)(now)
    looked_up = 0
    session: Optional[aiohttp.ClientSession] = None
    try:
        for row in rows:
            verdict = offline_verdict(row.term, row.kind)
            if verdict is None:
                if looked_up >= budget:
                    stats["deferred"] += 1
                    continue
                if session is None:
                    from fighthealthinsurance.pubmed_tools import _FETCH_HEADERS

                    session = aiohttp.ClientSession(headers=_FETCH_HEADERS)
                elif looked_up:
                    await asyncio.sleep(_NCBI_PAUSE_SECONDS)
                looked_up += 1
                verdict = await vocabulary_verdict(row.term, row.kind, session)
                if verdict is None:
                    stats["failed"] += 1
                    continue
            row.is_real, row.source = verdict
            row.checked_at = now
            await row.asave(update_fields=["is_real", "source", "checked_at"])
            stats["real" if row.is_real else "rejected"] += 1
    finally:
        if session is not None:
            await session.close()
    stats["looked_up"] = looked_up
    if stats:
        logger.info(f"Condition rankings refreshed: {dict(stats)}")
    return dict(stats)


_REFRESH_CLAIM_KEY = "condition_rankings_refresh"


async def refresh_if_due() -> bool:
    """refresh_term_checks at most once per CONDITION_RANKING_REFRESH_SECONDS
    across every process sharing the database; False when not due."""
    claimed = await database_sync_to_async(ModelHealthAlertState.try_claim)(
        _REFRESH_CLAIM_KEY, CONDITION_RANKING_REFRESH_SECONDS
    )
    if not claimed:
        return False
    await refresh_term_checks()
    return True
