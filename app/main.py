import logging

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .middleware import LoggingMiddleware
from .routers import alerts, dry_run, health, reset, routes, stats

logger = logging.getLogger("alerts_router")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI()

app.add_middleware(LoggingMiddleware)
app.include_router(health.router)
app.include_router(routes.router)
app.include_router(alerts.router)
app.include_router(dry_run.router)
app.include_router(stats.router)
app.include_router(reset.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content=jsonable_encoder({"error": exc.errors()}),
    )


@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request, exc):
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "database error"})


# @app.get("/")
# async def root():
#     return {"message": "Alert Router Service"}
