"""
Back-searching in large documents uploaded during chat.

Two ways in:

* Automatically: each turn, get_document_context_for_message lists the chat's
  stored documents and adds the sections that best match the user's message
  to the LLM context.
* On the model's request: the search_documents tool (chat/tools/
  document_search_tool.py) runs search_chat_documents, a grep-style search of
  the full stored text, or reads one section of it whole. A long paste or an
  upload is never in the model's context whole, so this is how the model
  finds what the rest of it says.

Section numbers are chunk_document's chunks, 1-based. Summarization stores
the same chunks' offsets, so a section number means the same text before and
after a document's analysis finishes.

The matching and passage ranking are document_grep's, shared with the appeal
flow's plan-document helper; what is here is the chat's side of it.
"""

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from loguru import logger

from fighthealthinsurance.chat.document_processor import chunk_document
from fighthealthinsurance.document_grep import (
    QUOTED_RE,
    STOPWORDS,
    WORD_RE,
    line_number,
    match_counts,
    passage_text,
    plural,
    query_needles,
    select_passages,
)
from fighthealthinsurance.models import ChatDocument

MAX_SEARCH_RESULTS = 5
MAX_CONTEXT_CHARS = 6000
MIN_QUERY_LENGTH = 3

# The listing's pointer to the search tool. No call syntax here: the system
# prompt documents the call, and a model echoing its context must not
# trigger a search.
DOCUMENT_LISTING_HEADER = (
    "Documents stored in this chat (you only ever see previews and excerpts "
    "of these -- search the full text with the search_documents tool before "
    "answering a question about what one says):"
)

# search_documents: the most passages one search returns, and the size of
# everything it returns.
MAX_TOOL_PASSAGES = 8
MAX_TOOL_RESULT_CHARS = 8000
# Longer than any real search. A model pasting a whole passage back as its
# query would otherwise get a phrase too long for any passage to fit.
MAX_TOOL_QUERY_CHARS = 300
# A passage's label ("[name, section N of M, line L]") and separators.
_PASSAGE_LABEL_CHARS = 80


def _extract_search_terms(query: str) -> List[str]:
    """Extract meaningful search terms from a user query."""
    words = WORD_RE.findall(query.lower())
    terms = [w for w in words if w not in STOPWORDS and len(w) >= MIN_QUERY_LENGTH]
    terms.extend(
        q.lower() for q in QUOTED_RE.findall(query) if len(q) >= MIN_QUERY_LENGTH
    )
    return terms


def _score_chunk(chunk_text: str, search_terms: List[str]) -> float:
    """Score a chunk by how well it matches the search terms.

    Uses simple term frequency with diminishing returns for repeated matches,
    normalized by query length so long questions don't artificially win.
    """
    if not search_terms or not chunk_text:
        return 0.0

    text_lower = chunk_text.lower()
    score = 0.0
    for term in search_terms:
        count = text_lower.count(term.lower())
        if count > 0:
            score += 1.0 + min(count - 1, 4) * 0.25

    return score / len(search_terms)


def _summary_preview_for_document(doc: ChatDocument, max_chars: int = 200) -> str:
    """Return stable summary preview text, with explicit status fallback."""
    if doc.summary:
        return doc.summary[:max_chars]
    return f"({doc.processing_status})"


