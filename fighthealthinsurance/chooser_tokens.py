"""Opaque candidate references for the chooser's blind voting.

A chooser task's candidates are stored in generation order: the internal
model's draft first, the synthesized draft last. Their database ids run in
the same order, so a payload that carried ids (or candidate_index) told a
voter who opened the network tab which draft was which class of model,
however the drafts were shuffled on the page. The next-task endpoint
therefore hands out tokens instead: each is the candidate id encrypted
with a fresh random nonce (Fernet), so two tokens for the same candidate
differ, tokens do not sort, and only this server can read them back. The
vote endpoint resolves a token to its id; a plain integer is still
accepted there, for older clients and tests, since the request is not
where the blindness is.
"""

import base64
import hashlib
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_SALT = b"chooser-candidate-token:"


def _fernet() -> Fernet:
    secret = settings.SECRET_KEY
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    key = hashlib.sha256(_SALT + secret).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def candidate_token(candidate_id: int) -> str:
    """An opaque, single-presentation reference to ``candidate_id``."""
    return _fernet().encrypt(str(int(candidate_id)).encode("ascii")).decode("ascii")


def resolve_candidate(value: Any) -> Optional[int]:
    """The candidate id a token from candidate_token names; None for
    anything else, a plain id included. Ids are what the token hides, and
    an endpoint that took them back would let a client learn a token's id by
    guessing: the vote endpoint answers differently for an id in the task
    and one outside it."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(_fernet().decrypt(value.strip().encode("ascii")).decode("ascii"))
    except (InvalidToken, ValueError, UnicodeEncodeError):
        return None
