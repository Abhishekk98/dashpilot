"""FastAPI entry point. Run with: uvicorn app.main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import context, health, insights, llm, measures, model, projects
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # All API routes live under /api so the frontend can proxy a single prefix.
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(context.router, prefix="/api")
    app.include_router(model.router, prefix="/api")
    app.include_router(measures.router, prefix="/api")
    app.include_router(insights.router, prefix="/api")
    app.include_router(llm.router, prefix="/api")
    return app


app = create_app()
