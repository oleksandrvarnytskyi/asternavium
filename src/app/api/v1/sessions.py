# SPDX-License-Identifier: AGPL-3.0-or-later
"""The caller's chat sessions and their message history."""

from http import HTTPStatus

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionServiceDep
from app.api.responses import error_responses
from app.api.v1.params import (
    DEFAULT_PAGE_SIZE,
    CursorQuery,
    LimitQuery,
    SessionIdPath,
)
from app.schemas.common import PageResponse
from app.schemas.sessions import (
    MessageResponse,
    SessionCreateRequest,
    SessionRenameRequest,
    SessionResponse,
)

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    responses=error_responses(
        HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_CONTENT, HTTPStatus.SERVICE_UNAVAILABLE
    ),
)


@router.post("", status_code=HTTPStatus.CREATED)
async def create_session(
    user: CurrentUserDep, sessions: SessionServiceDep, body: SessionCreateRequest
) -> SessionResponse:
    """Create an empty session.

    Temporary: removed in Phase 2, when sending the first chat message creates the session.
    """
    session = await sessions.create(user.user_id, module=body.module, title=body.title)
    return SessionResponse.model_validate(session)


@router.get("", responses=error_responses(HTTPStatus.BAD_REQUEST))
async def list_sessions(
    user: CurrentUserDep,
    sessions: SessionServiceDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PageResponse[SessionResponse]:
    """List your sessions, newest first."""
    page = await sessions.list_page(user.user_id, limit=limit, cursor=cursor)
    return PageResponse[SessionResponse](
        items=[SessionResponse.model_validate(session) for session in page.items],
        next_cursor=page.next_cursor,
    )


@router.patch("/{session_id}", responses=error_responses(HTTPStatus.NOT_FOUND))
async def rename_session(
    user: CurrentUserDep,
    sessions: SessionServiceDep,
    session_id: SessionIdPath,
    body: SessionRenameRequest,
) -> SessionResponse:
    """Rename one of your sessions."""
    session = await sessions.rename(user.user_id, session_id, title=body.title)
    return SessionResponse.model_validate(session)


@router.delete("/{session_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_session(
    user: CurrentUserDep, sessions: SessionServiceDep, session_id: SessionIdPath
) -> None:
    """Delete one of your sessions with all its messages.

    Idempotent: an ID you have no session with also returns ``204`` and changes nothing.
    """
    await sessions.delete(user.user_id, session_id)


@router.get(
    "/{session_id}/messages",
    responses=error_responses(HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND),
)
async def list_messages(
    user: CurrentUserDep,
    sessions: SessionServiceDep,
    session_id: SessionIdPath,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PageResponse[MessageResponse]:
    """List the messages of one of your sessions, newest first; empty until Phase 2."""
    page = await sessions.list_messages(user.user_id, session_id, limit=limit, cursor=cursor)
    return PageResponse[MessageResponse](
        items=[MessageResponse.model_validate(message) for message in page.items],
        next_cursor=page.next_cursor,
    )
