"""
Integration tests for long pasted messages in the ongoing chat flow.

Verifies end-to-end (through the WebSocket consumer) that:
1. A huge paste is preserved in document storage and replaced in chat history
   with a compact marker (history stays bounded).
2. The full text is never fanned out to the model backends.
3. A turn whose content was stored answers with an acknowledgment -- never
   an error frame, and never its own marker echoed back -- when the models
   produce no real reply.
4. Re-pasting identical content reuses the stored document.
5. A normal short message still takes the original/primary path unchanged.
"""

import asyncio
import re
from itertools import pairwise
from unittest.mock import AsyncMock, patch

from channels.testing import WebsocketCommunicator
from prometheus_client import REGISTRY
from rest_framework.test import APITestCase

from fighthealthinsurance.chat.document_search import DOCUMENT_LISTING_HEADER
from fighthealthinsurance.chat.message_preprocessor import (
    DIRECT_CHAT_HARD_LIMIT_CHARS,
    DIRECT_CHAT_SOFT_LIMIT_CHARS,
    TAIL_PREVIEW_CHARS,
    build_long_paste_marker,
    stored_document_note,
)
from fighthealthinsurance.models import ChatDocument, ChatTurn
from fighthealthinsurance.websockets import OngoingChatConsumer
from tests.chat_fixtures import (
    RecordingChatModel,
    discard_background_task,
    make_professional_chat,
)
from tests.policy_fixtures import (
    APPEAL_RULE,
    EXCEPTION_RULE,
    MEMBERS_WORD_FOR_STEP_THERAPY,
    PASTED_POLICY_WITH_QUESTION,
    POLICY_TEXT,
    QUANTITY_LIMIT_RULE,
    STEP_THERAPY_RULE,
    squash,
)
from tests.sync.mock_chat_model import MockChatModel


GUIDANCE_REPLY = "Here is some guidance about your denial and next steps."


class VaryingChatModel(RecordingChatModel):
    """Answers something different on every call, so multi-turn tests don't
    trip the repeated-reply rejection ladder."""

    async def generate_chat_response(self, current_message_for_llm, **kwargs):
        await super().generate_chat_response(current_message_for_llm, **kwargs)
        n = len(self.calls)
        return (
            f"Reply number {n} with fresh guidance about the denial.",
            f"Summary: turn {n}.",
        )


# Opens the prompt of the follow-up pass that hands search results back.
SEARCH_RESULT_MARKER = "Result of your search of the user's stored documents"


_SEARCHED_FOR_RE = re.compile(r'^Search of the stored documents for "(.*)":$', re.M)
_PASSAGE_LABEL_RE = re.compile(r"^\[.+?, section (\d+) of \d+, line [\d,]+\]$", re.M)
_SECTION_READ_RE = re.compile(r"^Section \d+ of \d+ of ", re.M)


class SearchingAgentModel(RecordingChatModel):
    """A model that works stored documents the way the prompts teach.

    It searches for ``queries[0]``; while a search finds nothing it tries
    the next query ("try other words"); with ``read_sections`` it then reads
    the section the best passage names; and once it has a passage it
    answers ``answer``. ``together`` sends every query in one reply instead.
    A message ``answer_directly`` accepts gets a plain reply, which differs
    per call so later turns aren't rejected as repeats. Each step is read
    off the message it is sent, never kept as state, since a pass may ask
    it more than once.
    """

    def __init__(
        self,
        queries,
        answer,
        *,
        read_sections=True,
        together=False,
        answer_directly=lambda message: False,
    ):
        super().__init__()
        self._queries = list(queries)
        self._answer = answer
        self._read_sections = read_sections
        self._together = together
        self._answer_directly = answer_directly

    @staticmethod
    def _search(*queries):
        calls = "\n".join(f'**search_documents {{"query": "{q}"}}**' for q in queries)
        return calls, "Summary: searching the stored policy."

    async def generate_chat_response(self, current_message_for_llm, **kwargs):
        await super().generate_chat_response(current_message_for_llm, **kwargs)
        message = current_message_for_llm or ""
        if SEARCH_RESULT_MARKER not in message:
            if self._answer_directly(message):
                return (
                    f"Reply number {len(self.calls)} about your policy.",
                    "Summary: discussing the policy.",
                )
            return self._search(*(self._queries if self._together else self._queries[:1]))
        searched = _SEARCHED_FOR_RE.search(message)
        if searched and not self._together:
            if "Nothing matched" in message:
                tried = self._queries.index(searched.group(1))
                if tried + 1 < len(self._queries):
                    return self._search(self._queries[tried + 1])
            elif self._read_sections:
                label = _PASSAGE_LABEL_RE.search(message)
                if label:
                    return (
                        f'**search_documents {{"section": {label.group(1)}}}**',
                        "Summary: reading the section.",
                    )
        return self._answer, "Summary: answered from the stored policy."


