"""The research the chat's tools fetch, built once and read back for letters."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from django.test import SimpleTestCase

from fighthealthinsurance.chat.research_context import (
    MAX_LETTER_ARTICLES,
    ChatResearch,
    chat_research,
    pubmed_block,
    research_for_chat,
    trials_block,
)
from fighthealthinsurance.chat.tools import BaseTool, PubMedTool

ARTICLE_A = "Title: Imaging in chronic back pain\nAbstract: MRI guided care..."
# An abstract can carry a blank line of its own.
ARTICLE_B = (
    "Title: Conservative therapy outcomes\n"
    "Abstract: Six weeks of therapy.\n\nMost improved..."
)
TRIAL = "NCT: NCT01234567; Title: Pembrolizumab in Melanoma; Status: RECRUITING"


def _stored(*blocks):
    """A context entry as the chat stores it: the model's own context with
    the tool blocks joined on by merge_strings."""
    text = "The member asked about their MRI denial."
    for block in blocks:
        text = BaseTool.merge_strings(text, block)
    return text


class ResearchBlockTextTest(SimpleTestCase):
    """The chat model reads these blocks: building them in one place must
    not change a byte of what the tools sent before."""

    def test_pubmed_block_text_is_unchanged(self):
        self.assertEqual(
            pubmed_block([ARTICLE_A]),
            "\n\nWe got back pubmedcontext:[:\n"
            + ARTICLE_A
            + "]. If you reference them make sure to include the title and journal.\n",
        )

    def test_trials_block_text_is_unchanged(self):
        self.assertEqual(
            trials_block([TRIAL]),
            "\n\nWe got back clinicaltrialscontext:[\n"
            + TRIAL
            + "\n]. When citing a trial, include the NCT ID and the URL. "
            "Remember: the existence of a trial does not by itself establish "
            "coverage; use it to argue that the therapy is being actively "
            "studied or used clinically, not that the patient is enrolled in a "
            "trial.\n",
        )


class ChatResearchTest(SimpleTestCase):
    def test_stored_articles_are_read_back_whole(self):
        research = chat_research([_stored(pubmed_block([ARTICLE_A, ARTICLE_B]))])
        self.assertEqual(research.pubmed, ARTICLE_A + "\n\n" + ARTICLE_B)

    def test_stored_trials_are_read_back(self):
        research = chat_research([_stored(trials_block([TRIAL]))])
        self.assertEqual(research.clinical_trials, TRIAL)

    def test_a_repeated_article_counts_once_newest_first(self):
        research = chat_research(
            [
                _stored(pubmed_block([ARTICLE_A])),
                _stored(pubmed_block([ARTICLE_B, ARTICLE_A])),
            ]
        )
        self.assertEqual(research.pubmed, ARTICLE_B + "\n\n" + ARTICLE_A)

    def test_articles_are_capped(self):
        articles = [
            f"Title: Study {i}\nAbstract: Findings {i}..."
            for i in range(MAX_LETTER_ARTICLES + 5)
        ]
        research = chat_research([_stored(pubmed_block(articles))])
        self.assertEqual(research.pubmed.count("Title: "), MAX_LETTER_ARTICLES)

    def test_a_chat_without_research_has_none(self):
        self.assertEqual(chat_research(["Just talk.", None, ""]), ChatResearch())

    def test_an_opener_without_its_closer_takes_nothing_after_it(self):
        """A summary quoting part of a block must not pull the text up to the
        next real block in as an article."""
        quoted = "Earlier: We got back pubmedcontext:[:\nTitle: half a quote"
        research = chat_research([_stored(quoted, pubmed_block([ARTICLE_A]))])
        self.assertEqual(research.pubmed, ARTICLE_A)

    def test_a_chat_has_its_stored_and_this_turns_research(self):
        chat = SimpleNamespace(
            summary_for_next_call=[_stored(pubmed_block([ARTICLE_A]))]
        )
        research = research_for_chat(chat, [pubmed_block([ARTICLE_B])])
        self.assertEqual(research.pubmed, ARTICLE_B + "\n\n" + ARTICLE_A)


class PubMedToolRecordsResearchTest(SimpleTestCase):
    def test_articles_are_recorded_before_the_follow_up_pass(self):
        """A letter drafted in the follow-up pass reads this turn's research
        from the list, so it has to be there before that pass runs."""
        found: list = []
        seen_by_follow_up = []

        async def follow_up(*args, **kwargs):
            seen_by_follow_up.append(len(found))
            return "Here is what the studies say.", None

        pubmed_tools = MagicMock()
        pubmed_tools.find_pubmed_article_ids_for_query = AsyncMock(return_value=["1"])
        pubmed_tools.get_articles = AsyncMock(
            return_value=[
                SimpleNamespace(title="Imaging", abstract="MRI guided care", text="")
            ]
        )
        rxnorm_tools = MagicMock()
        rxnorm_tools.normalize = AsyncMock(return_value=SimpleNamespace(matched=False))
        tool = PubMedTool(
            AsyncMock(),
            pubmed_tools=pubmed_tools,
            call_llm_callback=follow_up,
            rxnorm_tools=rxnorm_tools,
            research_found=found,
        )
        text = "**pubmed_query: MRI chronic back pain**"
        asyncio.run(
            tool.execute(tool.detect(text), text, "", model_backends=[MagicMock()])
        )
        self.assertEqual(seen_by_follow_up, [1])
