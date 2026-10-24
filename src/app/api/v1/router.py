# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate router for ``/v1``."""

from fastapi import APIRouter

from app.api.v1 import about

router = APIRouter(prefix="/v1")
router.include_router(about.router)