def _search_results(model: RecordingChatModel) -> list[str]:
    """The follow-up messages that carried search results, in order."""
    return [m for m in _messages_sent(model) if SEARCH_RESULT_MARKER in m]


def _failing_model() -> MockChatModel:
    """A backend whose every generation attempt fails (returns nothing)."""
    model = MockChatModel()
    model.set_persistent_response(None, None)
    return model


def _messages_sent(model: RecordingChatModel) -> list[str]:
    """Every message the model was asked to generate a reply to."""
    return [call["message"] for call in model.calls]


def _unsaved_document(chat, document_name, full_text, **_):
    """Stand-in for process_uploaded_document: the document storage would
    return, without touching the database."""
    return ChatDocument(
        chat=chat,
        document_name=document_name,
        full_text=full_text,
        char_count=len(full_text),
    )


def _counter(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def _drain_to_content(communicator):
    response = await communicator.receive_json_from(timeout=20)
    while "status" in response:
        response = await communicator.receive_json_from(timeout=20)
    return response


class ChatTurnTestCase(APITestCase):
    """Drives chat turns through the WebSocket consumer against
    ``self.model`` (reassign it before the first turn to swap the backend).
    Background work -- turn summaries, document analysis -- is handed to
    mocks that discard it, so no ML work ever runs."""

    BIG = ""  # The long paste a subclass sends with paste_big().

    def setUp(self):
        super().setUp()
        self.model = RecordingChatModel(always_reply=GUIDANCE_REPLY)
        self.enterContext(
            patch(
                "fighthealthinsurance.ml.ml_router.MLRouter.get_chat_backends",
                side_effect=lambda *args, **kwargs: [self.model],
            )
        )
        self.enterContext(
            patch(
                "fighthealthinsurance.ml.ml_router.MLRouter.get_chat_backends_with_fallback",
                side_effect=lambda *args, **kwargs: ([self.model], []),
            )
        )
        self.enterContext(
            patch(
                "fighthealthinsurance.chat_interface.fire_and_forget_in_new_threadpool",
                new=AsyncMock(side_effect=discard_background_task),
            )
        )
        self.enterContext(
            patch(
                "fighthealthinsurance.chat.document_processor.fire_and_forget_in_new_threadpool",
                new=AsyncMock(side_effect=discard_background_task),
            )
        )

    def mock_document_storage(self) -> AsyncMock:
        """Replace the turn's document storage with an in-memory stand-in."""
        return self.enterContext(
            patch(
                "fighthealthinsurance.chat_interface.process_uploaded_document",
                new=AsyncMock(side_effect=_unsaved_document),
            )
        )

    async def new_chat(self):
        """A professional user and their empty chat (one per test: each
        test's rows are rolled back)."""
        return await make_professional_chat("longpaste", "9999950001")

    async def run_turns(self, user, *payloads) -> list[dict]:
        """Send each payload over one connection, returning the first
        non-status frame received after each."""
        communicator = WebsocketCommunicator(
            OngoingChatConsumer.as_asgi(), "/ws/ongoing-chat/"
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        try:
            responses = []
            for payload in payloads:
                await communicator.send_json_to(payload)
                responses.append(await _drain_to_content(communicator))
            return responses
        finally:
            await communicator.disconnect()

    async def send(self, user, chat, content, **extra) -> dict:
        """Run a single turn sending ``content``; return its response frame."""
        (response,) = await self.run_turns(
            user, {"chat_id": str(chat.id), "content": content, **extra}
        )
        return response

    async def paste_big(self, **extra):
        """Paste ``BIG`` as the first turn of a new chat; return the
        refreshed chat and the turn's response frame."""
        user, chat = await self.new_chat()
        response = await self.send(user, chat, self.BIG, **extra)
        await chat.arefresh_from_db()
        return chat, response


class LongPasteChatTest(ChatTurnTestCase):
    """One huge paste, storage mocked out: what reaches storage, chat
    history and the model."""

    BIG = (
        "This claim was denied because the requested service is considered "
        "not medically necessary. "
    ) * 700  # ~63k chars, well over the hard limit

    def setUp(self):
        super().setUp()
        self.assertGreater(len(self.BIG), DIRECT_CHAT_HARD_LIMIT_CHARS)
        self.mock_store = self.mock_document_storage()

    async def test_paste_turn_delivers_the_model_reply(self):
        _, response = await self.paste_big()
        self.assertEqual(response.get("content"), GUIDANCE_REPLY)

    async def test_full_text_is_stored_under_a_generated_name(self):
        await self.paste_big()
        self.mock_store.assert_awaited_once()
        store_kwargs = self.mock_store.await_args.kwargs
        self.assertEqual(store_kwargs["full_text"], self.BIG)
        self.assertTrue(store_kwargs["document_name"].startswith("pasted_message_"))

    async def test_history_stores_a_compact_marker(self):
        chat, _ = await self.paste_big()
        user_msgs = [m for m in chat.chat_history if m.get("role") == "user"]
        self.assertEqual(len(user_msgs), 1)
        stored = user_msgs[0]["content"]
        self.assertLess(len(stored), 500)
        self.assertIn("stored for reference", stored.lower())
        self.assertNotIn(self.BIG, stored)

    async def test_full_text_is_never_sent_to_the_model(self):
        await self.paste_big()
        sent = _messages_sent(self.model)
        self.assertTrue(sent)
        for msg in sent:
            self.assertNotIn(self.BIG, msg)
            self.assertLess(len(msg), len(self.BIG))

    async def test_history_alternates_after_paste(self):
        chat, _ = await self.paste_big()
        roles = [m.get("role") for m in chat.chat_history]
        # Alternation: no two consecutive messages share a role.
        for prev, nxt in pairwise(roles):
            self.assertNotEqual(prev, nxt)
        self.assertEqual(roles[-1], "assistant")


class LongPasteAllModelsFailTest(ChatTurnTestCase):
    """When every model fails on a long-paste turn, the user must get a
    useful acknowledgment (content stored, how to proceed) instead of the
    generic all-models-down error frame -- the paste IS stored and queued
    for analysis, so 'try again' would only duplicate the failure. Storage
    is real here: the acknowledgment must only ever claim "stored" when the
    content truly is."""

    BIG = "Coverage denied: intensive outpatient program not authorized. " * 400

    def setUp(self):
        super().setUp()
        self.model = _failing_model()

    async def test_total_model_failure_yields_acknowledgment_not_error(self):
        _, response = await self.paste_big()
        self.assertNotIn("error", response)
        self.assertIn("paste it again", response.get("content", ""))

    async def test_acknowledgment_names_the_stored_document(self):
        chat, response = await self.paste_big()
        docs = [d async for d in ChatDocument.objects.filter(chat_id=chat.id)]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].full_text, self.BIG)
        self.assertIn(docs[0].document_name, response.get("content", ""))

    async def test_history_pairs_the_marker_with_the_acknowledgment(self):
        chat, response = await self.paste_big()
        roles = [m.get("role") for m in chat.chat_history]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertIn("stored for reference", chat.chat_history[0]["content"])
        self.assertEqual(chat.chat_history[1]["content"], response.get("content"))

    async def test_failed_paste_turn_row_says_failed(self):
        # Only the frame the user sees changes: the turn is still a failure.
        chat, _ = await self.paste_big()
        row = await ChatTurn.objects.filter(chat=chat).aget()
        self.assertEqual(row.outcome, "failed")

    async def test_total_model_failure_on_short_message_still_errors(self):
        # The acknowledgment fallback is only for turns whose content was
        # diverted to storage; an ordinary failed turn keeps the error frame.
        user, chat = await self.new_chat()
        response = await self.send(user, chat, "Why was my claim denied?")
        self.assertIn("error", response)


