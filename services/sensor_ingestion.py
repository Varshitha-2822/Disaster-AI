import json
import os
from datetime import datetime
from typing import Iterable, Optional

from database.db import db, SensorReading, AlertLog


def _parse_timestamp(value):
    if not value:
        return datetime.utcnow()
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


def _coerce_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def add_sensor_reading(payload: dict):
    if not payload:
        raise ValueError("Sensor payload is required.")

    sensor_id = str(payload.get("sensor_id") or "").strip()
    sensor_type = str(payload.get("type") or payload.get("sensor_type") or "").strip()
    value = _coerce_float(payload.get("value"))

    if not sensor_id or not sensor_type or value is None:
        raise ValueError("sensor_id, type, and value are required.")

    reading = SensorReading(
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        value=value,
        unit=payload.get("unit"),
        lat=_coerce_float(payload.get("lat")),
        lon=_coerce_float(payload.get("lon")),
        timestamp=_parse_timestamp(payload.get("timestamp")),
    )
    db.session.add(reading)
    db.session.commit()
    _log_sensor_alert(reading)
    return reading


def add_sensor_readings(items: Iterable[dict]):
    readings = []
    for payload in items:
        if not payload:
            continue
        try:
            readings.append(add_sensor_reading(payload))
        except ValueError:
            continue
    return readings


def list_latest_readings(limit_per_type: int = 1):
    readings = (
        SensorReading.query.order_by(SensorReading.timestamp.desc())
        .limit(500)
        .all()
    )
    latest = {}
    for reading in readings:
        if reading.sensor_type not in latest:
            latest[reading.sensor_type] = []
        if len(latest[reading.sensor_type]) < limit_per_type:
            latest[reading.sensor_type].append(reading)
    return latest


def list_recent_readings(sensor_type: Optional[str] = None, limit: int = 50):
    query = SensorReading.query
    if sensor_type:
        query = query.filter(SensorReading.sensor_type == sensor_type)
    rows = query.order_by(SensorReading.timestamp.desc()).limit(limit).all()
    return rows


def readings_to_dict(readings):
    return [
        {
            "sensor_id": r.sensor_id,
            "type": r.sensor_type,
            "value": r.value,
            "unit": r.unit,
            "lat": r.lat,
            "lon": r.lon,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in readings
    ]


def build_live_data_fallback():
    latest = list_latest_readings(limit_per_type=1)
    result = {}
    for sensor_type, readings in latest.items():
        if readings:
            result[sensor_type] = readings[0].value
    return result


def validate_ingest_token(request):
    token = os.getenv("SENSOR_INGEST_TOKEN")
    if not token:
        return True
    return request.headers.get("X-INGEST-TOKEN") == token


def _load_thresholds():
    raw = os.getenv("SENSOR_THRESHOLDS")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {
        "rainfall": {"warning": 100, "critical": 150},
        "river": {"warning": 7, "critical": 9},
        "soil": {"warning": 0.7, "critical": 0.85},
    }


def _log_sensor_alert(reading: SensorReading):
    thresholds = _load_thresholds()
    config = thresholds.get(reading.sensor_type)
    if not config:
        return
    level = None
    if reading.value >= config.get("critical", float("inf")):
        level = "critical"
    elif reading.value >= config.get("warning", float("inf")):
        level = "warning"
    if not level:
        return
    try:
        alert_log = AlertLog(
            recipient="system",
            status="sent",
            zones_affected=json.dumps([reading.sensor_id]),
            error_message=None,
            timestamp=datetime.utcnow(),
            zone="sensor-signal",
            risk=level,
        )
        db.session.add(alert_log)
        db.session.commit()
    except Exception:
        db.session.rollback()
