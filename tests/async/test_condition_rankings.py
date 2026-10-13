"""condition_rankings against the database: k-anonymity, the stored
verdicts, the seed pool, and the refresh's lookup budget.

Every outside vocabulary is patched: a test here never reaches RxNorm or
NCBI (see CLAUDE.md on hermetic tests).
"""

from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from fighthealthinsurance import condition_rankings as cr
from fighthealthinsurance.constants import TEST_ACCOUNT_EMAILS
from fighthealthinsurance.models import Denial, MedicalTermCheck


async def _denials(n, procedure, diagnosis, hashed_email=None, flagged=False):
    """``n`` denials, each from a different person unless an email is given."""
    for i in range(n):
        await Denial.objects.acreate(
            hashed_email=hashed_email or f"person-{procedure}-{diagnosis}-{i}",
            denial_text="denied",
            procedure=procedure,
            diagnosis=diagnosis,
            flag_for_exclude=flagged,
        )


async def _verdict(term, kind, is_real=True, display=""):
    return await MedicalTermCheck.objects.acreate(
        term=term, kind=kind, is_real=is_real, display=display, checked_at=timezone.now()
    )


def _no_lookups():
    """Patch every outside vocabulary so a lookup is a test failure."""
    boom = AsyncMock(side_effect=AssertionError("outside lookup made"))
    return (
        patch("fighthealthinsurance.condition_rankings._rxnorm_matched", boom),
        patch("fighthealthinsurance.condition_rankings._mesh_count", boom),
        patch("fighthealthinsurance.condition_rankings._pubmed_phrase_count", boom),
    )


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestCountTerms:
    async def test_a_term_needs_k_distinct_denials(self):
        await _denials(5, "MRI", "Lower back pain")
        await _denials(4, "CT scan", "Abdominal pain")

        counted = await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5)

        assert [(t.term, t.people) for t in counted] == [("lower back pain", 5)]

    async def test_spellings_merge_and_the_most_common_one_is_displayed(self):
        await _denials(3, "MRI", "Lower back pain")
        await _denials(2, "MRI", "lower back pain")
        await _denials(2, "MRI", "  LOWER BACK PAIN ")

        counted = await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5)

        assert counted == [cr.TermCount("lower back pain", "Lower back pain", 7)]

    async def test_one_person_filing_many_times_counts_once(self):
        """k counts people, not rows: one person's six filings of a rare
        condition must not make it public, seed it, or send it to NCBI."""
        await _denials(6, "MRI", "A rare condition", hashed_email="one-person")

        assert await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5) == []
        counted = await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 1)
        assert [(t.term, t.people) for t in counted] == [("a rare condition", 1)]

    async def test_one_person_is_counted_once_across_spellings(self):
        """Two people each spelling a term three ways are two people, not
        six: the count merges spellings before it counts."""
        for spelling in ("Lower back pain", "lower back pain", "LOWER BACK PAIN"):
            await _denials(1, "MRI", spelling, hashed_email="person-a")
            await _denials(1, "MRI", spelling, hashed_email="person-b")

        assert await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5) == []
        counted = await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 2)
        assert [(t.term, t.people) for t in counted] == [("lower back pain", 2)]

    async def test_flagged_and_test_account_denials_are_left_out(self):
        await _denials(5, "MRI", "Lower back pain", flagged=True)
        await _denials(
            5,
            "MRI",
            "Knee pain",
            hashed_email=Denial.get_hashed_email(TEST_ACCOUNT_EMAILS[0]),
        )

        assert await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5) == []

    async def test_free_text_and_non_answers_never_count(self):
        await _denials(6, "MRI", "see attached")
        await _denials(6, "MRI", "my back has hurt since 2019")

        assert await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5) == []


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestRankedTerms:
    async def test_only_vouched_for_terms_are_ranked(self):
        await _denials(12, "MRI", "Lower back pain")
        await _denials(7, "MRI", "Knee pain")
        await _denials(9, "MRI", "Definitely a condition")
        await _verdict("lower back pain", cr.KIND_CONDITION)
        await _verdict("knee pain", cr.KIND_CONDITION, display="Knee pain (patellofemoral)")
        await _verdict("definitely a condition", cr.KIND_CONDITION, is_real=False)

        ranked = await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION)

        assert [(r.display, r.people, r.public_count) for r in ranked] == [
            ("Lower back pain", 12, 10),
            ("Knee pain (patellofemoral)", 7, 5),
        ]

    async def test_an_unchecked_term_is_left_out_and_not_looked_up(self):
        await _denials(6, "MRI", "Lower back pain")
        await MedicalTermCheck.objects.acreate(
            term="lower back pain", kind=cr.KIND_CONDITION
        )

        with _no_lookups()[0], _no_lookups()[1], _no_lookups()[2]:
            assert await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION) == []

    async def test_limit(self):
        for i in range(3):
            await _denials(5 + i, "MRI", f"condition {chr(97 + i)}")
            await _verdict(f"condition {chr(97 + i)}", cr.KIND_CONDITION)

        ranked = await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION, limit=2)

        assert [r.term for r in ranked] == ["condition c", "condition b"]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestSeedPairs:
    async def test_a_pair_counts_people_not_rows(self):
        await _denials(6, "MRI", "Lower back pain", hashed_email="one-person")
        await _verdict("mri", cr.KIND_TREATMENT, display="MRI")
        await _verdict("lower back pain", cr.KIND_CONDITION)

        assert await cr.seed_pairs() == []

    async def test_a_pair_needs_k_people_and_two_vouched_for_terms(self):
        await _denials(6, "MRI", "Lower back pain")
        await _denials(6, "MRI", "Knee pain")
        await _denials(3, "CT scan", "Lower back pain")
        await _verdict("mri", cr.KIND_TREATMENT, display="MRI")
        await _verdict("lower back pain", cr.KIND_CONDITION)
        await _verdict("knee pain", cr.KIND_CONDITION, is_real=False)

        pairs = await cr.seed_pairs()

        assert pairs == [cr.SeedPair("MRI", "Lower back pain", 6)]

    async def test_no_verdicts_means_no_pairs(self):
        await _denials(6, "MRI", "Lower back pain")

        assert await cr.seed_pairs() == []


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestRefresh:
    async def test_rows_are_created_for_k_anonymous_terms_only(self):
        await _denials(5, "MRI", "Lower back pain")
        await _denials(4, "CT scan", "Abdominal pain")

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=0),
        ), patch(
            "fighthealthinsurance.condition_rankings._pubmed_phrase_count",
            AsyncMock(return_value=0),
        ), patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=False),
        ):
            await cr.refresh_term_checks()

        terms = {
            (r.kind, r.term)
            async for r in MedicalTermCheck.objects.all()
        }
        assert terms == {
            (cr.KIND_CONDITION, "lower back pain"),
            (cr.KIND_TREATMENT, "mri"),
        }

    async def test_microsite_terms_cost_no_lookup(self):
        # "Sleep Apnea" is a microsite condition.
        await _denials(5, "CPAP", "Sleep apnea")
        await _denials(5, "CPAP", "Snoring")

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=1),
        ) as mesh, patch(
            "fighthealthinsurance.condition_rankings._pubmed_phrase_count",
            AsyncMock(return_value=0),
        ), patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=False),
        ):
            stats = await cr.refresh_term_checks()

        apnea = await MedicalTermCheck.objects.aget(term="sleep apnea")
        assert (apnea.is_real, apnea.source) == (True, cr.SOURCE_MICROSITES)
        # snoring and cpap went to MeSH; sleep apnea did not.
        assert sorted(c.args[0] for c in mesh.await_args_list) == ["cpap", "snoring"]
        assert stats["real"] == 3

    async def test_the_lookup_budget_holds_and_the_rest_wait(self):
        # "see attached" fails the shape rules, so only the four conditions
        # reach the vocabularies.
        for i in range(4):
            await _denials(5, "see attached", f"condition {chr(97 + i)}")

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=1),
        ) as mesh, patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=True),
        ), patch("fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()):
            stats = await cr.refresh_term_checks(budget=2)

        assert stats["looked_up"] == 2
        assert stats["deferred"] == 2
        assert mesh.await_count == 2
        unchecked = await MedicalTermCheck.objects.filter(is_real__isnull=True).acount()
        assert unchecked == 2

    async def test_a_compound_phrase_falls_back_to_a_quoted_pubmed_search(self):
        await _denials(5, "MRI of lumbar spine", "Lower back pain")

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=0),
        ), patch(
            "fighthealthinsurance.condition_rankings._pubmed_phrase_count",
            AsyncMock(return_value=cr.CONDITION_RANKING_MIN_PUBMED_HITS),
        ) as pubmed, patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=False),
        ), patch("fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()):
            await cr.refresh_term_checks()

        row = await MedicalTermCheck.objects.aget(term="mri of lumbar spine")
        assert (row.is_real, row.source) == (True, cr.SOURCE_PUBMED)
        assert "mri of lumbar spine" in {c.args[0] for c in pubmed.await_args_list}

    async def test_a_lookup_that_cannot_answer_leaves_the_term_unchecked(self):
        await _denials(5, "MRI", "Lower back pain")

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=None),
        ), patch(
            "fighthealthinsurance.condition_rankings._pubmed_phrase_count",
            AsyncMock(return_value=None),
        ), patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=None),
        ), patch("fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()):
            stats = await cr.refresh_term_checks()

        assert stats["failed"] == 2
        assert await MedicalTermCheck.objects.filter(is_real__isnull=True).acount() == 2

    async def test_refresh_if_due_runs_once_per_window(self):
        with patch(
            "fighthealthinsurance.condition_rankings.refresh_term_checks",
            AsyncMock(return_value={}),
        ) as refresh:
            assert await cr.refresh_if_due() is True
            assert await cr.refresh_if_due() is False

        assert refresh.await_count == 1
