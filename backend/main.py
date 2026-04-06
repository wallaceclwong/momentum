"""
FastAPI application for S&P 500 Momentum Screener API.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.scheduler import setup_scheduler
from backend.api.routes_screener import router as screener_router
from backend.api.routes_portfolio import router as portfolio_router
from backend.api.routes_sectors import router as sectors_router
from backend.api.routes_backtest import router as backtest_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="S&P 500 Momentum Screener API",
    description="API for momentum screening and portfolio tracking",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(screener_router, prefix="/api/screener", tags=["screener"])
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(sectors_router, prefix="/api/sectors", tags=["sectors"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["backtest"])


@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup."""
    logger.info("Starting up S&P 500 Momentum Screener API...")
    setup_scheduler()
    logger.info("Scheduler configured")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown."""
    logger.info("Shutting down S&P 500 Momentum Screener API...")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "S&P 500 Momentum Screener API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
