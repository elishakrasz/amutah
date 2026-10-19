from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import dev, health
from app.settings import AuthBackend, get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Amutah Aid API", version="0.1.0")
    app.include_router(health.router, prefix="/api/v1")
    if settings.auth_backend is AuthBackend.LOCAL_DEV:
        app.include_router(dev.router, prefix="/api/v1")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    return app


app = create_app()
