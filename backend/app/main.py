from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, analytics, auth, auth_xero, budget, coa, consolidation, dashboard, entities, health, ic_rules, pet_days, reports, scenarios, sync
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(sync.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_xero.router, prefix=settings.API_V1_PREFIX)
app.include_router(consolidation.router, prefix=settings.API_V1_PREFIX)
app.include_router(entities.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(budget.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)
app.include_router(scenarios.router, prefix=settings.API_V1_PREFIX)
app.include_router(coa.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX)
app.include_router(ic_rules.router, prefix=settings.API_V1_PREFIX)
app.include_router(pet_days.router, prefix=settings.API_V1_PREFIX)
