from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, sessions, admin

app = FastAPI(
    title="LLM Consultant Advisor",
    description="API para análise de dados com LLM e busca por similaridade vetorial",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
