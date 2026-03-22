from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import chat, sessions, sync, goals, insights

load_dotenv()

app = FastAPI(title="Health Coach AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(sync.router)
app.include_router(goals.router)
app.include_router(insights.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
