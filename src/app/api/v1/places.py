# SPDX-License-Identifier: AGPL-3.0-or-later
"""Birthplace search over the bundled GeoNames dataset."""

from http import HTTPStatus
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query

from app.api.deps import PlaceRepositoryDep, get_current_user
from app.api.responses import error_responses
from app.schemas.places import PlaceSearchResponse, PlaceSummary

QUERY_MIN_LENGTH: Final = 2
QUERY_MAX_LENGTH: Final = 100
DEFAULT_LIMIT: Final = 10
MAX_LIMIT: Final = 20

router = APIRouter(
    tags=["places"],
    dependencies=[Depends(get_current_user)],
    responses=error_responses(HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_CONTENT),
)


@router.get("/places")
def search_places(
    places: PlaceRepositoryDep,
    query: Annotated[
        str,
        Query(
            min_length=QUERY_MIN_LENGTH,
            max_length=QUERY_MAX_LENGTH,
            description="Start of the place name in any language, e.g. ``par`` or ``Київ``.",
        ),
    ],
    limit: Annotated[
        int, Query(ge=1, le=MAX_LIMIT, description="Maximum number of places to return.")
    ] = DEFAULT_LIMIT,
) -> PlaceSearchResponse:
    """Find birthplaces by name prefix, largest population first.

    A plain ``def``: the search is CPU-bound, so FastAPI runs it in the thread pool instead of
    blocking the event loop.
    """
    matches = places.search(query, limit=limit)
    return PlaceSearchResponse(items=[PlaceSummary.model_validate(place) for place in matches])
