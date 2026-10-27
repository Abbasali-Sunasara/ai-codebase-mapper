from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# Enable CORS for local frontend development (Vite runs on port 5173 typically)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "AI Codebase Mapper API is running", "status": "active"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}