"""
FastAPI Background Remover API
Main application entry point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import settings
from app.services.remover import BackgroundRemoverService
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global service instance
remover_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global remover_service
    
    # Startup
    logger.info("Starting Background Remover API...")
    try:
        remover_service = BackgroundRemoverService()
        await remover_service.initialize()
        app.state.remover_service = remover_service
        logger.info(f"API started successfully on model: {settings.REMBG_MODEL}")
    except Exception as e:
        logger.error(f"Failed to initialize remover service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Background Remover API...")
    if remover_service:
        await remover_service.cleanup()


# Create FastAPI app
app = FastAPI(
    title="Background Remover API",
    description="Remove backgrounds from images using rembg",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Background Remover API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False
    )