class LongPasteMarkerEchoTest(ChatTurnTestCase):
    """A model that can only echo the paste's marker back. The ladder's
    last resort delivers a repeat because a repeat beats an error frame; a
    stored-content turn has something better than either -- its
    acknowledgment -- so the echo must never reach the user."""

    DOCUMENT_NAME = "denial_letter.txt"
    BIG = " ".join(["Denied: out-of-network emergency transport not covered."] * 400)

    def setUp(self):
        super().setUp()
        self.model = RecordingChatModel(
            always_reply=build_long_paste_marker(len(self.BIG), self.DOCUMENT_NAME)
        )

    async def paste_big(self):
        return await super().paste_big(document_name=self.DOCUMENT_NAME)

    async def test_marker_echo_is_replaced_by_acknowledgment(self):
        _, response = await self.paste_big()
        self.assertIn("paste it again", response.get("content", ""))

    async def test_replacement_is_counted_apart_from_delivered_repeats(self):
        replaced = {"action": "replaced_by_stored_content_ack"}
        before = _counter("fhi_chat_repeated_responses_total", **replaced)
        await self.paste_big()
        self.assertEqual(
            _counter("fhi_chat_repeated_responses_total", **replaced), before + 1
        )

    async def test_replacement_turn_row_says_ok(self):
        # The acknowledgment goes out as the turn's reply, so the ChatTurn
        # row follows the metric's "ok", like any delivered reply.
        chat, _ = await self.paste_big()
        row = await ChatTurn.objects.filter(chat=chat).aget()
        self.assertEqual(row.outcome, "ok")

    async def test_replacement_is_not_counted_as_a_failed_turn(self):
        # The models DID answer (only with repeats): alerting on it as a
        # failed turn would page on a turn that worked.
        failed_before = _counter("fhi_chat_turns_total", outcome="failed")
        await self.paste_big()
        self.assertEqual(
            _counter("fhi_chat_turns_total", outcome="failed"), failed_before
        )

    async def test_replacement_raises_no_total_failure_event(self):
        with patch(
            "fighthealthinsurance.chat_interface.capture_reliability_event"
        ) as capture:
            await self.paste_big()
        events = [call.args[0] for call in capture.call_args_list]
        self.assertNotIn("chat_turn_total_failure", events)


