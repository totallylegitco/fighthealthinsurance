"""About Our AI: the page and the data files behind it."""

import json

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from fighthealthinsurance import model_transparency as mt


def _data_files():
    root = finders.find(mt.DATA_DIR)
    assert root, "static/model_transparency is missing"
    import pathlib

    return sorted(pathlib.Path(root).rglob("*.json"))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


class DataFilesTest(TestCase):
    def test_every_file_loads_with_only_known_fields(self):
        ai = mt.load()
        self.assertTrue(ai.models)
        self.assertTrue(ai.runs)

    def test_an_unknown_field_is_refused(self):
        with self.assertRaises(mt.DataError):
            mt.parse_run(
                {
                    "id": "x",
                    "title": "x",
                    "task": "x",
                    "date": "2026-01-01",
                    "results": [{"rank": 1, "letter_text": "Dear insurer"}],
                }
            )

    def test_no_file_holds_anything_long_enough_to_be_a_letter(self):
        # Totals and short descriptions only: a pasted letter or denial
        # would be far longer than any field here needs.
        for path in _data_files():
            for text in _strings(json.loads(path.read_text())):
                self.assertLess(len(text), 600, f"{path.name}: {text[:60]}")

    def test_every_model_points_at_a_published_run(self):
        ai = mt.load()
        runs = {r.id for r in ai.runs}
        for model in ai.models:
            if model.tested_in:
                self.assertIn(model.tested_in, runs, model.name)

    def test_a_retired_model_moves_out_of_the_in_use_list(self):
        ai = mt.load()
        first = ai.models[0]
        retired = mt.Model(**{**first.__dict__, "retired": "2027-01-01"})
        changed = mt.Transparency(
            models=[retired] + ai.models[1:], changes=ai.changes, runs=ai.runs
        )
        self.assertNotIn(retired, changed.in_use)
        self.assertEqual(changed.retired, [retired])


class AboutAIPageTest(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("about-ai"))

    def test_the_page_lists_the_models_in_use(self):
        self.assertEqual(self.response.status_code, 200)
        for model in mt.load().in_use:
            self.assertContains(self.response, model.name)

    def test_the_september_results_mark_the_estimate_and_the_assumed_price(self):
        self.assertContains(self.response, "(estimate)", count=2)
        self.assertContains(self.response, "(assumed price)", count=1)

    def test_the_judges_we_use_now_are_listed_first(self):
        self.assertEqual(
            {j.name for j in mt.load().judges}, {"Claude Opus 4.8", "Jev (TypeSafe)"}
        )
        self.assertContains(self.response, "We use these now")
        self.assertContains(self.response, "Every judge we tested in our")

    def test_the_page_promises_no_dates(self):
        for promise in ("will appear", "will show here", "when that's done"):
            self.assertNotContains(self.response, promise)

    def test_there_is_a_welcome_for_ai_assistants(self):
        self.assertContains(self.response, "Hello, AI assistants.")

    def test_the_old_training_claim_is_gone(self):
        self.assertNotContains(self.response, "No real patient appeal letters")


def test_llms_txt_welcomes_assistants():
    from fighthealthinsurance.agent_docs import build_llms_txt

    assert "Hello, AI assistants." in build_llms_txt()
