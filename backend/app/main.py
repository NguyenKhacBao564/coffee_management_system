import logging
import logging.config

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import engine

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("nhu_tung.api")

app = FastAPI(title="Như Tùng · API", version="0.1.0")


@app.middleware("http")
async def no_store_for_api(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.middleware("http")
async def limit_scale_ingestion_request(request, call_next):
    if request.method == "POST" and request.url.path == "/api/scale-ingestion/batches":
        from fastapi.responses import JSONResponse

        max_bytes = settings.scale_ingestion_max_body_bytes
        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > max_bytes:
                return JSONResponse(status_code=413, content={"detail": {"code": "request_too_large", "message": "Batch vượt kích thước tối đa cho phép."}})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Content-Length không hợp lệ."})
        raw_body = await request.body()
        if len(raw_body) > max_bytes:
            return JSONResponse(status_code=413, content={"detail": {"code": "request_too_large", "message": "Batch vượt kích thước tối đa cho phép."}})
    return await call_next(request)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request, exc):
    logger.warning("Database request failed", extra={"path": request.url.path})
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=503, content={"detail": "Dịch vụ tạm thời chưa sẵn sàng."})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    from fastapi.responses import JSONResponse

    # Pydantic's default validation body includes raw input values. Omit them so
    # malformed credential requests are never echoed back to the browser.
    errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/api/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["health"])
def ready() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Database readiness check failed")
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail={"status": "not_ready"})
    return {"status": "ok"}


from app.modules.accounts.router import router as accounts_router

app.include_router(accounts_router)

from app.modules.trips.router import router as d02_router

app.include_router(d02_router)

from app.modules.scale_ingestion.router import router as scale_ingestion_router

app.include_router(scale_ingestion_router)

from app.modules.scale_ingestion.monitoring import router as scale_monitoring_router

app.include_router(scale_monitoring_router)

from app.modules.vehicle_pilot.router import router as vehicle_pilot_router

app.include_router(vehicle_pilot_router)

from app.modules.drum_processing.router import router as drum_processing_router

app.include_router(drum_processing_router)
