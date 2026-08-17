from fastapi import FastAPI


def create_app() -> FastAPI:
    from app.api.auth import router as auth_router
    app = FastAPI(title="Rachel-v2 Web Platform")
    app.include_router(auth_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