class LongPasteCrashedTurnTest(ChatTurnTestCase):
    async def test_setup_failure_after_storage_still_releases_summarization(self):
        # A raise between storage and the LLM pass (here: history prep) ends
        # the turn early. The stored paste's worker must still be released
        # -- however the turn ends -- not left waiting with it unanalyzed.
        big = "Denial letter contents pasted just before a setup crash. " * 400
        self.enterContext(
            patch(
                "fighthealthinsurance.chat_interface.prepare_history_for_llm",
                side_effect=RuntimeError("boom after storage"),
            )
        )
        worker = self.enterContext(
            patch(
                "fighthealthinsurance.chat.document_processor._summarize_when_released",
                side_effect=lambda *args: asyncio.sleep(0),
            )
        )
        user, chat = await self.new_chat()
        response = await self.send(user, chat, big)

        # The turn itself failed (consumer-level error frame)...
        self.assertIn("error", response)

        # ...but its paste was stored with one worker, which it released.
        doc = await ChatDocument.objects.aget(chat_id=chat.id)
        ((doc_id, _, release),) = [call.args for call in worker.call_args_list]
        self.assertEqual(doc_id, doc.id)
        self.assertTrue(release.is_set())


class LongPasteDedupTest(ChatTurnTestCase):
    """Re-pasting the same long message (say, after a failed turn) must not
    create a second stored document, and the marker in history must keep
    referencing the document that actually exists. (That it is never
    analyzed twice at once is the claim's job; test_document_processing
    covers it.)"""

    # ~20k chars: over the soft limit that triggers long-paste storage (like
    # the ~19k production failure) though under the hard cap.
    BIG = "Denied for lack of prior authorization on imaging. " * 400

    def setUp(self):
        super().setUp()
        self.model = VaryingChatModel()

    async def paste_big_twice(self):
        self.assertGreater(len(self.BIG), DIRECT_CHAT_SOFT_LIMIT_CHARS)
        user, chat = await self.new_chat()
        payload = {"chat_id": str(chat.id), "content": self.BIG}
        await self.run_turns(user, payload, payload)
        await chat.arefresh_from_db()
        return chat

    async def test_repaste_reuses_the_stored_document(self):
        chat = await self.paste_big_twice()
        self.assertEqual(await ChatDocument.objects.filter(chat=chat).acount(), 1)

    async def test_every_marker_names_the_stored_document(self):
        chat = await self.paste_big_twice()
        doc = await ChatDocument.objects.aget(chat=chat)
        user_msgs = [m["content"] for m in chat.chat_history if m.get("role") == "user"]
        self.assertEqual(len(user_msgs), 2)
        for msg in user_msgs:
            self.assertIn(doc.document_name, msg)


