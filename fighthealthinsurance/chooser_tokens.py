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
from typing import Any, Optional, Union

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


def resolve_candidate(value: Union[int, str, Any]) -> Optional[int]:
    """The candidate id ``value`` names: a token from candidate_token, or a
    plain integer (or its decimal string). None when it is neither."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.isdigit():
        return int(text)
    try:
        return int(_fernet().decrypt(text.encode("ascii")).decode("ascii"))
    except (InvalidToken, ValueError, UnicodeEncodeError):
        return None
