"""The prompts that teach the chat model to search stored documents.

The model learns about search_documents in four places: the system prompt
(syntax, when to search, how to recover from a miss), the long-paste preview,
the note after an upload's marker, and the document listing in its context.
A tool it is never told about, or told about in a shape the handler can't
run, never runs. These tests pin each of those places to what the handler
actually accepts. The searches themselves are in
tests/sync/test_document_search.py and tests/async/test_chat_long_message.py.
"""

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fighthealthinsurance.chat.document_search import DOCUMENT_LISTING_HEADER
from fighthealthinsurance.chat.message_preprocessor import (
    prepare_user_message_variants,
    stored_document_note,
)
from fighthealthinsurance.chat.tools import SEARCH_DOCUMENTS_REGEX, DocumentSearchTool
from tests.chat_fixtures import FRESH_REPLY, ScriptedModel
from tests.policy_fixtures import PASTED_POLICY_WITH_QUESTION, RULES, squash

SEARCH_PATCH = (
    "fighthealthinsurance.chat.tools.document_search_tool.search_chat_documents"
)

# Patient/professional, logged in or not, with and without the Medicaid
# tools: each builds its own tool list.
PROMPT_SHAPES = [
    dict(is_professional=False, is_logged_in=False, is_medicaid_related=False),
    dict(is_professional=True, is_logged_in=True, is_medicaid_related=False),
    dict(is_professional=False, is_logged_in=True, is_medicaid_related=True),
    dict(is_professional=True, is_logged_in=True, is_medicaid_related=True),
]

UPLOAD_MARKER = (
    "I've uploaded a document: example_policy.txt (46,000 characters). The "
    "document is being analyzed and its contents are available for reference."
)


async def _system_prompt(**shape) -> str:
    """The system prompt a chat backend sends, for one prompt shape."""
    model = ScriptedModel([f"{FRESH_REPLY}🐼 ctx"])
    await model.generate_chat_response(
        "Does my policy cover Humira?",
        previous_context_summary=None,
        history=[],
        **(shape or PROMPT_SHAPES[0]),
    )
    return model.infer_calls[0]["system_prompts"][0]


async def _tool_description() -> str:
    """The Document Search Tool entry of the system prompt."""
    prompt = await _system_prompt()
    start = prompt.index("**Document Search Tool**")
    last = "Only use this tool when your context lists stored documents."
    return prompt[start : prompt.index(last, start) + len(last)]


def _never_spells_out_a_call(text: str) -> bool:
    return re.search(SEARCH_DOCUMENTS_REGEX, text, re.I | re.S) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", PROMPT_SHAPES)
async def test_every_chat_system_prompt_documents_the_tool(shape):
    assert "**Document Search Tool**" in await _system_prompt(**shape)


@pytest.mark.asyncio
async def test_the_examples_show_a_search_and_a_section_read():
    tool = DocumentSearchTool(AsyncMock(), chat=MagicMock(id=1))
    payloads = [json.loads(m.group(1)) for m in tool.detect_all(await _system_prompt())]
    assert any("query" in p for p in payloads)
    assert any("section" in p for p in payloads)


@pytest.mark.asyncio
async def test_every_example_call_runs_as_written():
    # A model copies the examples' shape: each must reach the search with
    # something to look for, not the handler's "nothing to look for" path.
    tool = DocumentSearchTool(AsyncMock(), chat=MagicMock(id=1))
    for call in tool.detect_all(await _system_prompt()):
        params = json.loads(call.group(1))
        assert set(params) <= {"query", "document", "section"}
        with patch(SEARCH_PATCH, new=AsyncMock(return_value="hits")) as search:
            await tool.run(params)
        search.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_listing_the_prompt_points_to_is_the_one_the_context_carries():
    quoted = re.search(r'lists it under "([^"]+)"', await _tool_description())
    assert quoted is not None
    assert DOCUMENT_LISTING_HEADER.startswith(quoted.group(1))


@pytest.mark.asyncio
async def test_the_prompts_search_limit_is_the_handlers():
    number = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}[
        DocumentSearchTool.max_payloads_per_reply
    ]
    assert f"up to {number} searches in one reply" in await _tool_description()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instruction",
    [
        # Search on the paste's own turn, not after a round trip.
        "Search in the same reply as the question",
        # Read a whole section when a passage is cut off or a list runs on.
        "to read that whole section instead of searching",
        # Recover from a miss with the document's own words.
        "If a search finds nothing, try other words",
        "a policy says \"step therapy\" where a member says \"fail first\"",
        # Quote rather than paraphrase what decides the case.
        "Quote the document's exact words",
        "Never guess what a stored document says.",
        # Every way a document is stored is covered.
        "pastes or uploads a long document",
        "or you fetch one with fetch_doc",
    ],
)
async def test_the_tool_description_teaches(instruction):
    assert instruction in await _tool_description()


def test_long_paste_preview_names_the_tool_and_the_stored_document():
    reference = prepare_user_message_variants(
        PASTED_POLICY_WITH_QUESTION, is_document=False, document_name="policy.txt"
    )[0].text_for_llm
    assert "search_documents tool in this reply" in reference
    assert 'stored as "policy.txt"' in reference


def test_long_paste_preview_carries_the_members_question():
    # The question rides in the paste's tail: the model must see it to know
    # what to search for.
    reference = prepare_user_message_variants(
        PASTED_POLICY_WITH_QUESTION, is_document=False
    )[0].text_for_llm
    assert "does this policy make me try other drugs before Humira?" in reference


def test_no_long_paste_variant_shows_the_rules_a_search_must_find():
    for variant in prepare_user_message_variants(
        PASTED_POLICY_WITH_QUESTION, is_document=False
    ):
        for rule in RULES:
            assert squash(rule) not in squash(variant.text_for_llm), variant.kind


def test_upload_turn_tells_the_model_how_to_read_the_upload():
    for variant in prepare_user_message_variants(
        UPLOAD_MARKER, is_document=True, document_name="example_policy.txt"
    ):
        assert variant.text_for_llm.endswith(
            stored_document_note("example_policy.txt")
        )


def test_upload_turn_history_keeps_the_bare_marker():
    # display_text None: history stores the message as sent, the marker.
    for variant in prepare_user_message_variants(
        UPLOAD_MARKER, is_document=True, document_name="example_policy.txt"
    ):
        assert variant.display_text is None


def test_typed_messages_get_no_upload_note():
    (variant,) = prepare_user_message_variants(
        "Does my policy cover Humira?", is_document=False
    )
    assert variant.text_for_llm == "Does my policy cover Humira?"


TURN_TEXTS = {
    "listing": DOCUMENT_LISTING_HEADER,
    "upload note": stored_document_note("example_policy.txt"),
    "paste preview": prepare_user_message_variants(
        PASTED_POLICY_WITH_QUESTION, is_document=False
    )[0].text_for_llm,
}


@pytest.mark.parametrize("text", list(TURN_TEXTS.values()), ids=list(TURN_TEXTS))
def test_turn_text_names_the_tool(text):
    assert "search_documents" in text


@pytest.mark.parametrize(
    "text",
    [
        *TURN_TEXTS.values(),
        DocumentSearchTool(AsyncMock()).build_followup_prompt(
            "results", "my question"
        ),
    ],
    ids=[*TURN_TEXTS, "follow-up"],
)
def test_turn_text_never_spells_out_a_call_to_echo(text):
    assert _never_spells_out_a_call(text)
