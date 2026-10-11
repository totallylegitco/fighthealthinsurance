"""The research the chat's tools fetched, built and read back in one place.

PubMedTool and ClinicalTrialsTool hand the chat model what they found as
``pubmedcontext:[...]`` and ``clinicaltrialscontext:[...]`` blocks in the
turn's context, which the chat stores in ``summary_for_next_call``. A letter
drafted through the appeal pipeline (chat/appeal_letter_generator) should
argue from the same evidence the person just saw discussed, so the blocks
are built here and read back here, from one definition of their shape: a
change to how a tool words its block can't silently stop the letter from
finding it.
"""

import re
from typing import Any, Iterable, List, NamedTuple, Optional

# The markers the readers anchor on. Each block is joined into the turn's
# context with merge_strings, which strips the newlines around it, so the
# readers match these, not the padded forms the builders write.
_PUBMED_OPEN = "We got back pubmedcontext:[:\n"
_PUBMED_CLOSE = "]. If you reference them make sure to include the title and journal."
_TRIALS_OPEN = "We got back clinicaltrialscontext:[\n"
_TRIALS_CLOSE = "\n]. When citing a trial, include the NCT ID and the URL."
_TRIALS_GUIDANCE = (
    " Remember: the existence of a trial does not by itself establish coverage; "
    "use it to argue that the therapy is being actively studied or used clinically, "
    "not that the patient is enrolled in a trial.\n"
)


def _block_re(opener: str, closer: str) -> re.Pattern[str]:
    """A block's body: from ``opener`` to the first ``closer``, never across
    another ``opener``, so an opener left without its closer (a model's
    summary quoting part of a block) can't pull the text after it, up to
    the next real block, in as research."""
    open_re = re.escape(opener)
    return re.compile(
        open_re + r"((?:(?!" + open_re + r").)*?)" + re.escape(closer), re.DOTALL
    )


_PUBMED_BLOCK_RE = _block_re(_PUBMED_OPEN, _PUBMED_CLOSE)
_TRIALS_BLOCK_RE = _block_re(_TRIALS_OPEN, _TRIALS_CLOSE)
# Article summaries are "Title: ...\nAbstract: ..." joined by blank lines;
# an abstract can hold a blank line of its own, so split only before a title.
_PUBMED_ITEM_SPLIT_RE = re.compile(r"\n\n(?=Title: )")
# A trial is one line (format_trial_short); trials are joined by blank lines.
_TRIALS_ITEM_SPLIT_RE = re.compile(r"\n\n+")

# How much of the chat's research a letter takes, newest first: a PubMed
# search surfaces up to 8 articles of ~500 characters, and a long chat can
# hold many searches. make_appeals' shed ladder still drops the evidence
# when a prompt runs too large.
MAX_LETTER_ARTICLES = 10
MAX_LETTER_TRIALS = 6


def pubmed_block(summaries: List[str]) -> str:
    """The block PubMedTool adds to the turn's context."""
    return "\n\n" + _PUBMED_OPEN + "\n\n".join(summaries) + _PUBMED_CLOSE + "\n"


def trials_block(rendered: List[str]) -> str:
    """The block ClinicalTrialsTool adds to the turn's context."""
    return (
        "\n\n" + _TRIALS_OPEN + "\n\n".join(rendered) + _TRIALS_CLOSE + _TRIALS_GUIDANCE
    )


class ChatResearch(NamedTuple):
    """What the chat's tools found, as letter-pipeline context: each field
    is the text make_appeals takes for that source, or None."""

    pubmed: Optional[str] = None
    clinical_trials: Optional[str] = None


def _newest_items(
    texts: List[str],
    block_re: re.Pattern[str],
    split_re: re.Pattern[str],
    limit: int,
) -> Optional[str]:
    """The newest ``limit`` distinct items from the blocks in ``texts``
    (oldest text first), newest first, or None when there are none."""
    items: List[str] = []
    seen = set()
    for text in reversed(texts):
        for block in reversed(block_re.findall(text)):
            for item in split_re.split(block):
                item = item.strip()
                if item and item not in seen:
                    seen.add(item)
                    items.append(item)
                    if len(items) >= limit:
                        return "\n\n".join(items)
    return "\n\n".join(items) or None


def chat_research(texts: Iterable[Optional[str]]) -> ChatResearch:
    """The research found in ``texts`` -- the chat's stored context entries
    and this turn's tool results, oldest first -- de-duplicated, newest
    first, capped per source."""
    strings = [str(t) for t in texts if t]
    return ChatResearch(
        pubmed=_newest_items(
            strings, _PUBMED_BLOCK_RE, _PUBMED_ITEM_SPLIT_RE, MAX_LETTER_ARTICLES
        ),
        clinical_trials=_newest_items(
            strings, _TRIALS_BLOCK_RE, _TRIALS_ITEM_SPLIT_RE, MAX_LETTER_TRIALS
        ),
    )


def research_for_chat(chat: Any, found_this_turn: Iterable[str] = ()) -> ChatResearch:
    """The research a letter for ``chat`` should use: what its stored
    context entries hold (summary_for_next_call keeps the recent turns'
    tool results verbatim), plus what the tools found this turn, which is
    stored only once the turn ends."""
    return chat_research(
        [*(getattr(chat, "summary_for_next_call", None) or []), *found_this_turn]
    )
