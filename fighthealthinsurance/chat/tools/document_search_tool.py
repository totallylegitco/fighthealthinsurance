"""
Stored-document search tool for the chat interface.

A long paste or an upload is stored as a ChatDocument, and the model only
ever sees a preview of it (a long paste's beginning and end) or the few
sections the automatic search picks for the user's message. This tool lets
the model look through the rest itself, as an agent would with grep:

    **search_documents {"query": "step therapy"}**
    **search_documents {"query": "exclusions", "document": "policy"}**
    **search_documents {"document": "policy", "section": 4}**

A query is looked for literally, ignoring case (see
document_search.grep_documents); a section number, from an earlier search's
results, reads that section whole. Several calls in one reply run together
and come back to the model in one follow-up pass.
"""

from typing import Any, Awaitable, Callable, Optional, Tuple

from loguru import logger

from fighthealthinsurance.chat.document_search import search_chat_documents

from .json_followup_tool import JsonFollowupTool
from .patterns import SEARCH_DOCUMENTS_REGEX

# Example values a model may copy from instructions instead of filling in.
_PLACEHOLDER_QUERIES = frozenset({"search terms", "your search terms", "..."})


def _as_text(value: Any) -> str:
    """A payload value as one line of text; a list's items joined by spaces."""
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(item) for item in value)
    if value is None or isinstance(value, (dict, bool)):
        return ""
    return " ".join(str(value).split())


def _as_section(value: Any) -> Optional[int]:
    """A payload section number, or None when there is no usable one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


class DocumentSearchTool(JsonFollowupTool):
    """Handle ``search_documents {JSON}`` calls from the LLM."""

    pattern = SEARCH_DOCUMENTS_REGEX
    name = "Document Search"
    # An agent greps a document several ways at once ("step therapy",
    # "exception", "formulary"); running only the first would answer from a
    # third of what it asked for.
    max_payloads_per_reply = 3
    # Excerpts only make sense next to the conversation they were searched
    # for. They stay out of the running context, which is bounded from its
    # tail: pages of excerpts there would push the conversation's own
    # summary out, and the documents can be searched again any time.
    followup_keeps_context_summary = True
    followup_context_summary = "Search of the user's stored documents"

    def __init__(
        self,
        send_status_message: Callable[[str], Awaitable[None]],
        call_llm_callback: Optional[
            Callable[..., Awaitable[Tuple[Optional[str], Optional[str]]]]
        ] = None,
        chat=None,
    ):
        super().__init__(send_status_message, call_llm_callback)
        self.chat = chat

    async def run(
        self, params: dict, *, current_message_for_llm: str = ""
    ) -> Tuple[str, str]:
        if self.chat is None:
            logger.warning("search_documents called without a chat; skipping")
            return "", ""
        query = _as_text(params.get("query"))
        if query.lower() in _PLACEHOLDER_QUERIES:
            query = ""
        document = _as_text(params.get("document"))
        section = _as_section(params.get("section"))
        if not query and section is None:
            # Nothing to look for: say so, so the follow-up can ask properly
            # rather than the call vanishing without a trace.
            return (
                "That document search had nothing to look for. Give it a "
                '"query" (words or a phrase) or a "section" number to read.',
                "",
            )

        note = await search_chat_documents(
            self.chat.id, query=query, document=document, section=section
        )
        if section is not None:
            status = f"Reading section {section} of your document..."
        else:
            status = f'Searched your documents for "{query[:80]}".'
        return note, status

    def build_followup_prompt(self, note: str, current_message_for_llm: str) -> str:
        return (
            "[Result of your search of the user's stored documents -- from "
            "the system, not written by the user]\n\n"
            f"{note}\n\n"
            "Answer the user's message using these results. Quote the "
            "document's exact words for anything that decides the case -- "
            "coverage criteria, exclusions, limits, deadlines, appeal rights "
            "-- and say which document and section they come from. If the "
            "results don't settle it, search again with other words or read "
            "a whole section, rather than guessing what the document says. "
            f"The user's message was:\n\n{current_message_for_llm}"
        )