class LongPasteNameAdoptionDoesNotCorruptContentTest(ChatTurnTestCase):
    """Adopting a deduped document's name must not rewrite the user's own
    words. document_name is client-supplied and the truncated variant's text
    IS the raw paste, so a name that occurs in the pasted content (here the
    word "denied") must never be substituted inside the message we send to
    the model."""

    async def test_repaste_with_content_word_as_document_name(self):
        big = "The claim was denied because it was denied again. " * 500
        self.assertGreater(len(big), DIRECT_CHAT_SOFT_LIMIT_CHARS)
        self.model = VaryingChatModel()
        user, chat = await self.new_chat()
        await self.run_turns(
            user,
            # First paste stores the document under its own name.
            {"chat_id": str(chat.id), "content": big, "document_name": "first_doc.txt"},
            # Re-paste of the SAME content, this time naming it with a word
            # that appears throughout that content. It dedupes onto
            # "first_doc.txt", triggering name adoption.
            {"chat_id": str(chat.id), "content": big, "document_name": "denied"},
        )

        doc = await ChatDocument.objects.aget(chat=chat)
        self.assertEqual(doc.document_name, "first_doc.txt")

        # The user's words survived intact: no message sent to the model
        # contains the substitution "first_doc.txt" where the user wrote
        # "denied".
        sent = _messages_sent(self.model)
        self.assertTrue(sent)
        for msg in sent:
            self.assertNotIn("was first_doc.txt because", msg)


class LongPasteDocumentSearchTest(ChatTurnTestCase):
    """A model searches a long paste on the paste's own turn: a passage past
    everything it was shown reaches its follow-up pass, which writes the
    reply the user gets. Storage is real -- the search reads the stored row,
    still unanalyzed, as it would be mid-turn."""

    NEEDLE = (
        "Exception criteria: the plan covers the brand drug when two generics "
        "failed or caused an adverse reaction."
    )
    FILLER = "Section text about general plan administration and member rights. "
    BIG = FILLER * 450 + NEEDLE + " " + FILLER * 60
    ANSWER = "Your policy covers the brand drug once two generics have failed."

    def setUp(self):
        super().setUp()
        # Past the last-resort variant's cut and before the tail preview: no
        # message variant shows it.
        start = self.BIG.index(self.NEEDLE)
        self.assertGreater(start, DIRECT_CHAT_HARD_LIMIT_CHARS)
        self.assertLess(start + len(self.NEEDLE), len(self.BIG) - TAIL_PREVIEW_CHARS)
        self.model = SearchingAgentModel(
            ["exception criteria"], self.ANSWER, read_sections=False
        )

    async def test_reply_is_written_from_the_search_results(self):
        _, response = await self.paste_big()
        self.assertEqual(response.get("content"), self.ANSWER)

    async def test_only_the_search_shows_the_model_the_buried_passage(self):
        await self.paste_big()
        sent = _messages_sent(self.model)
        follow_ups = [m for m in sent if SEARCH_RESULT_MARKER in m]
        self.assertEqual(len(follow_ups), 1)
        self.assertIn(self.NEEDLE, follow_ups[0])
        for msg in sent:
            if SEARCH_RESULT_MARKER not in msg:
                self.assertNotIn(self.NEEDLE, msg)

    async def test_paste_turn_names_the_tool_to_the_model(self):
        await self.paste_big()
        self.assertIn("search_documents tool", self.model.calls[0]["message"])

    async def test_paste_turn_context_lists_the_paste_without_random_sections(self):
        await self.paste_big()
        context = self.model.calls[0]["context"]
        self.assertIn(DOCUMENT_LISTING_HEADER, context)
        self.assertNotIn("Relevant sections", context)


