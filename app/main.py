"""FastAPI application for BoondManager CSV Importer."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.boond_client import get_boond_client
from app.models import ConnectionTestResponse
from app.routers import contracts, deliveries, orders, projects, purchases, resources

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="BoondManager CSV Importer",
    description="Import entities into BoondManager from CSV files",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Include routers
app.include_router(projects.router, prefix="/api")
app.include_router(deliveries.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(purchases.router, prefix="/api")
app.include_router(contracts.router, prefix="/api")
app.include_router(resources.router, prefix="/api")


@app.get("/")
async def root() -> FileResponse:
    """Serve the main HTML page."""
    return FileResponse(static_path / "index.html")


@app.get("/api/test-connection")
async def test_connection() -> ConnectionTestResponse:
    """Test connection to BoondManager API."""
    client = get_boond_client()
    success, message = await client.test_connection()
    return ConnectionTestResponse(success=success, message=message)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
