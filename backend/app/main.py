from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .alerts import send_meter_alerts
from .db import close_pool, open_pool
from .mqtt_client import MqttSubscriber
from .storage import build_intervals, database_ping, interval_history, latest_meters, recent_raw, refresh_meter_status

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    limit: int = Query(default=96, ge=1, le=500),
) -> dict:
    return {"intervals": interval_history(meter_id, limit)}


@app.get("/api/readings/recent")
def get_recent_readings(
    meter_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    return {"readings": recent_raw(meter_id, limit)}


@app.post("/api/intervals/rebuild")
def rebuild_intervals(hours_back: int = Query(default=24, ge=1, le=24 * 365)) -> dict:
    updated = build_intervals(hours_back)
    return {"updated": updated}
