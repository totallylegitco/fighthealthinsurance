"""Appeal scenarios in the chooser: seeded from the real-condition pool,
with case facts and the evidence already on file. Every model and every
outside service is a mock; a live PubMed search is off in tests
(CHOOSER_PUBMED_LIVE_SEARCH) and asserted never to run."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import override_settings

from fighthealthinsurance.chooser_tasks import (
    _evidence_for,
    _generate_appeal_candidates,
)
from fighthealthinsurance.condition_rankings import SeedPair
from fighthealthinsurance.models import (
    ChooserCandidate,
    ChooserTask,
    PubMedMiniArticle,
    PubMedQueryData,
)

_LETTER = "Dear Reviewer, " + "this care is medically necessary. " * 10


def _writer(scenario):
    model = MagicMock()
    model.name = "model-a"
    model.external = False
    model._infer_no_context = AsyncMock(side_effect=[scenario] + [_LETTER] * 10)
    return model


async def _cached_search(query, pmids):
    await PubMedQueryData.objects.acreate(query=query, articles=json.dumps(pmids))


async def _article(pmid, title, url=None):
    await PubMedMiniArticle.objects.acreate(pmid=pmid, title=title, article_url=url)


def _no_live_search():
    return patch(
        "fighthealthinsurance.pubmed_tools.PubMedTools.find_pubmed_article_ids_for_query",
        AsyncMock(side_effect=AssertionError("live PubMed search ran")),
    )


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestEvidenceFor:
    async def test_cached_searches_are_reused_newest_first(self):
        await _cached_search("MRI Lower back pain", ["1", "2"])
        await _cached_search("mri lower back pain", ["3"])
        await _article("1", "Imaging for low back pain", "https://example.org/1")
        await _article("2", "")  # no title: never shown
        await _article("3", "A newer study")

        with _no_live_search():
            evidence = await _evidence_for("MRI", "Lower back pain")

        assert evidence == [
            {"pmid": "3", "title": "A newer study", "url": "https://pubmed.ncbi.nlm.nih.gov/3/"},
            {"pmid": "1", "title": "Imaging for low back pain", "url": "https://example.org/1"},
        ]

    async def test_nothing_cached_and_no_live_search_means_no_evidence(self):
        with _no_live_search():
            assert await _evidence_for("MRI", "Lower back pain") == []

    @override_settings(CHOOSER_PUBMED_LIVE_SEARCH=True)
    async def test_live_search_runs_only_when_nothing_is_cached(self):
        await _article("9", "Found live")
        search = AsyncMock(return_value=["9"])
        with patch(
            "fighthealthinsurance.pubmed_tools.PubMedTools.find_pubmed_article_ids_for_query",
            search,
        ):
            evidence = await _evidence_for("MRI", "Lower back pain")

        assert [e["pmid"] for e in evidence] == ["9"]
        assert search.await_args.args[0] == "MRI Lower back pain"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestSeededScenario:
    async def _generate(self, scenario, seed):
        task = await ChooserTask.objects.acreate(task_type="appeal", status="QUEUED")
        model = _writer(scenario)
        with patch("fighthealthinsurance.chooser_tasks.ml_router") as router, patch(
            "fighthealthinsurance.chooser_tasks._maybe_add_synthesized_candidate",
            AsyncMock(),
        ), patch(
            "fighthealthinsurance.chooser_tasks._pick_seed_pair",
            AsyncMock(return_value=seed),
        ), _no_live_search():
            router.generate_text_backends.return_value = [model]
            await _generate_appeal_candidates(task)
        await task.arefresh_from_db()
        return task, model

    async def test_the_seed_is_the_case_whatever_the_writer_echoed(self):
        await _cached_search("MRI Lower back pain", ["1"])
        await _article("1", "Imaging for low back pain")
        scenario = (
            "Procedure: Magnetic resonance imaging\nDiagnosis: lumbago\n"
            "Insurance Company: Fictional Mutual\nDenial Reason: not medically necessary.\n"
            "Case Facts: Patient in their 40s; eight months of symptoms; physical therapy failed.\n"
        )

        task, model = await self._generate(scenario, SeedPair("MRI", "Lower back pain", 8))

        assert task.status != "DISABLED"
        assert task.context_json["procedure"] == "MRI"
        assert task.context_json["diagnosis"] == "Lower back pain"
        assert task.context_json["seeded"] is True
        assert task.context_json["facts"] == [
            "Patient in their 40s",
            "eight months of symptoms",
            "physical therapy failed",
        ]
        assert [e["pmid"] for e in task.context_json["evidence"]] == ["1"]
        # The writer was told the pair, and the drafts were told the facts
        # and the evidence.
        scenario_prompt = model._infer_no_context.await_args_list[0].kwargs["prompt"]
        assert "MRI for Lower back pain" in scenario_prompt
        draft_prompt = model._infer_no_context.await_args_list[1].kwargs["prompt"]
        assert "- Patient in their 40s" in draft_prompt
        assert "Imaging for low back pain (PMID 1)" in draft_prompt
        assert await ChooserCandidate.objects.filter(task=task).acount() >= 1

    async def test_without_a_seed_the_writer_invents_the_pair(self):
        scenario = (
            "Procedure: Knee arthroscopy\nDiagnosis: Torn meniscus\n"
            "Insurance Company: Fictional Mutual\nDenial Reason: experimental.\n"
        )

        task, _ = await self._generate(scenario, None)

        assert task.context_json["procedure"] == "Knee arthroscopy"
        assert task.context_json["seeded"] is False
        assert "facts" not in task.context_json
        assert task.context_json["evidence"] == []

    async def test_a_seeded_scenario_still_needs_the_insurer_and_reason(self):
        task, _ = await self._generate("Procedure: MRI\nDiagnosis: pain\n", SeedPair("MRI", "Lower back pain", 8))

        assert task.status == "DISABLED"
