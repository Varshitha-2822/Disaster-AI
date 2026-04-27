
from services.sensor_ingestion import build_live_data_fallback


def fetch_live_data():
    data = {"rainfall": 120, "river": 7, "soil": 0.8}
    live = build_live_data_fallback()
    for key in ("rainfall", "river", "soil"):
        if key in live and live[key] is not None:
            data[key] = live[key]
    return data