POLICY_ANSWER = (
    "Yes -- the policy's step therapy section says you must first try two "
    "preferred biosimilars, Hyrimoz and Idacio, for 12 weeks each."
)


class PastedPolicySearchTest(ChatTurnTestCase):
    """A member pastes a long plan policy with their question at the end.
    The agent works it as the prompts teach -- search, read the section the
    best passage names, answer -- all on the paste's own turn, against the
    real stored (still unanalyzed) paste."""

    BIG = PASTED_POLICY_WITH_QUESTION

    def setUp(self):
        super().setUp()
        self.model = SearchingAgentModel(["step therapy"], POLICY_ANSWER)

    async def test_the_member_gets_the_answer_written_from_the_policy(self):
        _, response = await self.paste_big()
        self.assertEqual(response.get("content"), POLICY_ANSWER)

    async def test_the_section_read_hands_the_model_the_whole_rule(self):
        await self.paste_big()
        reads = [m for m in _search_results(self.model) if _SECTION_READ_RE.search(m)]
        self.assertEqual(len(reads), 1)
        self.assertIn(squash(STEP_THERAPY_RULE), squash(reads[0]))

    async def test_only_the_tool_shows_the_model_the_rule(self):
        await self.paste_big()
        for call in self.model.calls:
            if SEARCH_RESULT_MARKER not in call["message"]:
                self.assertNotIn(squash(STEP_THERAPY_RULE), squash(call["message"]))
                self.assertNotIn(
                    squash(STEP_THERAPY_RULE), squash(call["context"] or "")
                )

    async def test_the_section_read_quotes_the_members_question_once(self):
        # The second follow-up names the user's message, not the first
        # search's results a second time.
        await self.paste_big()
        (read,) = [m for m in _search_results(self.model) if _SECTION_READ_RE.search(m)]
        self.assertEqual(read.count("Search of the stored documents for"), 0)
        self.assertEqual(read.count("does this policy make me try other drugs"), 1)

    async def test_the_turn_counts_the_search_and_the_section_read(self):
        chat, _ = await self.paste_big()
        row = await ChatTurn.objects.filter(chat=chat).aget()
        self.assertEqual(row.tool_passes, 2)


class PastedPolicyRetryTest(ChatTurnTestCase):
    """The member's word for the rule is not the policy's: the agent's first
    search finds nothing, and it searches again in the policy's words."""

    BIG = PASTED_POLICY_WITH_QUESTION

    def setUp(self):
        super().setUp()
        self.model = SearchingAgentModel(
            [MEMBERS_WORD_FOR_STEP_THERAPY, "step therapy"], POLICY_ANSWER
        )

    async def test_the_first_search_tells_the_model_nothing_matched(self):
        await self.paste_big()
        self.assertIn("Nothing matched", _search_results(self.model)[0])

    async def test_the_retry_in_the_policys_words_finds_the_rule(self):
        await self.paste_big()
        later = squash(" ".join(_search_results(self.model)[1:]))
        self.assertIn(squash(STEP_THERAPY_RULE), later)

    async def test_the_retry_still_ends_in_the_answer(self):
        _, response = await self.paste_big()
        self.assertEqual(response.get("content"), POLICY_ANSWER)


