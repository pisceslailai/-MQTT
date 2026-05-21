from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .alerts import send_meter_alerts
from .config import get_settings
from .db import close_pool, open_pool
from .gateway_config import (
    GatewayParseError,
    delete_gateway_config,
    delete_usr_r_data_mapping,
    ensure_gateway_config_schema,
    get_gateway_config,
    list_gateway_configs,
    list_usr_r_data_mappings,
    save_gateway_config,
    save_usr_r_data_mapping,
    test_gateway_config,
)
from .mqtt_client import MqttSubscriber
from .runtime_settings import ensure_runtime_settings_schema, get_runtime_settings, update_runtime_settings
from .storage import build_intervals, database_ping, interval_history, latest_meters, recent_payloads, recent_raw, refresh_meter_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

mqtt_subscriber: MqttSubscriber | None = None
background_task: asyncio.Task | None = None


async def background_loop() -> None:
    while True:
        try:
            refresh_meter_status()
            updated = build_intervals(hours_back=24)
            alerts = send_meter_alerts(latest_meters())
            logger.info("Refreshed interval readings: %s", updated)
            if alerts:
                logger.info("Sent alert notifications: %s", alerts)
        except Exception:
            logger.exception("Background refresh failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_subscriber, background_task
    open_pool()
    ensure_gateway_config_schema()
    ensure_runtime_settings_schema()
    mqtt_subscriber = MqttSubscriber()
    mqtt_subscriber.start()
    background_task = asyncio.create_task(background_loop())
    try:
        yield
    finally:
        if background_task:
            background_task.cancel()
        if mqtt_subscriber:
            mqtt_subscriber.stop()
        close_pool()


app = FastAPI(title="Flow Meter Monitor", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    db_ok = False
    try:
        db_ok = database_ping()
    except Exception:
        logger.exception("Database health check failed")
    mqtt_connected = bool(mqtt_subscriber and mqtt_subscriber.is_connected())
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "mqtt_connected": mqtt_connected,
    }


@app.get("/api/meters/latest")
def get_latest_meters() -> dict:
    return {"meters": latest_meters()}


@app.get("/api/intervals")
def get_intervals(
    meter_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    status: str | None = None,
    limit: int = Query(default=96, ge=1, le=500),
) -> dict:
    return {"intervals": interval_history(meter_id, limit, start, end, status)}


@app.get("/api/readings/recent")
def get_recent_readings(
    meter_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    return {"readings": recent_raw(meter_id, limit, start, end, status)}


@app.get("/api/readings/payloads")
def get_recent_payloads(
    meter_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    return {"payloads": recent_payloads(limit, meter_id)}


@app.post("/api/intervals/rebuild")
def rebuild_intervals(hours_back: int = Query(default=24, ge=1, le=24 * 365)) -> dict:
    updated = build_intervals(hours_back)
    return {"updated": updated}


@app.get("/api/gateway-configs")
def get_gateway_configs() -> dict:
    return {"configs": list_gateway_configs()}


@app.get("/api/gateway-configs/{config_id}")
def get_gateway_config_detail(config_id: int) -> dict:
    config = get_gateway_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="gateway config not found")
    return {"config": config}


@app.post("/api/gateway-configs")
def create_gateway_config(payload: dict) -> dict:
    try:
        return {"config": save_gateway_config(payload)}
    except GatewayParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/gateway-configs/{config_id}")
def update_gateway_config(config_id: int, payload: dict) -> dict:
    try:
        return {"config": save_gateway_config(payload, config_id=config_id)}
    except GatewayParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/gateway-configs/{config_id}")
def remove_gateway_config(config_id: int) -> dict:
    deleted = delete_gateway_config(config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="gateway config not found")
    return {"deleted": True}


@app.post("/api/gateway-configs/test")
def test_config(payload: dict) -> dict:
    try:
        return test_gateway_config(payload)
    except (GatewayParseError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/usr-r-data-mappings")
def get_usr_r_data_mappings() -> dict:
    return {"mappings": list_usr_r_data_mappings()}


@app.post("/api/usr-r-data-mappings")
def create_usr_r_data_mapping(payload: dict) -> dict:
    try:
        return {"mapping": save_usr_r_data_mapping(payload)}
    except GatewayParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/usr-r-data-mappings/{mapping_id}")
def update_usr_r_data_mapping(mapping_id: int, payload: dict) -> dict:
    try:
        return {"mapping": save_usr_r_data_mapping(payload, mapping_id=mapping_id)}
    except GatewayParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/usr-r-data-mappings/{mapping_id}")
def remove_usr_r_data_mapping(mapping_id: int) -> dict:
    deleted = delete_usr_r_data_mapping(mapping_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="USR r_data mapping not found")
    return {"deleted": True}


@app.get("/api/runtime-settings")
def get_settings_api() -> dict:
    return {"settings": get_runtime_settings()}


@app.put("/api/runtime-settings")
def update_settings_api(payload: dict) -> dict:
    try:
        return {"settings": update_runtime_settings(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
