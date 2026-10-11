"""condition_rankings' term shaping: what a denial's procedure or diagnosis
string has to look like before it can even be counted. No database."""

import pytest

from fighthealthinsurance.condition_rankings import (
    KIND_CONDITION,
    KIND_TREATMENT,
    SOURCE_HEURISTIC,
    SOURCE_MICROSITES,
    looks_like_medical_term,
    normalize_term,
    offline_verdict,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Lower Back Pain", "lower back pain"),
        ("  MRI of lumbar\tspine.  ", "mri of lumbar spine"),
        ("(Zepbound)", "zepbound"),
        ("- Physical therapy -", "physical therapy"),
        ("", None),
        ("   ", None),
        (None, None),
        ("...", None),
    ],
)
def test_normalize_term(raw, expected):
    assert normalize_term(raw) == expected


@pytest.mark.parametrize(
    "term",
    [
        "lower back pain",
        "mri of lumbar spine",
        "type 2 diabetes",
        "covid-19",
        "mri",
        "physical therapy",
        "zepbound",
    ],
)
def test_terms_that_look_medical(term):
    assert looks_like_medical_term(term)


@pytest.mark.parametrize(
    "term",
    [
        # Non-answers.
        "unknown",
        "n/a",
        "see attached",
        "not sure",
        # Free text about oneself.
        "my back hurts",
        "i need an mri",
        # Identifiers and dates.
        "claim 123456",
        "01/02/2024",
        "member id a12345678",
        # Contact details.
        "me@example.com",
        "https://example.com/denial",
        # Too short, too long, or symbol soup.
        "ab",
        "a " * 60,
        "k9 !!! ???",
        "the insurance company said that this was not covered under the plan at all",
    ],
)
def test_terms_that_do_not_look_medical(term):
    assert not looks_like_medical_term(term)


def test_offline_verdict_rejects_shape_failures_without_a_lookup():
    assert offline_verdict("see attached", KIND_CONDITION) == (False, SOURCE_HEURISTIC)


def test_offline_verdict_accepts_a_microsite_term():
    # "Sleep Apnea" is a microsite condition; "CPAP Machine or Supplies"
    # splits into the treatments "cpap machine" and "supplies".
    assert offline_verdict("sleep apnea", KIND_CONDITION) == (True, SOURCE_MICROSITES)
    assert offline_verdict("cpap machine", KIND_TREATMENT) == (
        True,
        SOURCE_MICROSITES,
    )


def test_offline_verdict_leaves_an_unknown_term_to_the_vocabularies():
    assert offline_verdict("chronic lower back pain", KIND_CONDITION) is None
