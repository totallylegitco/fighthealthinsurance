"""select_passages: the passage selection the chat's search tool and the
appeal flow's plan-document helper share (fighthealthinsurance/document_grep.py).

The chat's single-query search is tested through grep_documents in
tests/sync/test_document_search.py; these cover what only several queries
at once exercise: round-robin coverage, the other-query bonus, the budget.
"""

from django.test import SimpleTestCase

from fighthealthinsurance.document_grep import (
    Passage,
    merge_adjacent,
    passage_text,
    select_passages,
)

FILLER = "General plan administration text about member services and rights.\n"


def _texts_of(texts, passages):
    return [passage_text(texts[p.source], p) for p in passages]


class TestSelectPassages(SimpleTestCase):
    def setUp(self):
        # "coverage" on every line; the code once, far away.
        self.text = (
            "".join(f"Line {i}: coverage applies here.\n" for i in range(300))
            + FILLER * 40
            + "Billing code J0135 is used for adalimumab injections.\n"
            + FILLER * 40
        )

    def test_a_query_with_one_hit_is_not_crowded_out_by_one_on_every_line(self):
        passages = select_passages(
            [self.text], ["coverage", "J0135"], budget_chars=4000, max_passages=10
        )
        self.assertTrue(any("J0135" in t for t in _texts_of([self.text], passages)))

    def test_queries_take_turns(self):
        passages = select_passages(
            [self.text], ["coverage", "J0135"], budget_chars=4000, max_passages=10
        )
        self.assertIn("J0135", passage_text(self.text, passages[1]))

    def test_passages_stay_within_the_budget(self):
        passages = select_passages(
            [self.text],
            ["coverage", "J0135"],
            budget_chars=3000,
            max_passages=50,
            per_passage_overhead=40,
        )
        spent = sum(p.end - p.start + 40 for p in passages)
        self.assertLessEqual(spent, 3000)

    def test_passages_never_overlap(self):
        passages = select_passages(
            [self.text], ["coverage", "applies"], budget_chars=20000, max_passages=30
        )
        ordered = sorted(passages, key=lambda p: p.start)
        for first, second in zip(ordered, ordered[1:]):
            self.assertLessEqual(first.end, second.start)

    def test_a_passage_where_several_queries_meet_ranks_first(self):
        text = (
            "Step therapy applies to biologics.\n"
            + FILLER * 30
            + "Step therapy exceptions: an exception is granted on appeal.\n"
            + FILLER * 30
        )
        (first, *_) = select_passages(
            [text], ["step therapy", "appeal"], budget_chars=8000, max_passages=4
        )
        self.assertIn("exception is granted on appeal", passage_text(text, first))

    def test_passages_come_from_every_text(self):
        texts = [FILLER * 20 + "Exclusions: cosmetic.\n", "Exclusions: experimental.\n"]
        passages = select_passages(
            texts, ["exclusions"], budget_chars=8000, max_passages=5
        )
        self.assertEqual({p.source for p in passages}, {0, 1})

    def test_nothing_matched_selects_nothing(self):
        self.assertEqual(
            select_passages([self.text], ["acupuncture"], 8000, max_passages=5), []
        )

    def test_a_passage_too_big_for_what_is_left_gives_way_to_a_smaller_one(self):
        # The run-on line scores higher (two hits) but its passage spans the
        # full radius both ways; the one at the very start of the text is
        # cut short by it, and fits.
        text = "short hit.\n" + FILLER * 20 + "long hit and hit " + "x " * 400 + "\n"
        passages = select_passages([text], ["hit"], budget_chars=400, max_passages=5)
        self.assertEqual(len(passages), 1)
        self.assertIn("short hit", passage_text(text, passages[0]))


class TestMergeAdjacent(SimpleTestCase):
    def test_passages_that_meet_are_joined_in_reading_order(self):
        merged = merge_adjacent(
            [Passage(0, 100, 200, 150, 1.0), Passage(0, 0, 99, 50, 2.0)], max_gap=10
        )
        self.assertEqual(merged, [Passage(0, 0, 200, 50, 2.0)])

    def test_passages_further_apart_stay_separate(self):
        passages = [Passage(0, 0, 100, 50, 1.0), Passage(0, 200, 300, 250, 1.0)]
        self.assertEqual(merge_adjacent(passages, max_gap=10), passages)

    def test_passages_from_different_texts_stay_separate(self):
        passages = [Passage(0, 0, 100, 50, 1.0), Passage(1, 100, 200, 150, 1.0)]
        self.assertEqual(merge_adjacent(passages, max_gap=10), passages)
