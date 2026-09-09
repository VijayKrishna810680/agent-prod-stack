"""Access control for the approval endpoint.

Problem this solves (flagged as an open gap in PROBLEMS_SOLVED.md): a trace_id tells
you *what* happened, not whether the person who approved a sensitive action was
allowed to. Approving a refund, a data change, or any agent action that touches a
real business system has to be gated on an authenticated identity, not a
self-reported `reviewer_id` in the request body.

This is a minimal bearer-token scheme so the scaffold stays runnable without a full
identity provider — swap `Settings.reviewer_api_keys` for a call to your real IdP
(Okta/Azure AD/etc.) and nothing else in this file changes.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.settings import get_settings


def require_reviewer(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: validates a bearer token and returns the reviewer's id.

    The caller can no longer claim to be any reviewer they like by putting a name in
    the JSON body — the identity is derived from a token only the org controls.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()
    reviewer_id = settings.reviewer_api_keys.get(token)

    if reviewer_id is None:
        raise HTTPException(status_code=403, detail="Unknown or revoked reviewer token")

    return reviewer_id
