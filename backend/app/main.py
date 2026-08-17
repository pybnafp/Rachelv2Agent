import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse


def create_app() -> FastAPI:
    from app.api.auth import router as auth_router
    from app.api.admin import router as admin_router
    from app.api.jobs import router as jobs_router

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.core.config import get_settings
        from app.db.base import Base
        import app.db.models  # register tables on Base
        settings = get_settings()
        if not settings.testing:
            try:
                import app.db.session as dbs
                dbs.init_engine()
                Base.metadata.create_all(dbs.engine)
            except Exception:
                logging.warning("DB init failed (app still boots); run migrations/seed later",
                                exc_info=True)
        try:
            import app.db.session as dbs
            from app.api.admin import seed_default_provider
            with dbs.SessionLocal() as session:
                seed_default_provider(session)
        except Exception:
            logging.warning("seed_default_provider failed; app continues without seed",
                            exc_info=True)
        yield

    app = FastAPI(title="Rachel-v2 Web Platform", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(jobs_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
