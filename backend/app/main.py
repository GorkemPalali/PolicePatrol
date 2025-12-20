from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import api_router

settings = get_settings()

app = FastAPI(
    title="Predictive Patrol Routing System",
    description="Suç risk tahmini ve devriye rotası optimizasyonu sistemi",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "name": "Predictive Patrol Routing System",
        "version": "1.0.0",
        "status": "running"
    }
