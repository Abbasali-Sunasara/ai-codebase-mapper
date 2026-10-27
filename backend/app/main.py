from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router

app = FastAPI(
    title="AI Codebase Mapper API",
    version="1.0.0",
    description="Deterministic AST code analysis paired with AI architectural summaries."
)

# Enable CORS for local React/Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include our analysis routes
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "AI Codebase Mapper Backend is running successfully!"}