"""FastAPI entrypoint — the modular monolith (architecture §2)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import models  # noqa: F401 — register tables
from .agents import finance, hub, inbox, nutrition, orchestrator, stylist  # noqa: F401 — register agents
from .db import Base, engine
from .routers import auth as auth_router, interview as interview_router, finance as finance_router, inbox as inbox_router, nutrition as nutrition_router, screen, stylist as stylist_router, kernel as kernel_router, voice as voice_router, realtime as realtime_router, tasks as tasks_router, telegram as telegram_router, whatsapp as whatsapp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .config import assert_llm_configured, get_settings
    assert_llm_configured(get_settings())   # a stub brain never serves real mail
    # Dev convenience; real schema management is Alembic (`alembic upgrade head`).
    Base.metadata.create_all(bind=engine)
    try:  # auto-reply windows that were open when the process last stopped
        from .autosend import rearm_all
        rearm_all()
    except Exception:  # noqa: BLE001
        pass
    yield


app = FastAPI(title="Super App API", version="0.1.0", lifespan=lifespan)
app.include_router(screen.router)
app.include_router(nutrition_router.router)
app.include_router(finance_router.router)
app.include_router(stylist_router.router)
app.include_router(inbox_router.router)
app.include_router(auth_router.router)
app.include_router(interview_router.router)
app.include_router(kernel_router.router)
app.include_router(voice_router.router)
app.include_router(realtime_router.router)
app.include_router(tasks_router.router)
app.include_router(telegram_router.router)
app.include_router(whatsapp_router.router)


@app.get("/health")
def health():
    return {"ok": True}
