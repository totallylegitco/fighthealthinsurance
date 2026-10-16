"""A chat upload is never thrown away because the connection was down.

The chat reads a document on the person's device, then sends the text over
the chat's WebSocket. If that socket wasn't open when reading finished, the
document used to be dropped without a word: the "I've uploaded a document"
bubble and the spinner still appeared, but nothing was sent, and the
eventual Retry sent the bubble's own text instead of the document. With no
socket at all, picking a file did nothing.

Now the read document is kept, the person is told it hasn't gone, and Retry
sends it. Only one retry can be in flight at a time, so a double click or a
second Retry can't send the same turn again.

There is no JS test harness in this repo, so these read the source, like
``tests/async-unit/test_appeal_sends_what_was_edited.py``.
"""

import pathlib
import re

CHAT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "fighthealthinsurance"
    / "static"
    / "js"
    / "chat_interface.tsx"
)


def _source() -> str:
    return CHAT.read_text()


def _brace_block(src: str, open_at: int) -> str:
    assert src[open_at] == "{", src[open_at : open_at + 20]
    depth = 0
    for i in range(open_at, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_at : i + 1]
    raise AssertionError("unbalanced braces")


def _arrow_body(src: str, name: str) -> str:
    """The body of ``const name = ... => {`` (a useCallback wrapper too)."""
    heads = list(re.finditer(r"\bconst\s+" + re.escape(name) + r"\s*=", src))
    assert len(heads) == 1, f"expected one `const {name}`, found {len(heads)}"
    arrow = src.index("=>", heads[0].end())
    return _brace_block(src, src.index("{", arrow))


def _onclose_body(src: str) -> str:
    head = re.search(r"\bws\.onclose\s*=\s*\(\)\s*=>\s*\{", src)
    assert head is not None, "the socket no longer has an onclose handler"
    return _brace_block(src, head.end() - 1)


def test_an_upload_is_read_even_when_there_is_no_socket():
    body = _arrow_body(_source(), "handleFileUpload")
    assert "wsRef" not in body, (
        "the upload handler looks at the socket itself again, so it can skip "
        "or drop a document without going through sendUpload"
    )


def test_an_upload_that_cannot_send_is_kept_and_the_person_told():
    body = _arrow_body(_source(), "handleFileUpload")
    head = "if (!sendUpload(upload)) {"
    assert head in body, "nothing handles an upload the connection can't take"
    branch = _brace_block(body, body.index(head) + len(head) - 1)
    assert "unsentUploadRef.current = upload;" in branch, (
        "the read document is thrown away when it can't be sent"
    )
    assert re.search(r"error:\s*`[^`]*wasn't sent[^`]*Retry", branch), (
        "the person isn't told the document didn't send and that Retry sends it"
    )


def test_the_upload_shows_in_the_chat_only_after_it_is_sent():
    body = _arrow_body(_source(), "sendUpload")
    not_open = body.find("return false;")
    sent = body.find("wsRef.current.send(")
    bubble = body.find("I've uploaded a document")
    assert -1 < not_open < sent < bubble, (
        "the upload bubble and spinner can appear for a document that never went"
    )


def test_retry_sends_a_kept_upload_before_anything_else():
    body = _arrow_body(_source(), "handleRetryLastMessage")
    held = body.find("unsentUploadRef.current")
    sent = body.find("sendUpload(unsentUpload)")
    resend_text = body.find("sendChatMessage(")
    assert -1 < held < sent < resend_text, (
        "Retry resends the last message's text instead of the kept document"
    )


def test_retry_while_disconnected_says_so_instead_of_doing_nothing():
    body = _arrow_body(_source(), "handleRetryLastMessage")
    assert not re.search(r"if \(!wsRef\.current\) return;", body), (
        "Retry silently does nothing while the socket is gone"
    )


def test_a_second_retry_cannot_start_while_one_is_in_flight():
    body = _arrow_body(_source(), "handleRetryLastMessage")
    first_statement = re.search(r"\{\s*(?://[^\n]*\n\s*)*(?P<stmt>[^\n]+)", body)
    assert first_statement is not None
    assert first_statement.group("stmt").strip() == (
        "if (retryInFlightRef.current) return;"
    ), "Retry no longer refuses while a retry is still in flight"
    assert body.count("setRetryInFlight(true);") == 2, (
        "a retry that went out (document or message) isn't marked in flight"
    )


def test_a_retry_stops_counting_as_in_flight_when_its_turn_ends():
    src = _source()
    ends_with_turn = re.search(
        r"useEffect\(\(\) => \{\s*if \(!state\.isLoading\) \{\s*"
        r"setRetryInFlight\(false\);\s*\}\s*\}, \[state\.isLoading\]\);",
        src,
    )
    assert ends_with_turn is not None, (
        "a finished turn leaves Retry locked for the rest of the chat"
    )


def test_a_retry_stops_counting_as_in_flight_when_the_socket_closes():
    assert "setRetryInFlight(false);" in _onclose_body(_source()), (
        "a retry on a dead socket keeps Retry locked after the reconnect"
    )


def test_both_retry_buttons_show_a_retry_in_flight():
    buttons = [
        b
        for b in re.findall(r"<Button\b[\s\S]*?</Button>", _source())
        if "onClick={handleRetryLastMessage}" in b
    ]
    assert len(buttons) == 2, f"expected two Retry buttons, found {len(buttons)}"
    for button in buttons:
        assert "loading={retryInFlight}" in button, (
            "a Retry button looks ready while a retry is still in flight"
        )


def test_a_new_chat_drops_the_old_chats_unsent_upload():
    body = _arrow_body(_source(), "startNewChat")
    assert "unsentUploadRef.current = null;" in body, (
        "a new chat's Retry could send the previous chat's document"
    )
