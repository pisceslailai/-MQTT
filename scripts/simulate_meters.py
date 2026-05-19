import argparse
from datetime import datetime, timedelta, timezone
import json
import random
import time

import paho.mqtt.client as mqtt


def publish_reading(client: mqtt.Client, meter_id: str, device_ts: datetime, total_flow: float) -> None:
    instant_flow = random.uniform(8.0, 18.0)
    payload = {
        "meter_id": meter_id,
        "device_ts": device_ts.isoformat(),
        "instant_flow": round(instant_flow, 3),
        "total_flow": round(total_flow, 3),
        "unit": "m3/h",
    }
    topic = f"meters/{meter_id}/reading"
    client.publish(topic, json.dumps(payload), qos=1)
    print(f"published {topic} {payload}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish simulated flow meter readings to MQTT.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between simulated readings.")
    parser.add_argument("--clock-skew-minutes", type=int, default=0)
    parser.add_argument("--offline-after", type=int, default=0, help="Stop after N publishes; 0 means never stop.")
    parser.add_argument("--backfill-minutes", type=int, default=0, help="Publish old device timestamps to simulate backfill.")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"simulator-{int(time.time())}")
    if args.username:
        client.username_pw_set(args.username, args.password or None)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    totals = {"FM001": 10000.0, "FM002": 20000.0}
    count = 0
    try:
        while True:
            count += 1
            now = datetime.now(timezone(timedelta(hours=8)))
            if args.backfill_minutes:
                now = now - timedelta(minutes=args.backfill_minutes)
            if args.clock_skew_minutes:
                now = now + timedelta(minutes=args.clock_skew_minutes)

            for meter_id in ("FM001", "FM002"):
                totals[meter_id] += random.uniform(0.1, 0.4)
                publish_reading(client, meter_id, now, totals[meter_id])

            if args.offline_after and count >= args.offline_after:
                print("offline-after reached; simulator exiting")
                break
            time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
