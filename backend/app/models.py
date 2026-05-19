from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MeterReading:
    meter_id: str
    device_ts: datetime
    instant_flow: float
    total_flow: float
    unit: str
    payload: dict[str, Any]
    topic: str
