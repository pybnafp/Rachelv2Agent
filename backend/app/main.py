from contextlib import asynccontextmanager

from fastapi import FastAPI


def create_app() -> FastAPI:
    from app.api.auth import router as auth_router
    from app.api.admin import router as admin_router

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
                pass  # DB unreachable: app still boots; retry via deployed migration/seed
        try:
            import app.db.session as dbs
            from app.api.admin import seed_default_provider
            with dbs.SessionLocal() as session:
                seed_default_provider(session)
        except Exception:
            pass
        yield

    app = FastAPI(title="Rachel-v2 Web Platform", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(admin_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
