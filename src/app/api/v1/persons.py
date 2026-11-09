# SPDX-License-Identifier: AGPL-3.0-or-later
"""The persons the caller makes charts for: themselves, relatives or clients."""

from http import HTTPStatus

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, PersonServiceDep
from app.api.responses import error_responses
from app.api.v1.params import DEFAULT_PAGE_SIZE, CursorQuery, LimitQuery, PersonIdPath
from app.schemas.common import PageResponse
from app.schemas.persons import PersonRequest, PersonResponse

router = APIRouter(
    prefix="/persons",
    tags=["persons"],
    responses=error_responses(
        HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_CONTENT, HTTPStatus.SERVICE_UNAVAILABLE
    ),
)


@router.post("", status_code=HTTPStatus.CREATED)
async def create_person(
    user: CurrentUserDep, persons: PersonServiceDep, body: PersonRequest
) -> PersonResponse:
    """Add a person with their birth data.

    The birthplace must come from GET /v1/places (``422 place_not_found`` otherwise). A local
    time skipped by a clock change, an ambiguous time without a choice, or a birth in the
    future is rejected with ``422 invalid_birth_data``.
    """
    person = await persons.create(user.user_id, label=body.label, birth=body.birth.to_birth_data())
    return PersonResponse.from_record(person)


@router.get("", responses=error_responses(HTTPStatus.BAD_REQUEST))
async def list_persons(
    user: CurrentUserDep,
    persons: PersonServiceDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PageResponse[PersonResponse]:
    """List your persons, newest first."""
    page = await persons.list_page(user.user_id, limit=limit, cursor=cursor)
    return PageResponse[PersonResponse](
        items=[PersonResponse.from_record(person) for person in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{person_id}", responses=error_responses(HTTPStatus.NOT_FOUND))
async def get_person(
    user: CurrentUserDep, persons: PersonServiceDep, person_id: PersonIdPath
) -> PersonResponse:
    """Read one of your persons."""
    return PersonResponse.from_record(await persons.get(user.user_id, person_id))


@router.put("/{person_id}", responses=error_responses(HTTPStatus.NOT_FOUND))
async def replace_person(
    user: CurrentUserDep,
    persons: PersonServiceDep,
    person_id: PersonIdPath,
    body: PersonRequest,
) -> PersonResponse:
    """Replace the label and birth data of one of your persons; validated as for POST."""
    person = await persons.replace(
        user.user_id, person_id, label=body.label, birth=body.birth.to_birth_data()
    )
    return PersonResponse.from_record(person)


@router.delete("/{person_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_person(
    user: CurrentUserDep, persons: PersonServiceDep, person_id: PersonIdPath
) -> None:
    """Delete one of your persons; clears your profile's ``owner_person_id`` if it named them.

    Idempotent: an ID you have no person with also returns ``204`` and changes nothing.
    """
    await persons.delete(user.user_id, person_id)
