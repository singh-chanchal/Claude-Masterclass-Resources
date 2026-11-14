import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.client import AIError
from app.config import get_settings
from app.database import init_db
from app.routers import applications, auth, dashboard, matches, resumes
from app.services.errors import BadRequest, NotFound

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HireTrack AI", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(BadRequest)
    async def _bad_request(_: Request, exc: BadRequest):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(AIError)
    async def _ai_error(_: Request, exc: AIError):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    for r in (auth.router, resumes.router, matches.router, applications.router, dashboard.router):
        app.include_router(r)

    @app.get("/api/health", tags=["meta"])
    def health():
        s = get_settings()
        return {"status": "ok", "ai_provider": s.ai_provider}

    return app


app = create_app()
