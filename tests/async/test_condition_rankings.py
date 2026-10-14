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


async def _count():
    """A refresh that spends no outside lookups: it records every
    k-anonymous term's people count, which is what the page reads."""
    with patch("fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()):
        return await cr.refresh_term_checks(budget=0)


def _no_lookups():
    """Patch every outside vocabulary so a lookup is a test failure."""
    boom = AsyncMock(side_effect=AssertionError("outside lookup made"))
    return (
        patch("fighthealthinsurance.condition_rankings._rxnorm_matched", boom),
        patch("fighthealthinsurance.condition_rankings._mesh_count", boom),
        patch("fighthealthinsurance.condition_rankings._pubmed_phrase_count", boom),
    )


def _no_pubmed():
    """The quoted PubMed search must not run: MeSH answered, or the budget
    is spent. Without this the test is hermetic only by accident."""
    return patch(
        "fighthealthinsurance.condition_rankings._pubmed_phrase_count",
        AsyncMock(side_effect=AssertionError("PubMed phrase lookup made")),
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

    async def test_professional_account_denials_are_left_out(self):
        """A clinic's cases are its patients', filed under the professional
        terms: the same base as the de-identified export leaves them out."""
        from django.contrib.auth import get_user_model

        from fhi_users.models import ProfessionalUser

        user = await get_user_model().objects.acreate_user(
            username="clinician", password="testpass123"
        )
        pro = await ProfessionalUser.objects.acreate(user=user, active=True)
        for i in range(6):
            await Denial.objects.acreate(
                hashed_email=f"clinic-patient-{i}",
                denial_text="denied",
                procedure="MRI",
                diagnosis="Lower back pain",
                creating_professional=pro,
            )

        assert await sync_to_async(cr.count_terms)(cr.KIND_CONDITION, 5) == []

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
        await _count()

        ranked = await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION)

        # The display is the spelling most people used; the vocabulary row's
        # own display is refreshed from the denials.
        assert [(r.display, r.people, r.public_count) for r in ranked] == [
            ("Lower back pain", 12, 10),
            ("Knee pain", 7, 5),
        ]

    async def test_an_unchecked_term_is_left_out_and_not_looked_up(self):
        await _denials(6, "MRI", "Lower back pain")
        await MedicalTermCheck.objects.acreate(
            term="lower back pain", kind=cr.KIND_CONDITION
        )
        await _count()

        with _no_lookups()[0], _no_lookups()[1], _no_lookups()[2]:
            assert await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION) == []

    async def test_order_ties_by_name_within_a_rounded_bucket(self):
        """Six people and five people both show as "5+"; listing the six
        first would say which is larger, so the order is by name there."""
        await _denials(6, "MRI", "Zoster")
        await _denials(5, "MRI", "Asthma")
        await _denials(11, "MRI", "Migraine")
        for term in ("zoster", "asthma", "migraine"):
            await _verdict(term, cr.KIND_CONDITION)
        await _count()

        ranked = await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION)

        assert [(r.term, r.public_count) for r in ranked] == [
            ("migraine", 10),
            ("asthma", 5),
            ("zoster", 5),
        ]

    async def test_limit_cuts_by_rounded_count_then_name(self):
        # a: 5 people, b: 6, c: 11 -> shown as 5+, 5+, 10+. The cut keeps c,
        # then a before b: within a bucket the order is by name, so the cut
        # does not say whether a or b has more people.
        for letter, people in (("a", 5), ("b", 6), ("c", 11)):
            await _denials(people, "MRI", f"condition {letter}")
            await _verdict(f"condition {letter}", cr.KIND_CONDITION)
        await _count()

        ranked = await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION, limit=2)

        assert [r.term for r in ranked] == ["condition c", "condition a"]

    async def test_the_page_never_scans_the_denials(self):
        """ranked_terms is a read of MedicalTermCheck: an anonymous page load
        must not run the aggregation over the denials."""
        await _denials(6, "MRI", "Lower back pain")
        await _verdict("lower back pain", cr.KIND_CONDITION)
        await _count()

        with patch(
            "fighthealthinsurance.condition_rankings._person_spellings",
            side_effect=AssertionError("the page scanned the denials"),
        ):
            ranked = await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION)

        assert [r.term for r in ranked] == ["lower back pain"]

    async def test_a_term_that_fell_below_k_leaves_the_page(self):
        await _denials(6, "MRI", "Lower back pain")
        await _verdict("lower back pain", cr.KIND_CONDITION)
        await _count()
        assert await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION) != []
        async for denial in Denial.objects.all()[:2]:
            await denial.adelete()
        await _count()

        assert await sync_to_async(cr.ranked_terms)(cr.KIND_CONDITION) == []
        row = await MedicalTermCheck.objects.aget(term="lower back pain")
        assert row.people == 0


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
        ), _no_pubmed(), patch(
            "fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()
        ):
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

    async def test_a_display_spelling_is_cut_to_the_column(self):
        await _denials(5, "MRI", "Lower back pain" + "." * 170)

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=1),
        ), patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=False),
        ), _no_pubmed(), patch(
            "fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()
        ):
            await cr.refresh_term_checks()

        row = await MedicalTermCheck.objects.aget(term="lower back pain")
        width = MedicalTermCheck._meta.get_field("display").max_length
        assert len(row.display) <= width
        assert row.display.startswith("Lower back pain")

    async def test_mesh_silence_with_no_pubmed_answer_is_not_a_rejection(self):
        """MeSH finding nothing is not final: the quoted PubMed search
        decides compound phrases, and when it cannot answer the term must
        stay unchecked rather than be stored as not real."""
        await _denials(5, "see attached", "Lumbar radiculopathy")

        with patch(
            "fighthealthinsurance.condition_rankings._mesh_count",
            AsyncMock(return_value=0),
        ), patch(
            "fighthealthinsurance.condition_rankings._pubmed_phrase_count",
            AsyncMock(return_value=None),
        ), patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=False),
        ), patch("fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()):
            stats = await cr.refresh_term_checks()

        row = await MedicalTermCheck.objects.aget(term="lumbar radiculopathy")
        assert row.is_real is None
        assert stats["failed"] == 1

    async def test_a_row_no_longer_k_anonymous_is_not_looked_up(self):
        """A row made while its term was k-anonymous is not sent out later
        if the term has since fallen below k (a denial deleted, say)."""
        await _denials(5, "see attached", "Lower back pain")
        with patch("fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()):
            await cr.refresh_term_checks(budget=0)
        assert await MedicalTermCheck.objects.filter(is_real__isnull=True).acount() == 1
        async for denial in Denial.objects.all()[:3]:
            await denial.adelete()

        mesh = AsyncMock(return_value=1)
        with patch("fighthealthinsurance.condition_rankings._mesh_count", mesh), patch(
            "fighthealthinsurance.condition_rankings._rxnorm_matched",
            AsyncMock(return_value=False),
        ), _no_pubmed(), patch(
            "fighthealthinsurance.condition_rankings.asyncio.sleep", AsyncMock()
        ):
            stats = await cr.refresh_term_checks(budget=10)

        assert mesh.await_count == 0
        assert stats["below_k_now"] == 1
        row = await MedicalTermCheck.objects.aget(term="lower back pain")
        assert row.is_real is None

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

    async def test_a_refresh_already_running_is_skipped(self):
        """The actor's hourly refresh and the management command must not
        look up the same terms side by side."""
        from fighthealthinsurance.models import ModelHealthAlertState

        assert await sync_to_async(ModelHealthAlertState.try_claim)(
            cr._RUN_CLAIM_KEY, cr._RUN_CLAIM_SECONDS
        )

        assert await cr.refresh_term_checks() == {"skipped": 1}

    async def test_a_finished_refresh_frees_the_run_claim(self):
        await _denials(5, "MRI", "Lower back pain")
        first = await _count()
        second = await _count()

        assert "skipped" not in first
        assert "skipped" not in second

    async def test_refresh_if_due_runs_once_per_window(self):
        with patch(
            "fighthealthinsurance.condition_rankings.refresh_term_checks",
            AsyncMock(return_value={}),
        ) as refresh:
            assert await cr.refresh_if_due() is True
            assert await cr.refresh_if_due() is False

        assert refresh.await_count == 1
