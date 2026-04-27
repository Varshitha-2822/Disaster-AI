import json
from collections import deque
from datetime import datetime

from database.db import db, TextRecord

TEXT_BUFFER = deque(maxlen=500)


def _to_json(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True)


def add_record(record):
    if not record:
        return None
    TEXT_BUFFER.append(record)
    extra = record.get("extra", {}) or {}
    for key in ("entities", "secondary_risks", "alert_level", "tweet_url", "type"):
        if key in record and key not in extra:
            extra[key] = record.get(key)
    model = TextRecord(
        source=record.get("source", "unknown"),
        text=record.get("text", ""),
        sentiment=record.get("sentiment", "neutral"),
        disaster_types=_to_json(record.get("disaster_types", [])),
        keywords=_to_json(record.get("keywords", [])),
        location_hints=_to_json(record.get("location_hints", [])),
        external_id=record.get("tweet_id") or record.get("external_id"),
        extra=_to_json(extra),
        created_at=datetime.utcnow(),
    )
    db.session.add(model)
    db.session.commit()
    return model


def add_records(records):
    if not records:
        return 0
    for record in records:
        TEXT_BUFFER.append(record)
        extra = record.get("extra", {}) or {}
        for key in ("entities", "secondary_risks", "alert_level", "tweet_url", "type"):
            if key in record and key not in extra:
                extra[key] = record.get(key)
        model = TextRecord(
            source=record.get("source", "unknown"),
            text=record.get("text", ""),
            sentiment=record.get("sentiment", "neutral"),
            disaster_types=_to_json(record.get("disaster_types", [])),
            keywords=_to_json(record.get("keywords", [])),
            location_hints=_to_json(record.get("location_hints", [])),
            external_id=record.get("tweet_id") or record.get("external_id"),
            extra=_to_json(extra),
            created_at=datetime.utcnow(),
        )
        db.session.add(model)
    db.session.commit()
    return len(records)


def list_records(limit=100):
    if limit <= 0:
        return []
    rows = (
        TextRecord.query.order_by(TextRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    records = []
    for row in rows:
        extra = json.loads(row.extra) if row.extra else {}
        records.append({
            "text": row.text,
            "source": row.source,
            "sentiment": row.sentiment,
            "disaster_types": json.loads(row.disaster_types) if row.disaster_types else [],
            "keywords": json.loads(row.keywords) if row.keywords else [],
            "location_hints": json.loads(row.location_hints) if row.location_hints else [],
            "external_id": row.external_id,
            "secondary_risks": extra.get("secondary_risks", []),
            "alert_level": extra.get("alert_level", "info"),
            "entities": extra.get("entities", []),
            "extra": extra,
            "timestamp": row.created_at.isoformat() if row.created_at else None,
        })
    return records


def clear_records():
    TEXT_BUFFER.clear()
    TextRecord.query.delete()
    db.session.commit()
