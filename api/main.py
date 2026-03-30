from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth, chat, oauth, sessions, sync, goals, insights, integrations, profile
from api.routers import stripe as stripe_router
from api.routers import user as user_router
from api.routers import workout_builder as workout_builder_router
from api.routers import manual_workout as manual_workout_router

load_dotenv()

app = FastAPI(title="Health Coach AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(sync.router)
app.include_router(goals.router)
app.include_router(insights.router)
app.include_router(integrations.router)
app.include_router(profile.router)
app.include_router(stripe_router.router)
app.include_router(user_router.router)
app.include_router(workout_builder_router.router)
app.include_router(manual_workout_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