class PastedPolicyManySearchesTest(ChatTurnTestCase):
    """Several searches in one reply come back in one follow-up."""

    BIG = PASTED_POLICY_WITH_QUESTION

    def setUp(self):
        super().setUp()
        self.model = SearchingAgentModel(
            ["quantity limit", "internal appeal"], POLICY_ANSWER, together=True
        )

    async def test_one_follow_up_carries_every_search(self):
        await self.paste_big()
        (results,) = _search_results(self.model)
        self.assertIn(squash(QUANTITY_LIMIT_RULE), squash(results))
        self.assertIn(squash(APPEAL_RULE), squash(results))


class PastedPolicyLaterTurnTest(ChatTurnTestCase):
    """The policy was pasted on an earlier turn; the question comes later,
    before the paste's analysis has finished (it is discarded here, so the
    stored row stays unanalyzed)."""

    QUESTION = "Can I get an exception to that rule?"

    async def paste_then_ask(self, question):
        user, chat = await self.new_chat()
        _, response = await self.run_turns(
            user,
            {"chat_id": str(chat.id), "content": PASTED_POLICY_WITH_QUESTION},
            {"chat_id": str(chat.id), "content": question},
        )
        return response

    async def test_a_later_question_brings_its_rule_into_context(self):
        self.model = VaryingChatModel()
        await self.paste_then_ask("What is the quantity limit on the pens?")
        asked = [c for c in self.model.calls if "quantity limit on the pens" in c["message"]]
        self.assertTrue(asked)
        self.assertIn(squash(QUANTITY_LIMIT_RULE), squash(asked[-1]["context"]))

    async def test_the_agent_searches_the_earlier_paste(self):
        self.model = SearchingAgentModel(
            ["step therapy exception"],
            POLICY_ANSWER,
            answer_directly=lambda message: self.QUESTION not in message,
        )
        response = await self.paste_then_ask(self.QUESTION)
        self.assertEqual(response.get("content"), POLICY_ANSWER)
        self.assertIn(
            squash(EXCEPTION_RULE), squash(" ".join(_search_results(self.model)))
        )


class UploadedPolicySearchTest(ChatTurnTestCase):
    """An uploaded policy: the model is shown none of it, is told how to
    read it, and reads it before answering."""

    NAME = "example_policy.txt"

    def setUp(self):
        super().setUp()
        self.model = SearchingAgentModel(["internal appeal"], POLICY_ANSWER)

    async def upload(self):
        user, chat = await self.new_chat()
        response = await self.send(
            user, chat, POLICY_TEXT, is_document=True, document_name=self.NAME
        )
        await chat.arefresh_from_db()
        return chat, response

    async def test_upload_turn_tells_the_model_how_to_read_it(self):
        await self.upload()
        self.assertIn(stored_document_note(self.NAME), self.model.calls[0]["message"])

    async def test_upload_history_keeps_the_bare_marker(self):
        chat, _ = await self.upload()
        self.assertNotIn("search_documents", chat.chat_history[0]["content"])

    async def test_the_search_reads_the_uploaded_policy(self):
        await self.upload()
        self.assertIn(
            squash(APPEAL_RULE), squash(" ".join(_search_results(self.model)))
        )

    async def test_the_member_gets_the_answer(self):
        _, response = await self.upload()
        self.assertEqual(response.get("content"), POLICY_ANSWER)


class NormalMessagePrimaryPathTest(ChatTurnTestCase):
    MESSAGE = "Why was my physical therapy claim denied?"

    def setUp(self):
        super().setUp()
        self.mock_store = self.mock_document_storage()

    async def test_short_message_is_not_routed_to_storage(self):
        user, chat = await self.new_chat()
        await self.send(user, chat, self.MESSAGE)
        self.mock_store.assert_not_awaited()

    async def test_short_message_is_stored_verbatim(self):
        user, chat = await self.new_chat()
        response = await self.send(user, chat, self.MESSAGE)
        self.assertIn("content", response)
        await chat.arefresh_from_db()
        user_msgs = [m for m in chat.chat_history if m.get("role") == "user"]
        self.assertEqual(len(user_msgs), 1)
        self.assertEqual(user_msgs[0]["content"], self.MESSAGE)
