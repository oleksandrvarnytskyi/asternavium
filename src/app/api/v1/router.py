# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate router for ``/v1``."""

from fastapi import APIRouter

from app.api.v1 import about, me, persons, places, profile, sessions

router = APIRouter(prefix="/v1")
router.include_router(about.router)
router.include_router(places.router)
router.include_router(me.router)
router.include_router(profile.router)
router.include_router(persons.router)
router.include_router(sessions.router)
