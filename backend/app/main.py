from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.core.config import settings

app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    description="Deterministic AST code analysis paired with AI architectural summaries."
)

# Enable CORS for local React/Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include our analysis routes
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "AI Codebase Mapper Backend is running successfully!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
