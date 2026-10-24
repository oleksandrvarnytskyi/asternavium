# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unversioned liveness endpoint for load balancers and monitors."""

from fastapi import APIRouter

from app.schemas.system import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> HealthResponse:
    """Report that the process is up."""
    return HealthResponse()
