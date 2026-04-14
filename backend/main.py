"""Entry point for the FastAPI application — registers routers and starts the app."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import mongo
from app.routers import analysis, status


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongo.connect()
    yield
    await mongo.disconnect()


app = FastAPI(
    title="Customer Behavior Agent API",
    description="AI-powered e-commerce behavior analysis pipeline",
    version="0.1.0",
    lifespan=lifespan,
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
    return {"status": "ok"}