async def get_document_context_for_message(
    chat_id,
    user_message: str,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_results: int = MAX_SEARCH_RESULTS,
) -> Optional[str]:
    """Build all document context (listing + relevant chunks) in a single pass.

    Returns None if the chat has no uploaded documents. A ``user_message``
    with no search terms (an empty one included) gets the listing only.

    Every section of every document is searched, analyzed or not: a long
    paste is analyzed only after its turn, so a follow-up question usually
    arrives before its analysis has finished.
    """
    if not await ChatDocument.objects.filter(chat_id=chat_id).aexists():
        return None

    search_terms = _extract_search_terms(user_message)

    documents = ChatDocument.objects.filter(chat_id=chat_id).order_by("created_at")

    summary_entries: List[str] = []
    scored_chunks: List[Dict] = []

    async for doc in documents.aiterator():
        sections = chunk_document(doc.full_text)
        summary_preview = _summary_preview_for_document(doc)
        summary_entries.append(
            f"- {doc.document_name} ({doc.char_count:,} chars, "
            f"{plural(len(sections), 'section')}, {doc.processing_status}): "
            f"{summary_preview}"
        )

        if not search_terms:
            continue

        for chunk in sections:
            score = _score_chunk(chunk["text"], search_terms)
            if score > 0:
                scored_chunks.append(
                    {
                        "score": score,
                        "document_name": doc.document_name,
                        "chunk_index": chunk["chunk_index"],
                        "text": chunk["text"],
                    }
                )

    parts: List[str] = []
    listing_budget = max_chars // 4
    if summary_entries:
        listing = "\n".join(summary_entries)
        if len(listing) > listing_budget:
            listing = listing[:listing_budget] + "..."
        parts.append(f"{DOCUMENT_LISTING_HEADER}\n{listing}")

    if scored_chunks:
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        formatted: List[str] = []
        total_chars = 0
        for chunk in scored_chunks[:max_results]:
            chunk_text = chunk["text"]
            if total_chars + len(chunk_text) > max_chars:
                remaining = max_chars - total_chars
                if remaining < 200:
                    break
                chunk_text = chunk_text[:remaining] + "..."
            header = f"[Document: {chunk['document_name']}, Section {chunk['chunk_index'] + 1}]"
            formatted.append(f"{header}\n{chunk_text}")
            total_chars += len(chunk_text) + len(header)

        if formatted:
            parts.append(
                "Relevant sections from uploaded documents:\n\n"
                + "\n\n---\n\n".join(formatted)
            )

    return "\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# The search_documents tool: grep-style search, and reading a section whole.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredDocument:
    """A stored document as the search tool sees it."""

    name: str
    text: str

    @property
    def sections(self) -> List[Dict]:
        return chunk_document(self.text)


def _section_number(sections: Sequence[Dict], pos: int) -> int:
    """1-based number of the first section holding character ``pos``."""
    for chunk in sections:
        if chunk["start_char"] <= pos < chunk["end_char"]:
            return int(chunk["chunk_index"]) + 1
    return len(sections)


def grep_documents(documents: Sequence[StoredDocument], query: str) -> str:
    """Search ``documents`` for ``query`` the way grep would, ranked.

    Returns, for the model: how often each part of the query occurs in each
    document, then the best-matching passages, best first, each labelled
    with its document, section and line so the model can quote it and read
    the whole section next.
    """
    query = query[:MAX_TOOL_QUERY_CHARS]
    needles = query_needles(query)
    if not needles:
        return (
            "That search was empty. Give the search a word or phrase to look "
            "for, or a section number to read."
        )
    shown_query = " ".join(query.split())
    lines = [f'Search of the stored documents for "{shown_query}":']
    found: set = set()
    section_lists = [doc.sections for doc in documents]
    for index, doc in enumerate(documents):
        counts = {
            label: count
            for label, count in match_counts(doc.text, needles).items()
            if count
        }
        found.update(counts)
        lines.append(
            f"- {doc.name} ({len(doc.text):,} chars, "
            f"{plural(len(section_lists[index]), 'section')}): "
            + (
                ", ".join(
                    f'"{label}" {plural(count, "time")}'
                    for label, count in counts.items()
                )
                or "no matches"
            )
        )

    if not found:
        lines.append(
            "Nothing matched. Search again with other words -- a synonym, the "
            "generic or brand name of a drug, a billing code, or the start of "
            'a word ("authoriz" finds every form of authorize) -- or read a '
            "section by its number."
        )
        return "\n".join(lines)

    missing = [n.label for n in needles if n.label not in found]
    if missing:
        lines.append(
            "Not found in any document: " + ", ".join(f'"{m}"' for m in missing)
        )
    lines.append("\nBest-matching passages, best first:")
    closing = (
        "\nThese are excerpts. To see more around one, read its whole section "
        "by number; to find more, search again with other words."
    )

    passages: List[str] = []
    for passage in select_passages(
        [doc.text for doc in documents],
        [query],
        budget_chars=MAX_TOOL_RESULT_CHARS - len("\n".join(lines)) - len(closing),
        max_passages=MAX_TOOL_PASSAGES,
        per_passage_overhead=_PASSAGE_LABEL_CHARS,
    ):
        doc = documents[passage.source]
        sections = section_lists[passage.source]
        passages.append(
            f"[{doc.name}, section {_section_number(sections, passage.hit)} of "
            f"{len(sections)}, line {line_number(doc.text, passage.hit):,}]\n"
            f"{passage_text(doc.text, passage)}"
        )

    lines.append("\n\n".join(passages))
    lines.append(closing)
    return "\n".join(lines)


