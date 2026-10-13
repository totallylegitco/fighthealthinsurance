"""The public Appeal Arena rankings page: synthetic votes only, aggregate
conditions and treatments only, nothing about any one person."""

import datetime
import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from fighthealthinsurance import condition_rankings as cr
from fighthealthinsurance import public_rankings
from fighthealthinsurance.models import (
    ChooserCandidate,
    ChooserSkip,
    ChooserTask,
    ChooserVote,
    Denial,
    MedicalTermCheck,
    ProposedAppeal,
)


def _task(source="synthetic", models=("model-a", "model-b")):
    task = ChooserTask.objects.create(task_type="appeal", status="READY", source=source)
    candidates = [
        ChooserCandidate.objects.create(
            task=task,
            candidate_index=i,
            kind="appeal_letter",
            model_name=name,
            content=f"Draft {name}",
        )
        for i, name in enumerate(models)
    ]
    return task, candidates


def _vote(task, candidates, chosen, session, flagged=()):
    return ChooserVote.objects.create(
        task=task,
        chosen_candidate=chosen,
        presented_candidate_ids=[c.id for c in candidates],
        flagged_candidate_ids=[c.id for c in flagged],
        session_key=session,
    )


class ChooserRankingsPageTest(TestCase):
    def setUp(self):
        # Synthetic: model-a wins twice, model-b once and is flagged once.
        task, (a, b) = _task()
        _vote(task, [a, b], a, "session-secret-1")
        _vote(task, [a, b], a, "session-secret-2", flagged=[b])
        _vote(task, [a, b], b, "session-secret-3")
        ChooserSkip.objects.create(task=task, session_key="session-secret-4")
        # Not synthetic: a task built from something else must not count.
        other, (c, d) = _task(source="real_denial", models=("model-real", "model-b"))
        _vote(other, [c, d], c, "session-secret-5")

    def test_anonymous_can_read_the_page(self):
        response = self.client.get(reverse("chooser_rankings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Appeal Arena Rankings")
        self.assertContains(response, "model-a")

    def test_only_synthetic_votes_are_counted(self):
        data = public_rankings.compute_rankings()

        all_time = data["windows"][0]
        appeals = all_time["tables"][0]["rows"]
        by_model = {r["model"]: r for r in appeals}
        self.assertNotIn("model-real", by_model)
        self.assertEqual(by_model["model-a"]["won"], 2)
        self.assertEqual(by_model["model-a"]["shown"], 3)
        self.assertEqual(by_model["model-b"]["won"], 1)
        self.assertEqual(by_model["model-b"]["shown"], 3)
        self.assertEqual(by_model["model-b"]["flagged"], 1)
        self.assertAlmostEqual(by_model["model-b"]["flag_rate"], 100.0 / 3)
        self.assertEqual(data["totals"]["votes"], 3)
        self.assertEqual(data["totals"]["tasks_judged"], 1)

    def test_nothing_about_a_session_or_a_person_reaches_the_page(self):
        Denial.objects.create(
            hashed_email="hash-of-a-real-person",
            denial_text="the whole letter",
            procedure="A very rare procedure",
            diagnosis="A very rare condition",
        )
        ProposedAppeal.objects.create(appeal_text="real patient text")

        body = self.client.get(reverse("chooser_rankings")).content.decode()

        for secret in (
            "session-secret",
            "hash-of-a-real-person",
            "very rare",
            "the whole letter",
            "real patient text",
        ):
            self.assertNotIn(secret, body)

    def test_json_format(self):
        response = self.client.get(reverse("chooser_rankings") + "?format=json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("public", response["Cache-Control"])
        data = json.loads(response.content)
        self.assertEqual(data["totals"]["votes"], 3)
        self.assertEqual([w["slug"] for w in data["windows"]], ["all", "30d"])

    def test_votes_cast_before_blind_voting_began_are_left_out(self):
        """A vote from before the blind payload shipped was cast with the
        model name in the JSON; it does not belong in a leaderboard that
        says a vote is for the letter."""
        floor = public_rankings.blind_since()
        self.assertIsNotNone(floor)
        task, (a, b) = _task(models=("model-old", "model-older"))
        old = _vote(task, [a, b], a, "session-secret-old")
        ChooserVote.objects.filter(pk=old.pk).update(
            created_at=floor - datetime.timedelta(days=1)
        )

        data = public_rankings.compute_rankings()

        rows = data["windows"][0]["tables"][0]["rows"]
        self.assertNotIn("model-old", {r["model"] for r in rows})
        self.assertEqual(data["totals"]["votes"], 3)
        self.assertEqual(data["blind_since"], floor.isoformat())

    @override_settings(PUBLIC_RANKINGS_SINCE="")
    def test_an_empty_since_setting_counts_every_vote(self):
        with mock.patch.object(public_rankings, "PUBLIC_RANKINGS_SINCE", ""):
            self.assertIsNone(public_rankings.blind_since())

    def test_models_with_too_few_votes_are_warming_up_and_sort_last(self):
        task, (e, f) = _task(models=("model-e", "model-f"))
        for i in range(public_rankings.PUBLIC_RANKINGS_MIN_SHOWN):
            _vote(task, [e, f], f, f"warm-{i}")

        rows = public_rankings.compute_rankings()["windows"][0]["tables"][0]["rows"]

        ranked = [r for r in rows if not r["warming_up"]]
        warming = [r for r in rows if r["warming_up"]]
        self.assertEqual([r["model"] for r in ranked], ["model-f", "model-e"])
        self.assertEqual({r["model"] for r in warming}, {"model-a", "model-b"})
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3, 4])


