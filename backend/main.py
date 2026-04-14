"""Entry point for the FastAPI application — registers routers and starts the app."""

# TODO: add lifespan handler to initialise MongoDB and Qdrant connections on startup

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analysis, status

app = FastAPI(
    title="Customer Behavior Agent API",
    description="AI-powered e-commerce behavior analysis pipeline",
    version="0.1.0",
)

# TODO: tighten origins to the actual frontend URL in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
app.include_router(status.router, prefix="/analysis", tags=["status"])


@app.get("/health")
async def health_check():
    # TODO: include db connectivity checks
    return {"status": "ok"}