def read_document_section(document: StoredDocument, number: int) -> str:
    """The whole text of section ``number`` (1-based) of ``document``."""
    sections = document.sections
    if not sections:
        return f"{document.name} is empty."
    if not 1 <= number <= len(sections):
        return (
            f"{document.name} has {plural(len(sections), 'section')} "
            f"(1-{len(sections)}); there is no section {number}."
        )
    chunk = sections[number - 1]
    text = chunk["text"]
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "…"
    return (
        f"Section {number} of {len(sections)} of {document.name} "
        f"(from line {line_number(document.text, chunk['start_char']):,}):\n"
        f"{text}"
    )


def _pick_documents(
    documents: Sequence[StoredDocument], name: str
) -> Tuple[List[StoredDocument], str]:
    """The documents whose names contain ``name`` (any case), or every
    document plus a note saying so when none does."""
    wanted = " ".join(name.lower().split())
    if not wanted:
        return list(documents), ""
    matching = [doc for doc in documents if wanted in doc.name.lower()]
    if matching:
        return matching, ""
    stored = ", ".join(doc.name for doc in documents)
    return list(documents), (
        f'No stored document is named like "{name[:200]}" (stored: {stored}), '
        f"so all of them were used.\n"
    )


async def _load_stored_documents(chat_id) -> List[StoredDocument]:
    """The chat's stored documents, oldest first.

    A document stored twice with identical text (a re-paste after its first
    copy's analysis was abandoned) is listed once, under its newest name, so
    a search does not return every passage twice.
    """
    by_digest: Dict[str, StoredDocument] = {}
    async for doc in (
        ChatDocument.objects.filter(chat_id=chat_id)
        .order_by("created_at", "id")
        .only("document_name", "full_text")
        .aiterator()
    ):
        text = doc.full_text or ""
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        by_digest[digest] = StoredDocument(name=doc.document_name, text=text)
    return list(by_digest.values())


async def search_chat_documents(
    chat_id,
    query: str = "",
    document: str = "",
    section: Optional[int] = None,
) -> str:
    """Run one search_documents call over a chat's stored documents.

    With ``section``, returns that section of the document named (the most
    recently stored one when no name is given or several match); otherwise
    greps every document named, or all of them, for ``query``. Always
    returns text for the model, including when there is nothing to search.
    """
    documents = await _load_stored_documents(chat_id)
    if not documents:
        return (
            "There are no documents stored in this chat: nothing the user "
            "pasted was long enough to be stored, and they have not uploaded "
            "one. If you need a document's text, ask them to paste or upload it."
        )
    picked, note = _pick_documents(documents, document)
    logger.info(
        f"search_documents in chat {chat_id}: {len(picked)} of "
        f"{len(documents)} documents, query_chars={len(query)}, "
        f"section={'yes' if section is not None else 'no'}"
    )
    if section is not None:
        target = picked[-1]
        if len(picked) > 1:
            note += (
                f"(Read from {target.name}, the most recently stored of "
                f"{len(picked)} documents; name another to read from it.)\n"
            )
        return note + read_document_section(target, section)
    return note + grep_documents(picked, query)