class ChooserRankingsTermsTest(TestCase):
    def setUp(self):
        for i in range(7):
            Denial.objects.create(
                hashed_email=f"person-{i}",
                denial_text="denied",
                procedure="MRI",
                diagnosis="Lower back pain",
            )
        for i in range(6):
            Denial.objects.create(
                hashed_email=f"other-{i}",
                denial_text="denied",
                procedure="Something unvouched",
                diagnosis="Jane Doe",
            )
        now = timezone.now()
        MedicalTermCheck.objects.create(
            term="mri", kind=cr.KIND_TREATMENT, is_real=True, display="MRI", checked_at=now
        )
        MedicalTermCheck.objects.create(
            term="lower back pain", kind=cr.KIND_CONDITION, is_real=True, checked_at=now
        )
        MedicalTermCheck.objects.create(
            term="jane doe", kind=cr.KIND_CONDITION, is_real=False, checked_at=now
        )

    def test_only_vouched_for_terms_with_rounded_counts(self):
        data = public_rankings.compute_rankings()

        self.assertEqual(
            [(r["name"], r["count"], r["share"]) for r in data["conditions"]],
            [("Lower back pain", 5, 100)],
        )
        self.assertEqual(
            [(r["name"], r["count"]) for r in data["treatments"]], [("MRI", 5)]
        )
        self.assertEqual(data["k_anonymity"], cr.CONDITION_RANKING_MIN_PEOPLE)

    def test_bar_widths_come_from_the_rounded_counts(self):
        """Two terms shown as "5+" must get the same bar: a width from the
        true counts would tell them apart."""
        for i in range(9):
            Denial.objects.create(
                hashed_email=f"knee-{i}",
                denial_text="denied",
                procedure="MRI",
                diagnosis="Knee pain",
            )
        MedicalTermCheck.objects.create(
            term="knee pain", kind=cr.KIND_CONDITION, is_real=True, checked_at=timezone.now()
        )

        rows = public_rankings.compute_rankings()["conditions"]

        self.assertEqual([(r["count"], r["share"]) for r in rows], [(5, 100), (5, 100)])

    def test_the_page_shows_the_terms_and_not_the_rejected_ones(self):
        body = self.client.get(reverse("chooser_rankings")).content.decode()

        self.assertIn("Lower back pain", body)
        self.assertIn("5+", body)
        self.assertNotIn("Jane Doe", body)
        self.assertNotIn("Something unvouched", body)
