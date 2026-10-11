"""Aggregate API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    alerts,
    analytics,
    auth,
    finance,
    media,
    messaging,
    patients,
    schedules,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(patients.router)
api_router.include_router(finance.router)
api_router.include_router(schedules.router)
api_router.include_router(messaging.router)
api_router.include_router(media.router)
api_router.include_router(alerts.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
