from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from database.db import db, init_db, User, Stakeholder, SystemConfig, AlertLog, AlertLog
from models.risk_predictor import predict_risk
from services.data_fetcher import fetch_live_data
from services.text_ingestion import add_record, add_records, list_records
from services.sensor_ingestion import (
    add_sensor_reading,
    add_sensor_readings,
    list_latest_readings,
    list_recent_readings,
    readings_to_dict,
    validate_ingest_token,
)
from services.twitter_ingestion import fetch_recent_tweets, fetch_user_data
from models.text_analyzer import analyze_text, aggregate_text_signals
from utils.auth import admin_required, emergency_operator_required
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
import random
import csv
import io
from werkzeug.utils import secure_filename
import traceback
from PIL import Image
import numpy as np
import cv2
import torch
import timm
import torch.nn.functional as F
from torchvision import transforms
from gradcam import GradCAM


def _log_text_alert(record):
    level = record.get("alert_level")
    if level not in {"warning", "critical"}:
        return
    zones = record.get("location_hints", [])
    try:
        alert_log = AlertLog(
            recipient="system",
            status="sent",
            zones_affected=json.dumps(zones),
            error_message=None,
            timestamp=datetime.utcnow(),
            zone="text-signal",
            risk=level,
        )
        db.session.add(alert_log)
        db.session.commit()
    except Exception:
        db.session.rollback()

# Try to load GIS-processed data if available
try:
    import geopandas as gpd
    GIS_AVAILABLE = True
except ImportError:
    GIS_AVAILABLE = False

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Resolve all local resources from this app folder only.
APP_BASE_DIR = app.root_path
DATA_DIR = os.path.join(APP_BASE_DIR, "data")
MODELS_DIR = os.path.join(APP_BASE_DIR, "models")

# Add data directory to path
if DATA_DIR not in sys.path:
    sys.path.append(DATA_DIR)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    # Use SQLAlchemy 2.0 style: db.session.get() instead of Model.query.get()
    return db.session.get(User, int(user_id))

# Flask 3 FIX: Initialize DB manually
with app.app_context():
    init_db()

# Import complete India zones data - ALL STATES, DISTRICTS, AND AREAS
# This covers all 28 states, 8 union territories, and 664+ districts
try:
    # Import from data directory
    import importlib.util
    data_path = os.path.join(DATA_DIR, "complete_india_zones.py")
    spec = importlib.util.spec_from_file_location("complete_india_zones", data_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ZONES_DATA = module.COMPLETE_INDIA_ZONES
    print(f"Loaded {len(ZONES_DATA)} zones covering all of India")
except Exception as e:
    try:
        # Alternative: Direct import
        if DATA_DIR not in sys.path:
            sys.path.insert(0, DATA_DIR)
        from complete_india_zones import COMPLETE_INDIA_ZONES
        ZONES_DATA = COMPLETE_INDIA_ZONES
        print(f"Loaded {len(ZONES_DATA)} zones covering all of India")
    except Exception as e2:
        # Fallback: Generate zones if file doesn't exist
        from utils.generate_complete_india_zones import generate_complete_zones
        ZONES_DATA = generate_complete_zones()
        print(f"Generated {len(ZONES_DATA)} zones covering all of India")

# Add last_update to all zones if missing
for zone in ZONES_DATA:
    if 'last_update' not in zone:
        zone['last_update'] = datetime.now().isoformat()

# Legacy zone data (kept for reference only - not used, can be removed)
LEGACY_ZONES_DATA = [
    # ========== NORTHERN INDIA ==========
    
    # Jammu & Kashmir - Districts
    {"id": "jk_jammu", "name": "Jammu District", "coords": [[32.6, 74.5], [32.9, 74.5], [32.9, 75.0], [32.6, 75.0]], "risk_level": "HIGH", "risk_score": 0.75, "hospitals": 12, "schools": 85, "roads_km": 220, "population": 320000, "last_update": datetime.now().isoformat()},
    {"id": "jk_srinagar", "name": "Srinagar District", "coords": [[34.0, 74.7], [34.2, 74.7], [34.2, 75.0], [34.0, 75.0]], "risk_level": "SEVERE", "risk_score": 0.88, "hospitals": 18, "schools": 120, "roads_km": 280, "population": 450000, "last_update": datetime.now().isoformat()},
    {"id": "jk_anantnag", "name": "Anantnag District", "coords": [[33.6, 75.0], [33.9, 75.0], [33.9, 75.3], [33.6, 75.3]], "risk_level": "HIGH", "risk_score": 0.78, "hospitals": 8, "schools": 65, "roads_km": 180, "population": 280000, "last_update": datetime.now().isoformat()},
    {"id": "jk_baramulla", "name": "Baramulla District", "coords": [[34.1, 74.2], [34.4, 74.2], [34.4, 74.6], [34.1, 74.6]], "risk_level": "HIGH", "risk_score": 0.72, "hospitals": 7, "schools": 50, "roads_km": 170, "population": 200000, "last_update": datetime.now().isoformat()},
    
    # Punjab - Districts
    {"id": "pb_amritsar", "name": "Amritsar District", "coords": [[31.4, 74.7], [31.7, 74.7], [31.7, 75.1], [31.4, 75.1]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 25, "schools": 180, "roads_km": 450, "population": 650000, "last_update": datetime.now().isoformat()},
    {"id": "pb_ludhiana", "name": "Ludhiana District", "coords": [[30.7, 75.5], [31.0, 75.5], [31.0, 75.9], [30.7, 75.9]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 32, "schools": 220, "roads_km": 580, "population": 850000, "last_update": datetime.now().isoformat()},
    {"id": "pb_patiala", "name": "Patiala District", "coords": [[30.2, 76.2], [30.5, 76.2], [30.5, 76.6], [30.2, 76.6]], "risk_level": "MODERATE", "risk_score": 0.48, "hospitals": 18, "schools": 140, "roads_km": 420, "population": 520000, "last_update": datetime.now().isoformat()},
    {"id": "pb_jalandhar", "name": "Jalandhar District", "coords": [[31.2, 75.3], [31.5, 75.3], [31.5, 75.7], [31.2, 75.7]], "risk_level": "MODERATE", "risk_score": 0.50, "hospitals": 22, "schools": 165, "roads_km": 480, "population": 680000, "last_update": datetime.now().isoformat()},
    
    # Himachal Pradesh - Districts
    {"id": "hp_shimla", "name": "Shimla District", "coords": [[31.0, 77.0], [31.3, 77.0], [31.3, 77.4], [31.0, 77.4]], "risk_level": "HIGH", "risk_score": 0.72, "hospitals": 15, "schools": 95, "roads_km": 320, "population": 280000, "last_update": datetime.now().isoformat()},
    {"id": "hp_kangra", "name": "Kangra District", "coords": [[32.0, 76.0], [32.3, 76.0], [32.3, 76.4], [32.0, 76.4]], "risk_level": "HIGH", "risk_score": 0.68, "hospitals": 12, "schools": 85, "roads_km": 280, "population": 220000, "last_update": datetime.now().isoformat()},
    {"id": "hp_mandi", "name": "Mandi District", "coords": [[31.5, 76.8], [31.8, 76.8], [31.8, 77.2], [31.5, 77.2]], "risk_level": "HIGH", "risk_score": 0.70, "hospitals": 10, "schools": 72, "roads_km": 250, "population": 180000, "last_update": datetime.now().isoformat()},
    
    # Uttarakhand - Districts
    {"id": "uk_dehradun", "name": "Dehradun District", "coords": [[30.2, 77.8], [30.5, 77.8], [30.5, 78.2], [30.2, 78.2]], "risk_level": "SEVERE", "risk_score": 0.88, "hospitals": 28, "schools": 180, "roads_km": 520, "population": 450000, "last_update": datetime.now().isoformat()},
    {"id": "uk_haridwar", "name": "Haridwar District", "coords": [[29.7, 77.8], [30.0, 77.8], [30.0, 78.2], [29.7, 78.2]], "risk_level": "SEVERE", "risk_score": 0.92, "hospitals": 22, "schools": 150, "roads_km": 480, "population": 380000, "last_update": datetime.now().isoformat()},
    {"id": "uk_uttarkashi", "name": "Uttarkashi District", "coords": [[30.7, 78.2], [31.0, 78.2], [31.0, 78.6], [30.7, 78.6]], "risk_level": "SEVERE", "risk_score": 0.90, "hospitals": 8, "schools": 55, "roads_km": 180, "population": 120000, "last_update": datetime.now().isoformat()},
    {"id": "uk_chamoli", "name": "Chamoli District", "coords": [[30.3, 79.2], [30.6, 79.2], [30.6, 79.6], [30.3, 79.6]], "risk_level": "SEVERE", "risk_score": 0.85, "hospitals": 12, "schools": 75, "roads_km": 220, "population": 180000, "last_update": datetime.now().isoformat()},
    
    # Delhi NCR - Regions
    {"id": "delhi_central", "name": "Central Delhi", "coords": [[28.5, 77.1], [28.7, 77.1], [28.7, 77.3], [28.5, 77.3]], "risk_level": "MODERATE", "risk_score": 0.48, "hospitals": 85, "schools": 520, "roads_km": 1800, "population": 3200000, "last_update": datetime.now().isoformat()},
    {"id": "delhi_north", "name": "North Delhi", "coords": [[28.7, 77.1], [28.9, 77.1], [28.9, 77.3], [28.7, 77.3]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 95, "schools": 580, "roads_km": 2000, "population": 3800000, "last_update": datetime.now().isoformat()},
    {"id": "delhi_south", "name": "South Delhi", "coords": [[28.4, 77.1], [28.6, 77.1], [28.6, 77.3], [28.4, 77.3]], "risk_level": "LOW", "risk_score": 0.45, "hospitals": 78, "schools": 480, "roads_km": 1650, "population": 2800000, "last_update": datetime.now().isoformat()},
    {"id": "delhi_east", "name": "East Delhi", "coords": [[28.6, 77.2], [28.8, 77.2], [28.8, 77.4], [28.6, 77.4]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 92, "schools": 550, "roads_km": 1950, "population": 3500000, "last_update": datetime.now().isoformat()},
    {"id": "delhi_west", "name": "West Delhi", "coords": [[28.5, 76.9], [28.7, 76.9], [28.7, 77.1], [28.5, 77.1]], "risk_level": "MODERATE", "risk_score": 0.50, "hospitals": 100, "schools": 670, "roads_km": 2100, "population": 4200000, "last_update": datetime.now().isoformat()},
    
    # ========== EASTERN INDIA ==========
    
    # West Bengal - Districts
    {"id": "wb_kolkata", "name": "Kolkata District", "coords": [[22.4, 88.2], [22.7, 88.2], [22.7, 88.5], [22.4, 88.5]], "risk_level": "SEVERE", "risk_score": 0.90, "hospitals": 125, "schools": 850, "roads_km": 2800, "population": 4500000, "last_update": datetime.now().isoformat()},
    {"id": "wb_howrah", "name": "Howrah District", "coords": [[22.5, 88.1], [22.8, 88.1], [22.8, 88.4], [22.5, 88.4]], "risk_level": "SEVERE", "risk_score": 0.88, "hospitals": 45, "schools": 320, "roads_km": 1200, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "wb_north24", "name": "North 24 Parganas", "coords": [[22.6, 88.3], [22.9, 88.3], [22.9, 88.6], [22.6, 88.6]], "risk_level": "SEVERE", "risk_score": 0.85, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 3200000, "last_update": datetime.now().isoformat()},
    {"id": "wb_south24", "name": "South 24 Parganas", "coords": [[22.1, 88.2], [22.4, 88.2], [22.4, 88.5], [22.1, 88.5]], "risk_level": "SEVERE", "risk_score": 0.92, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 2800000, "last_update": datetime.now().isoformat()},
    {"id": "wb_murshidabad", "name": "Murshidabad District", "coords": [[24.0, 88.0], [24.3, 88.0], [24.3, 88.3], [24.0, 88.3]], "risk_level": "HIGH", "risk_score": 0.78, "hospitals": 28, "schools": 220, "roads_km": 680, "population": 850000, "last_update": datetime.now().isoformat()},
    {"id": "wb_malda", "name": "Malda District", "coords": [[24.8, 87.8], [25.1, 87.8], [25.1, 88.1], [24.8, 88.1]], "risk_level": "HIGH", "risk_score": 0.75, "hospitals": 22, "schools": 180, "roads_km": 580, "population": 720000, "last_update": datetime.now().isoformat()},
    
    # Bihar - Districts
    {"id": "bihar_patna", "name": "Patna District", "coords": [[25.4, 85.0], [25.7, 85.0], [25.7, 85.3], [25.4, 85.3]], "risk_level": "SEVERE", "risk_score": 0.95, "hospitals": 85, "schools": 620, "roads_km": 2200, "population": 3200000, "last_update": datetime.now().isoformat()},
    {"id": "bihar_muzaffarpur", "name": "Muzaffarpur District", "coords": [[26.0, 85.2], [26.3, 85.2], [26.3, 85.5], [26.0, 85.5]], "risk_level": "SEVERE", "risk_score": 0.90, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "bihar_darbhanga", "name": "Darbhanga District", "coords": [[26.1, 85.8], [26.4, 85.8], [26.4, 86.1], [26.1, 86.1]], "risk_level": "SEVERE", "risk_score": 0.88, "hospitals": 35, "schools": 280, "roads_km": 980, "population": 1500000, "last_update": datetime.now().isoformat()},
    {"id": "bihar_bhagalpur", "name": "Bhagalpur District", "coords": [[25.2, 86.8], [25.5, 86.8], [25.5, 87.1], [25.2, 87.1]], "risk_level": "SEVERE", "risk_score": 0.92, "hospitals": 38, "schools": 290, "roads_km": 1100, "population": 1600000, "last_update": datetime.now().isoformat()},
    {"id": "bihar_purnia", "name": "Purnia District", "coords": [[25.7, 87.2], [26.0, 87.2], [26.0, 87.5], [25.7, 87.5]], "risk_level": "HIGH", "risk_score": 0.82, "hospitals": 28, "schools": 220, "roads_km": 850, "population": 1200000, "last_update": datetime.now().isoformat()},
    {"id": "bihar_gaya", "name": "Gaya District", "coords": [[24.6, 84.8], [24.9, 84.8], [24.9, 85.1], [24.6, 85.1]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 32, "schools": 250, "roads_km": 920, "population": 1400000, "last_update": datetime.now().isoformat()},
    
    # Assam - Districts
    {"id": "assam_guwahati", "name": "Guwahati District", "coords": [[26.0, 91.5], [26.3, 91.5], [26.3, 91.8], [26.0, 91.8]], "risk_level": "SEVERE", "risk_score": 0.95, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2200000, "last_update": datetime.now().isoformat()},
    {"id": "assam_dibrugarh", "name": "Dibrugarh District", "coords": [[27.3, 94.5], [27.6, 94.5], [27.6, 94.8], [27.3, 94.8]], "risk_level": "SEVERE", "risk_score": 0.92, "hospitals": 28, "schools": 220, "roads_km": 850, "population": 850000, "last_update": datetime.now().isoformat()},
    {"id": "assam_jorhat", "name": "Jorhat District", "coords": [[26.7, 94.0], [27.0, 94.0], [27.0, 94.3], [26.7, 94.3]], "risk_level": "SEVERE", "risk_score": 0.90, "hospitals": 22, "schools": 180, "roads_km": 720, "population": 720000, "last_update": datetime.now().isoformat()},
    {"id": "assam_silchar", "name": "Silchar District", "coords": [[24.7, 92.7], [25.0, 92.7], [25.0, 93.0], [24.7, 93.0]], "risk_level": "HIGH", "risk_score": 0.85, "hospitals": 25, "schools": 200, "roads_km": 780, "population": 680000, "last_update": datetime.now().isoformat()},
    {"id": "assam_tezpur", "name": "Tezpur District", "coords": [[26.5, 92.5], [26.8, 92.5], [26.8, 92.8], [26.5, 92.8]], "risk_level": "HIGH", "risk_score": 0.80, "hospitals": 18, "schools": 150, "roads_km": 620, "population": 520000, "last_update": datetime.now().isoformat()},
    
    # Odisha - Districts
    {"id": "odisha_bhubaneswar", "name": "Bhubaneswar District", "coords": [[20.1, 85.5], [20.4, 85.5], [20.4, 85.8], [20.1, 85.8]], "risk_level": "HIGH", "risk_score": 0.78, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "odisha_cuttack", "name": "Cuttack District", "coords": [[20.3, 85.7], [20.6, 85.7], [20.6, 86.0], [20.3, 86.0]], "risk_level": "HIGH", "risk_score": 0.80, "hospitals": 42, "schools": 320, "roads_km": 1280, "population": 1500000, "last_update": datetime.now().isoformat()},
    {"id": "odisha_puri", "name": "Puri District", "coords": [[19.7, 85.5], [20.0, 85.5], [20.0, 85.8], [19.7, 85.8]], "risk_level": "MODERATE", "risk_score": 0.65, "hospitals": 28, "schools": 220, "roads_km": 850, "population": 980000, "last_update": datetime.now().isoformat()},
    {"id": "odisha_balasore", "name": "Balasore District", "coords": [[21.3, 86.7], [21.6, 86.7], [21.6, 87.0], [21.3, 87.0]], "risk_level": "HIGH", "risk_score": 0.75, "hospitals": 32, "schools": 250, "roads_km": 980, "population": 1200000, "last_update": datetime.now().isoformat()},
    
    # ========== CENTRAL INDIA ==========
    
    # Madhya Pradesh - Districts
    {"id": "mp_bhopal", "name": "Bhopal District", "coords": [[23.1, 77.3], [23.4, 77.3], [23.4, 77.6], [23.1, 77.6]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2200000, "last_update": datetime.now().isoformat()},
    {"id": "mp_indore", "name": "Indore District", "coords": [[22.6, 75.7], [22.9, 75.7], [22.9, 76.0], [22.6, 76.0]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 85, "schools": 620, "roads_km": 2200, "population": 3200000, "last_update": datetime.now().isoformat()},
    {"id": "mp_gwalior", "name": "Gwalior District", "coords": [[26.1, 78.0], [26.4, 78.0], [26.4, 78.3], [26.1, 78.3]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1500000, "last_update": datetime.now().isoformat()},
    {"id": "mp_jabalpur", "name": "Jabalpur District", "coords": [[23.1, 79.8], [23.4, 79.8], [23.4, 80.1], [23.1, 80.1]], "risk_level": "MODERATE", "risk_score": 0.60, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 1800000, "last_update": datetime.now().isoformat()},
    
    # Chhattisgarh - Districts
    {"id": "cg_raipur", "name": "Raipur District", "coords": [[21.1, 81.5], [21.4, 81.5], [21.4, 81.8], [21.1, 81.8]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 58, "schools": 420, "roads_km": 1600, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "cg_bilaspur", "name": "Bilaspur District", "coords": [[22.0, 82.0], [22.3, 82.0], [22.3, 82.3], [22.0, 82.3]], "risk_level": "MODERATE", "risk_score": 0.50, "hospitals": 32, "schools": 250, "roads_km": 980, "population": 980000, "last_update": datetime.now().isoformat()},
    
    # ========== WESTERN INDIA ==========
    
    # Maharashtra - Districts
    {"id": "mh_mumbai", "name": "Mumbai District", "coords": [[18.9, 72.7], [19.2, 72.7], [19.2, 73.0], [18.9, 73.0]], "risk_level": "HIGH", "risk_score": 0.75, "hospitals": 280, "schools": 1800, "roads_km": 5200, "population": 12000000, "last_update": datetime.now().isoformat()},
    {"id": "mh_pune", "name": "Pune District", "coords": [[18.4, 73.7], [18.7, 73.7], [18.7, 74.0], [18.4, 74.0]], "risk_level": "MODERATE", "risk_score": 0.65, "hospitals": 125, "schools": 850, "roads_km": 3200, "population": 4500000, "last_update": datetime.now().isoformat()},
    {"id": "mh_nashik", "name": "Nashik District", "coords": [[19.8, 73.5], [20.1, 73.5], [20.1, 73.8], [19.8, 73.8]], "risk_level": "MODERATE", "risk_score": 0.60, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2200000, "last_update": datetime.now().isoformat()},
    {"id": "mh_nagpur", "name": "Nagpur District", "coords": [[21.0, 79.0], [21.3, 79.0], [21.3, 79.3], [21.0, 79.3]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 85, "schools": 620, "roads_km": 2200, "population": 2800000, "last_update": datetime.now().isoformat()},
    {"id": "mh_aurangabad", "name": "Aurangabad District", "coords": [[19.7, 75.2], [20.0, 75.2], [20.0, 75.5], [19.7, 75.5]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "mh_kolhapur", "name": "Kolhapur District", "coords": [[16.5, 74.0], [16.8, 74.0], [16.8, 74.3], [16.5, 74.3]], "risk_level": "HIGH", "risk_score": 0.72, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1500000, "last_update": datetime.now().isoformat()},
    
    # Gujarat - Districts
    {"id": "guj_ahmedabad", "name": "Ahmedabad District", "coords": [[23.0, 72.4], [23.3, 72.4], [23.3, 72.7], [23.0, 72.7]], "risk_level": "MODERATE", "risk_score": 0.50, "hospitals": 125, "schools": 850, "roads_km": 3200, "population": 5500000, "last_update": datetime.now().isoformat()},
    {"id": "guj_surat", "name": "Surat District", "coords": [[21.1, 72.7], [21.4, 72.7], [21.4, 73.0], [21.1, 73.0]], "risk_level": "MODERATE", "risk_score": 0.48, "hospitals": 95, "schools": 680, "roads_km": 2800, "population": 4500000, "last_update": datetime.now().isoformat()},
    {"id": "guj_vadodara", "name": "Vadodara District", "coords": [[22.2, 73.1], [22.5, 73.1], [22.5, 73.4], [22.2, 73.4]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2800000, "last_update": datetime.now().isoformat()},
    {"id": "guj_rajkot", "name": "Rajkot District", "coords": [[22.2, 70.5], [22.5, 70.5], [22.5, 70.8], [22.2, 70.8]], "risk_level": "LOW", "risk_score": 0.40, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 2200000, "last_update": datetime.now().isoformat()},
    
    # Rajasthan - Districts
    {"id": "raj_jaipur", "name": "Jaipur District", "coords": [[26.8, 75.7], [27.1, 75.7], [27.1, 76.0], [26.8, 76.0]], "risk_level": "LOW", "risk_score": 0.35, "hospitals": 95, "schools": 680, "roads_km": 2800, "population": 3800000, "last_update": datetime.now().isoformat()},
    {"id": "raj_jodhpur", "name": "Jodhpur District", "coords": [[26.2, 72.8], [26.5, 72.8], [26.5, 73.1], [26.2, 73.1]], "risk_level": "LOW", "risk_score": 0.30, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "raj_udaipur", "name": "Udaipur District", "coords": [[24.4, 73.6], [24.7, 73.6], [24.7, 73.9], [24.4, 73.9]], "risk_level": "LOW", "risk_score": 0.32, "hospitals": 35, "schools": 280, "roads_km": 980, "population": 1200000, "last_update": datetime.now().isoformat()},
    
    # ========== SOUTHERN INDIA ==========
    
    # Karnataka - Districts
    {"id": "ka_bangalore", "name": "Bangalore District", "coords": [[12.8, 77.4], [13.1, 77.4], [13.1, 77.7], [12.8, 77.7]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 185, "schools": 1200, "roads_km": 4200, "population": 8500000, "last_update": datetime.now().isoformat()},
    {"id": "ka_mysore", "name": "Mysore District", "coords": [[12.2, 76.5], [12.5, 76.5], [12.5, 76.8], [12.2, 76.8]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2200000, "last_update": datetime.now().isoformat()},
    {"id": "ka_mangalore", "name": "Mangalore District", "coords": [[12.8, 74.7], [13.1, 74.7], [13.1, 75.0], [12.8, 75.0]], "risk_level": "HIGH", "risk_score": 0.72, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "ka_hubli", "name": "Hubli District", "coords": [[15.2, 75.0], [15.5, 75.0], [15.5, 75.3], [15.2, 75.3]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1500000, "last_update": datetime.now().isoformat()},
    
    # Kerala - Districts
    {"id": "kl_kochi", "name": "Kochi District", "coords": [[9.8, 76.1], [10.1, 76.1], [10.1, 76.4], [9.8, 76.4]], "risk_level": "HIGH", "risk_score": 0.82, "hospitals": 85, "schools": 620, "roads_km": 2200, "population": 3200000, "last_update": datetime.now().isoformat()},
    {"id": "kl_thiruvananthapuram", "name": "Thiruvananthapuram District", "coords": [[8.4, 76.8], [8.7, 76.8], [8.7, 77.1], [8.4, 77.1]], "risk_level": "HIGH", "risk_score": 0.78, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2800000, "last_update": datetime.now().isoformat()},
    {"id": "kl_kozhikode", "name": "Kozhikode District", "coords": [[11.1, 75.7], [11.4, 75.7], [11.4, 76.0], [11.1, 76.0]], "risk_level": "HIGH", "risk_score": 0.80, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 2200000, "last_update": datetime.now().isoformat()},
    {"id": "kl_thrissur", "name": "Thrissur District", "coords": [[10.4, 76.1], [10.7, 76.1], [10.7, 76.4], [10.4, 76.4]], "risk_level": "HIGH", "risk_score": 0.75, "hospitals": 48, "schools": 350, "roads_km": 1280, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "kl_alappuzha", "name": "Alappuzha District", "coords": [[9.4, 76.3], [9.7, 76.3], [9.7, 76.6], [9.4, 76.6]], "risk_level": "SEVERE", "risk_score": 0.88, "hospitals": 38, "schools": 280, "roads_km": 980, "population": 1500000, "last_update": datetime.now().isoformat()},
    
    # Tamil Nadu - Districts
    {"id": "tn_chennai", "name": "Chennai District", "coords": [[13.0, 80.1], [13.3, 80.1], [13.3, 80.4], [13.0, 80.4]], "risk_level": "HIGH", "risk_score": 0.78, "hospitals": 185, "schools": 1200, "roads_km": 4200, "population": 8500000, "last_update": datetime.now().isoformat()},
    {"id": "tn_coimbatore", "name": "Coimbatore District", "coords": [[11.0, 76.9], [11.3, 76.9], [11.3, 77.2], [11.0, 77.2]], "risk_level": "MODERATE", "risk_score": 0.65, "hospitals": 95, "schools": 680, "roads_km": 2800, "population": 4200000, "last_update": datetime.now().isoformat()},
    {"id": "tn_madurai", "name": "Madurai District", "coords": [[9.8, 78.0], [10.1, 78.0], [10.1, 78.3], [9.8, 78.3]], "risk_level": "MODERATE", "risk_score": 0.60, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 2800000, "last_update": datetime.now().isoformat()},
    {"id": "tn_tiruchirappalli", "name": "Tiruchirappalli District", "coords": [[10.7, 78.6], [11.0, 78.6], [11.0, 78.9], [10.7, 78.9]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 2200000, "last_update": datetime.now().isoformat()},
    {"id": "tn_salem", "name": "Salem District", "coords": [[11.6, 78.0], [11.9, 78.0], [11.9, 78.3], [11.6, 78.3]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1800000, "last_update": datetime.now().isoformat()},
    
    # Andhra Pradesh - Districts
    {"id": "ap_hyderabad", "name": "Hyderabad District", "coords": [[17.3, 78.3], [17.6, 78.3], [17.6, 78.6], [17.3, 78.6]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 125, "schools": 850, "roads_km": 3200, "population": 6800000, "last_update": datetime.now().isoformat()},
    {"id": "ap_visakhapatnam", "name": "Visakhapatnam District", "coords": [[17.6, 83.2], [17.9, 83.2], [17.9, 83.5], [17.6, 83.5]], "risk_level": "HIGH", "risk_score": 0.75, "hospitals": 85, "schools": 620, "roads_km": 2200, "population": 4200000, "last_update": datetime.now().isoformat()},
    {"id": "ap_vijayawada", "name": "Vijayawada District", "coords": [[16.4, 80.5], [16.7, 80.5], [16.7, 80.8], [16.4, 80.8]], "risk_level": "HIGH", "risk_score": 0.78, "hospitals": 68, "schools": 480, "roads_km": 1800, "population": 3200000, "last_update": datetime.now().isoformat()},
    {"id": "ap_guntur", "name": "Guntur District", "coords": [[16.2, 80.3], [16.5, 80.3], [16.5, 80.6], [16.2, 80.6]], "risk_level": "HIGH", "risk_score": 0.72, "hospitals": 52, "schools": 380, "roads_km": 1500, "population": 2800000, "last_update": datetime.now().isoformat()},
    
    # Telangana - Districts
    {"id": "tel_hyderabad", "name": "Hyderabad District", "coords": [[17.3, 78.3], [17.6, 78.3], [17.6, 78.6], [17.3, 78.6]], "risk_level": "MODERATE", "risk_score": 0.55, "hospitals": 95, "schools": 680, "roads_km": 2800, "population": 5200000, "last_update": datetime.now().isoformat()},
    {"id": "tel_warangal", "name": "Warangal District", "coords": [[17.9, 79.5], [18.2, 79.5], [18.2, 79.8], [17.9, 79.8]], "risk_level": "MODERATE", "risk_score": 0.58, "hospitals": 42, "schools": 320, "roads_km": 1200, "population": 1800000, "last_update": datetime.now().isoformat()},
    {"id": "tel_karimnagar", "name": "Karimnagar District", "coords": [[18.3, 79.0], [18.6, 79.0], [18.6, 79.3], [18.3, 79.3]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 35, "schools": 280, "roads_km": 980, "population": 1500000, "last_update": datetime.now().isoformat()},
    
    # ========== NORTHEASTERN INDIA ==========
    
    # Manipur
    {"id": "manipur_imphal", "name": "Imphal District", "coords": [[24.7, 93.8], [25.0, 93.8], [25.0, 94.1], [24.7, 94.1]], "risk_level": "HIGH", "risk_score": 0.80, "hospitals": 18, "schools": 120, "roads_km": 420, "population": 450000, "last_update": datetime.now().isoformat()},
    
    # Meghalaya
    {"id": "meghalaya_shillong", "name": "Shillong District", "coords": [[25.4, 91.7], [25.7, 91.7], [25.7, 92.0], [25.4, 92.0]], "risk_level": "HIGH", "risk_score": 0.85, "hospitals": 15, "schools": 95, "roads_km": 380, "population": 380000, "last_update": datetime.now().isoformat()},
    
    # Tripura
    {"id": "tripura_agartala", "name": "Agartala District", "coords": [[23.7, 91.2], [24.0, 91.2], [24.0, 91.5], [23.7, 91.5]], "risk_level": "MODERATE", "risk_score": 0.60, "hospitals": 12, "schools": 85, "roads_km": 320, "population": 420000, "last_update": datetime.now().isoformat()},
    
    # ========== COASTAL REGIONS ==========
    
    # Goa
    {"id": "goa_north", "name": "North Goa", "coords": [[15.4, 73.7], [15.7, 73.7], [15.7, 74.0], [15.4, 74.0]], "risk_level": "MODERATE", "risk_score": 0.52, "hospitals": 22, "schools": 180, "roads_km": 680, "population": 850000, "last_update": datetime.now().isoformat()},
    {"id": "goa_south", "name": "South Goa", "coords": [[15.1, 73.9], [15.4, 73.9], [15.4, 74.2], [15.1, 74.2]], "risk_level": "MODERATE", "risk_score": 0.50, "hospitals": 20, "schools": 200, "roads_km": 720, "population": 650000, "last_update": datetime.now().isoformat()},
]  # Legacy data - not used, ZONES_DATA above contains complete dataset



# ML Classification configuration
ML_DEVICE = torch.device("cpu")
ML_CLASS_NAMES = ["cyclone", "earthquake", "flood", "wildfire"]
ML_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ML_MODEL_DIR = os.path.join(MODELS_DIR, "ML_Models")
ML_MODEL_FILE = "efficientnet_b0.pth"
ML_MODEL = None
ML_TRANSFORM = None
ML_READY = False
ML_ERROR = None

app.config["ML_UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads")
app.config["ML_HEATMAP_FOLDER"] = os.path.join(app.static_folder, "heatmap")
app.config["ML_OVERLAY_FOLDER"] = os.path.join(app.static_folder, "overlay")

for folder in [app.config["ML_UPLOAD_FOLDER"], app.config["ML_HEATMAP_FOLDER"], app.config["ML_OVERLAY_FOLDER"]]:
    os.makedirs(folder, exist_ok=True)


def _initialize_ml_classifier():
    """Load image classification model once at startup."""
    global ML_MODEL, ML_TRANSFORM, ML_READY, ML_ERROR

    try:
        model_path = os.path.join(ML_MODEL_DIR, ML_MODEL_FILE)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at {model_path}")

        ML_MODEL = timm.create_model("efficientnet_b0", pretrained=False, num_classes=len(ML_CLASS_NAMES)).to(ML_DEVICE)
        ML_MODEL.load_state_dict(torch.load(model_path, map_location=ML_DEVICE))
        ML_MODEL.eval()

        ML_TRANSFORM = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
        ])

        ML_READY = True
        ML_ERROR = None
        print("ML classifier initialized successfully")
    except Exception as exc:
        ML_READY = False
        ML_ERROR = str(exc)
        print(f"Warning: ML classifier is unavailable: {ML_ERROR}")


def _predict_image(img_tensor):
    with torch.no_grad():
        output = ML_MODEL(img_tensor)
        probs = F.softmax(output, dim=1)
        conf, pred = torch.max(probs, dim=1)
    return ML_CLASS_NAMES[pred.item()], conf.item(), pred.item()


def _apply_gradcam(image_path, class_idx):
    gradcam = GradCAM(ML_MODEL, ML_MODEL.conv_head)

    img = Image.open(image_path).convert("RGB")
    img_tensor = ML_TRANSFORM(img).unsqueeze(0).to(ML_DEVICE)

    cam = gradcam.generate_cam(img_tensor, class_idx)
    cam = cv2.resize(cam, (img.size[0], img.size[1]))
    heatmap = cv2.applyColorMap(np.uint8(255 * cam), cv2.COLORMAP_JET)

    img_np = np.array(img)
    overlay = 0.4 * heatmap + 0.6 * img_np

    return heatmap, overlay.astype(np.uint8)


def _run_classification(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Please select an image file.")

    safe_name = secure_filename(file_storage.filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ML_ALLOWED_EXTENSIONS:
        raise ValueError("Only JPG, JPEG, and PNG files are supported.")

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    base_name = f"{stamp}_{safe_name}"

    upload_abs = os.path.join(app.config["ML_UPLOAD_FOLDER"], base_name)
    file_storage.save(upload_abs)

    img = Image.open(upload_abs).convert("RGB")
    img_tensor = ML_TRANSFORM(img).unsqueeze(0).to(ML_DEVICE)
    label, confidence, class_idx = _predict_image(img_tensor)

    heatmap, overlay = _apply_gradcam(upload_abs, class_idx)

    heatmap_name = f"heatmap_{base_name}"
    overlay_name = f"overlay_{base_name}"

    heatmap_abs = os.path.join(app.config["ML_HEATMAP_FOLDER"], heatmap_name)
    overlay_abs = os.path.join(app.config["ML_OVERLAY_FOLDER"], overlay_name)

    cv2.imwrite(heatmap_abs, heatmap)
    cv2.imwrite(overlay_abs, overlay)

    return {
        "label": label,
        "confidence": confidence,
        "uploaded_image": url_for("static", filename=f"uploads/{base_name}"),
        "heatmap_image": url_for("static", filename=f"heatmap/{heatmap_name}"),
        "overlay_image": url_for("static", filename=f"overlay/{overlay_name}"),
    }


_initialize_ml_classifier()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/classify", methods=["GET", "POST"])
@login_required
def classify():
    if request.method == "POST":
        if not ML_READY:
            flash(f"ML service unavailable: {ML_ERROR}", "error")
            return render_template(
                "classifier_home.html",
                mode="user",
                submit_endpoint="classify",
                ml_ready=ML_READY,
                ml_error=ML_ERROR,
            )

        try:
            result = _run_classification(request.files.get("image"))
            return render_template(
                "classifier_result.html",
                mode="user",
                submit_endpoint="classify",
                **result,
            )
        except Exception as exc:
            flash(str(exc), "error")

    return render_template(
        "classifier_home.html",
        mode="user",
        submit_endpoint="classify",
        ml_ready=ML_READY,
        ml_error=ML_ERROR,
    )

@app.route("/admin/classify", methods=["GET", "POST"])
@admin_required
def admin_classify():
    """Admin ML image classification route."""
    if request.method == "POST":
        if not ML_READY:
            flash(f"ML service unavailable: {ML_ERROR}", "error")
            return render_template(
                "classifier_home.html",
                mode="admin",
                submit_endpoint="admin_classify",
                ml_ready=ML_READY,
                ml_error=ML_ERROR,
            )

        try:
            result = _run_classification(request.files.get("image"))
            return render_template(
                "classifier_result.html",
                mode="admin",
                submit_endpoint="admin_classify",
                **result,
            )
        except Exception as exc:
            flash(str(exc), "error")

    return render_template(
        "classifier_home.html",
        mode="admin",
        submit_endpoint="admin_classify",
        ml_ready=ML_READY,
        ml_error=ML_ERROR,
    )

@app.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard - requires login"""
    return render_template("dashboard.html", user=current_user)

@app.route("/login", methods=['GET', 'POST'])
def login():
    """User login page"""
    # if current_user.is_authenticated:
    #     return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password.', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        # Debug logging for troubleshooting
        if not user:
            flash('Invalid username or password.', 'error')
            print(f"ERROR: Login failed: User '{username}' not found in database")
        elif not user.active:
            flash('Your account has been deactivated. Please contact an administrator.', 'error')
            print(f"ERROR: Login failed: User '{username}' is inactive")
        elif not user.check_password(password):
            flash('Invalid username or password.', 'error')
            print(f"ERROR: Login failed: Incorrect password for user '{username}'")
            print(f"   User exists: {user.username}, Role: {user.role}, Active: {user.active}")
        else:
            # Successful login
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            flash(f'Welcome back, {user.username}!', 'success')
            print(f"Successful login: {user.username} (role: {user.role})")
            return redirect(url_for('classify'))
    
    return render_template('login.html')

@app.route("/register", methods=['GET', 'POST'])
def register():
    """User registration page"""
    # if current_user.is_authenticated:
    #     return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role', 'viewer')
        
        # Validation
        if not all([username, email, password, confirm_password]):
            flash('Please fill in all fields.', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html')
        
        # Validate role - prevent admin self-registration for security
        valid_roles = ['viewer', 'emergency_operator']
        if role not in valid_roles:
            flash('Invalid role selected. Please choose a valid account type.', 'error')
            return render_template('register.html')
        
        # Security: Prevent admin role registration through public signup
        if role == 'admin':
            flash('Admin accounts cannot be created through self-registration. Please contact an administrator.', 'error')
            return render_template('register.html')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html')
        
        # Create new user with selected role
        new_user = User(
            username=username,
            email=email,
            role=role,
            active=True
        )
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            
            role_display = role.replace('_', ' ').title()
            flash(f'Registration successful! Your account type is: {role_display}. Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'error')
            print(f"Registration error: {e}")
    
    return render_template('register.html')

@app.route("/logout")
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route("/api/zones")
@login_required
def api_zones():
    """Get all zones with current risk data"""
    live_data = fetch_live_data()
    zones_with_live = []
    for zone in ZONES_DATA:
        # Calculate live risk score based on current conditions
        features = [live_data.get("rainfall", 120), live_data.get("river", 7), live_data.get("soil", 0.8)]
        risk_level, risk_score = predict_risk(features)
        
        # Combine static and live risk
        combined_score = (zone["risk_score"] * 0.6 + risk_score * 0.4)
        if combined_score >= 0.8:
            final_level = "SEVERE"
        elif combined_score >= 0.6:
            final_level = "HIGH"
        elif combined_score >= 0.4:
            final_level = "MODERATE"
        else:
            final_level = "LOW"
        
        zone_copy = zone.copy()
        zone_copy["live_risk_score"] = round(combined_score, 3)
        zone_copy["live_risk_level"] = final_level
        zone_copy["rainfall"] = live_data.get("rainfall", 0)
        zone_copy["river_level"] = live_data.get("river", 0)
        zone_copy["soil_moisture"] = live_data.get("soil", 0)
        zones_with_live.append(zone_copy)
    
    return jsonify({"zones": zones_with_live})

@app.route("/api/risk")
@login_required
def api_risk():
    """Get overall risk assessment"""
    live_data = fetch_live_data()
    features = [live_data.get("rainfall", 120), live_data.get("river", 7), live_data.get("soil", 0.8)]
    risk, score = predict_risk(features)
    return jsonify({
        "risk": risk,
        "score": round(score, 3),
        "confidence": round(score * 100, 1),
        "rainfall": live_data.get("rainfall", 0),
        "river_level": live_data.get("river", 0),
        "soil_moisture": round(live_data.get("soil", 0), 2),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/vulnerability")
@login_required
def api_vulnerability():
    """Get vulnerability summary across all zones"""
    total_hospitals = sum(z["hospitals"] for z in ZONES_DATA)
    total_schools = sum(z["schools"] for z in ZONES_DATA)
    total_roads = sum(z["roads_km"] for z in ZONES_DATA)
    total_population = sum(z["population"] for z in ZONES_DATA)
    
    high_risk_zones = [z for z in ZONES_DATA if z["risk_score"] >= 0.6]
    
    return jsonify({
        "total_hospitals": total_hospitals,
        "total_schools": total_schools,
        "total_roads_km": total_roads,
        "total_population": total_population,
        "high_risk_zones": len(high_risk_zones),
        "zones": [
            {
                "name": z["name"],
                "risk_score": z["risk_score"],
                "hospitals": z["hospitals"],
                "schools": z["schools"],
                "roads_km": z["roads_km"],
                "population": z["population"]
            }
            for z in ZONES_DATA
        ]
    })

@app.route("/api/stats")
@login_required
def api_stats():
    """Get dashboard statistics"""
    live_data = fetch_live_data()
    high_risk_count = sum(1 for z in ZONES_DATA if z["risk_score"] >= 0.6)
    avg_risk = sum(z["risk_score"] for z in ZONES_DATA) / len(ZONES_DATA)
    
    return jsonify({
        "total_zones": len(ZONES_DATA),
        "high_risk_zones": high_risk_count,
        "average_risk_score": round(avg_risk, 3),
        "current_rainfall": live_data.get("rainfall", 0),
        "current_river_level": live_data.get("river", 0),
        "data_sources": ["Google Flood Hub", "IMD", "NASA GPM", "CWC Gauges"],
        "last_update": datetime.now().isoformat()
    })

@app.route("/api/text/analyze", methods=["POST"])
@login_required
def api_text_analyze():
    """Analyze a single text payload."""
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    source = payload.get("source", "unknown")
    try:
        record = analyze_text(text, source=source)
        add_record(record)
        _log_text_alert(record)
        return jsonify(record)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@app.route("/api/text/ingest", methods=["POST"])
@login_required
def api_text_ingest():
    """Ingest and analyze a batch of text items."""
    payload = request.get_json(silent=True) or {}
    items = payload.get("items", [])
    analyzed = []
    for item in items:
        text = item.get("text", "")
        source = item.get("source", "unknown")
        try:
            record = analyze_text(text, source=source)
            analyzed.append(record)
        except ValueError:
            continue
    if analyzed:
        add_records(analyzed)
    return jsonify({
        "ingested": len(analyzed),
        "records": analyzed
    })

@app.route("/api/text/summary")
@login_required
def api_text_summary():
    """Return aggregated text analytics summary."""
    records = list_records(limit=200)
    summary = aggregate_text_signals(records)
    return jsonify(summary)

@app.route("/api/text/fetch-twitter", methods=["POST"])
@login_required
def api_text_fetch_twitter():
    """Fetch recent tweets from X API, analyze, and store."""
    payload = request.get_json(silent=True) or {}
    query = payload.get("query", "")
    max_results = payload.get("max_results", 10)
    try:
        tweets = fetch_recent_tweets(query=query, max_results=max_results)
    except Exception as exc:
        # Surface error details for easier troubleshooting.
        app.logger.exception("Twitter fetch failed")
        error_msg = str(exc) or exc.__class__.__name__
        return jsonify({"error": error_msg}), 400

    analyzed = []
    for item in tweets:
        try:
            record = analyze_text(item.get("text", ""), source=item.get("source") or "twitter")
            record["tweet_id"] = item.get("tweet_id")
            record["created_at"] = item.get("created_at")
            record["author_id"] = item.get("author_id")
            record["lang"] = item.get("lang")
            record["metrics"] = item.get("metrics", {})
            record["tweet_url"] = item.get("tweet_url") or item.get("tweet_url", "")
            record["extra"] = {
                "created_at": item.get("created_at"),
                "author_id": item.get("author_id"),
                "lang": item.get("lang"),
                "metrics": item.get("metrics", {}),
                "tweet_url": item.get("tweet_url") or item.get("tweet_url", ""),
            }
            analyzed.append(record)
        except ValueError:
            continue

    if analyzed:
        add_records(analyzed)
        for record in analyzed:
            _log_text_alert(record)

    return jsonify({
        "fetched": len(tweets),
        "ingested": len(analyzed),
        "records": analyzed
    })


@app.route("/api/sensors/ingest", methods=["POST"])
def api_sensors_ingest():
    """Ingest sensor readings via HTTP."""
    if not validate_ingest_token(request):
        return jsonify({"error": "Invalid ingest token"}), 401
    payload = request.get_json(silent=True) or {}
    readings = payload.get("readings")
    try:
        if isinstance(readings, list):
            rows = add_sensor_readings(readings)
            return jsonify({"ingested": len(rows)})
        row = add_sensor_reading(payload)
        return jsonify({"ingested": 1, "reading": {
            "sensor_id": row.sensor_id,
            "type": row.sensor_type,
            "value": row.value,
            "unit": row.unit,
            "lat": row.lat,
            "lon": row.lon,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/sensors/ingest-file", methods=["POST"])
def api_sensors_ingest_file():
    """Bulk ingest sensor readings via CSV or JSON upload."""
    if not validate_ingest_token(request):
        return jsonify({"error": "Invalid ingest token"}), 401
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Invalid file"}), 400
    filename = file.filename.lower()
    try:
        raw = file.read()
        if filename.endswith(".json"):
            payload = json.loads(raw.decode("utf-8"))
            items = payload if isinstance(payload, list) else payload.get("readings", [])
            rows = add_sensor_readings(items)
            return jsonify({"ingested": len(rows)})
        if filename.endswith(".csv"):
            text = raw.decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
            items = []
            for row in reader:
                items.append({
                    "sensor_id": row.get("sensor_id") or row.get("id"),
                    "type": row.get("type") or row.get("sensor_type"),
                    "value": row.get("value"),
                    "unit": row.get("unit"),
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                    "timestamp": row.get("timestamp"),
                })
            rows = add_sensor_readings(items)
            return jsonify({"ingested": len(rows)})
        return jsonify({"error": "Unsupported file type. Use .csv or .json"}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/sensors/latest")
@login_required
def api_sensors_latest():
    """Return latest sensor readings grouped by type."""
    latest = list_latest_readings(limit_per_type=1)
    return jsonify({
        "latest": {
            sensor_type: readings_to_dict(readings)
            for sensor_type, readings in latest.items()
        }
    })


@app.route("/api/sensors/history")
@login_required
def api_sensors_history():
    sensor_type = request.args.get("type")
    limit = int(request.args.get("limit", 50))
    rows = list_recent_readings(sensor_type=sensor_type, limit=limit)
    return jsonify({"readings": readings_to_dict(rows)})

@app.route("/reports")
@login_required
def reports():
    zone_id = request.args.get('zone', None)
    zone_data = None
    
    if zone_id:
        # Find zone data
        for zone in ZONES_DATA:
            if zone["id"] == zone_id:
                live_data = fetch_live_data()
                features = [live_data.get("rainfall", 120), live_data.get("river", 7), live_data.get("soil", 0.8)]
                risk_level, risk_score = predict_risk(features)
                
                # Combine static and live risk
                combined_score = (zone["risk_score"] * 0.6 + risk_score * 0.4)
                if combined_score >= 0.8:
                    final_level = "SEVERE"
                elif combined_score >= 0.6:
                    final_level = "HIGH"
                elif combined_score >= 0.4:
                    final_level = "MODERATE"
                else:
                    final_level = "LOW"
                
                zone_data = zone.copy()
                zone_data["live_risk_score"] = round(combined_score, 3)
                zone_data["live_risk_level"] = final_level
                zone_data["rainfall"] = live_data.get("rainfall", 0)
                zone_data["river_level"] = live_data.get("river", 0)
                zone_data["soil_moisture"] = live_data.get("soil", 0)
                break
    
    return render_template("reports.html", zone_data=zone_data, zone_id=zone_id)

@app.route("/text-analysis")
@login_required
def text_analysis():
    return render_template("text_analysis.html")


def _translate_tweet_text(text):
    """Best-effort translation to English; fallback to original text."""
    if not text:
        return text
    try:
        # Optional dependency; if unavailable, we continue with raw text.
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        return translated or text
    except Exception:
        return text


def _predict_text_label_and_confidence(text):
    """
    Lightweight label/confidence mapping using existing text analyzer.
    Keeps output format expected by result_twitter template.
    """
    analyzed = analyze_text(text, source="twitter")
    sentiment = analyzed.get("sentiment", "neutral")
    disaster_types = analyzed.get("disaster_types", [])
    location_hints = analyzed.get("location_hints", [])
    keywords = analyzed.get("keywords", [])

    label = sentiment.upper()
    signal_boost = 0.0
    if any(kind != "unknown" for kind in disaster_types):
        signal_boost += 0.15
    if location_hints:
        signal_boost += 0.10
    signal_boost += min(len(keywords), 4) * 0.025

    base = {"positive": 0.60, "neutral": 0.55, "negative": 0.70}.get(sentiment, 0.50)
    confidence = min(0.99, max(0.35, base + signal_boost))
    return {"label": label, "confidence": confidence}


@app.route("/predict_twitter", methods=["POST"])
@login_required
def predict_twitter():
    username = request.form.get("username", "").strip()
    if not username:
        return "Username is required. Please go back and try again.", 400

    try:
        user_info, tweets = asyncio.run(fetch_user_data(username))

        for tweet in tweets:
            text_to_predict = tweet.get("text", "")
            translated = _translate_tweet_text(text_to_predict)
            if translated:
                text_to_predict = translated

            result = _predict_text_label_and_confidence(text_to_predict)
            tweet["personality"] = result["label"]
            tweet["confidence"] = round(result["confidence"] * 100, 2)

        return render_template("result_twitter.html", user_info=user_info, tweets=tweets)
    except Exception as exc:
        print(f"Error in predict_twitter: {exc}")
        return f"An error occurred: {exc}. Please go back and try again."

@app.route("/api/reports/zone/<zone_id>")
@login_required
def api_zone_reports(zone_id):
    """Get detailed reports data for a specific zone"""
    zone = None
    for z in ZONES_DATA:
        if z["id"] == zone_id:
            zone = z
            break
    
    if not zone:
        return jsonify({"error": "Zone not found"}), 404
    
    live_data = fetch_live_data()
    features = [live_data.get("rainfall", 120), live_data.get("river", 7), live_data.get("soil", 0.8)]
    risk_level, risk_score = predict_risk(features)
    
    combined_score = (zone["risk_score"] * 0.6 + risk_score * 0.4)
    if combined_score >= 0.8:
        final_level = "SEVERE"
    elif combined_score >= 0.6:
        final_level = "HIGH"
    elif combined_score >= 0.4:
        final_level = "MODERATE"
    else:
        final_level = "LOW"
    
    # Generate historical risk data (simulated)
    historical_data = []
    for i in range(30):
        historical_data.append({
            "date": (datetime.now() - timedelta(days=30-i)).strftime("%Y-%m-%d"),
            "risk_score": round(random.uniform(0.2, 0.9), 3),
            "rainfall": random.randint(50, 200),
            "river_level": round(random.uniform(2, 10), 1)
        })
    
    return jsonify({
        "zone": {
            **zone,
            "live_risk_score": round(combined_score, 3),
            "live_risk_level": final_level,
            "rainfall": live_data.get("rainfall", 0),
            "river_level": live_data.get("river", 0),
            "soil_moisture": live_data.get("soil", 0)
        },
        "historical_data": historical_data,
        "alerts": [
            {
                "id": 1,
                "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
                "status": "Sent",
                "recipients": zone["population"]
            },
            {
                "id": 2,
                "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),
                "status": "Sent",
                "recipients": zone["population"]
            }
        ]
    })

@app.route("/api/reports/all")
@login_required
def api_all_reports():
    """Get reports for all zones"""
    live_data = fetch_live_data()
    zones_summary = []
    
    for zone in ZONES_DATA:
        features = [live_data.get("rainfall", 120), live_data.get("river", 7), live_data.get("soil", 0.8)]
        risk_level, risk_score = predict_risk(features)
        combined_score = (zone["risk_score"] * 0.6 + risk_score * 0.4)
        
        zones_summary.append({
            "id": zone["id"],
            "name": zone["name"],
            "risk_score": round(combined_score * 100, 1),
            "hospitals": zone["hospitals"],
            "schools": zone["schools"],
            "roads_km": zone["roads_km"],
            "population": zone["population"]
        })
    
    return jsonify({"zones": zones_summary})

@app.route("/api/gis/process", methods=['POST'])
@admin_required
def trigger_gis_processing():
    """Trigger GIS processing pipeline"""
    try:
        from gis_processing.pipeline import FloodHazardPipeline
        
        pipeline = FloodHazardPipeline()
        results = pipeline.run_complete_pipeline()
        
        return jsonify({
            "status": "success",
            "message": "GIS processing completed",
            "outputs": {
                "hazard_map": results['objective1']['static_map_png'],
                "hazard_zones": results['objective1']['hazard_zones_geojson'],
                "vulnerability_summary": results['objective2']['vulnerability_summary']
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/api/gis/status")
@login_required
def gis_status():
    """Check GIS processing status and available outputs"""
    status = {
        "gis_available": GIS_AVAILABLE,
        "outputs": {}
    }
    
    # Check for generated files
    output_dir = os.path.join(APP_BASE_DIR, "data", "processed")
    if os.path.exists(output_dir):
        files = {
            "hazard_map_tif": os.path.join(output_dir, "hazard_map.tif"),
            "hazard_zones_geojson": os.path.join(output_dir, "hazard_zones.geojson"),
            "static_map_png": os.path.join(output_dir, "static_hazard_map.png"),
            "enhanced_map_png": os.path.join(output_dir, "enhanced_hazard_map.png"),
            "vulnerability_summary": os.path.join(output_dir, "vulnerability_summary.json")
        }
        
        for key, path in files.items():
            status["outputs"][key] = {
                "exists": os.path.exists(path),
                "path": path
            }
    
    return jsonify(status)

@app.route("/api/static-map")
@login_required
def get_static_map():
    """Serve static hazard map image"""
    from flask import send_file
    
    # Try enhanced map first, then basic map
    enhanced_map = os.path.join(APP_BASE_DIR, "data", "processed", "enhanced_hazard_map.png")
    basic_map = os.path.join(APP_BASE_DIR, "data", "processed", "static_hazard_map.png")
    
    if os.path.exists(enhanced_map):
        return send_file(enhanced_map, mimetype='image/png')
    elif os.path.exists(basic_map):
        return send_file(basic_map, mimetype='image/png')
    else:
        # Return placeholder or generate on-the-fly
        return jsonify({"error": "Static map not available. Run GIS processing first."}), 404

@app.route("/api/gis/raster-map")
@login_required
def get_raster_map():
    """Get colored raster hazard map for Leaflet display (direct area coloring, no overlay boxes)"""
    from flask import send_file
    
    raster_map_path = os.path.join(APP_BASE_DIR, "data", "processed", "hazard_raster.png")
    if os.path.exists(raster_map_path):
        return send_file(raster_map_path, mimetype='image/png')
    else:
        # Fallback to static map
        static_map_path = os.path.join(APP_BASE_DIR, "data", "processed", "static_hazard_map.png")
        if os.path.exists(static_map_path):
            return send_file(static_map_path, mimetype='image/png')
        return jsonify({"error": "Raster map not available. Run GIS processing first."}), 404

@app.route("/api/gis/raster-bounds")
@login_required
def get_raster_bounds():
    """Get bounds for raster map overlay"""
    # India bounds: [[south, west], [north, east]] for Leaflet
    return jsonify({
        "bounds": [[6.0, 68.0], [37.0, 97.0]],  # [[south, west], [north, east]]
        "center": [23.5, 78.5],
        "zoom": 5
    })

@app.route("/api/alert/trigger", methods=['POST'])
@emergency_operator_required
def trigger_alert():
    """Trigger emergency alert system (Objective 3) - Requires Emergency Operator or Admin"""
    try:
        from services.alert_service import send_emergency_alerts
        
        # Get high-risk zones
        high_risk_zones = [zone for zone in ZONES_DATA if zone.get('risk_level') in ['HIGH', 'SEVERE']]
        
        if not high_risk_zones:
            return jsonify({
                "status": "success",
                "message": "No high-risk zones found. No alerts needed.",
                "zones_alerted": 0,
                "alerts_sent": 0,
                "timestamp": datetime.now().isoformat()
            })
        
        # Trigger alert
        result = send_emergency_alerts(high_risk_zones)
        
        # Build response message
        message = "Emergency alerts processed successfully"
        if result.get('recipients_found', 0) == 0:
            message = "No stakeholders found for high-risk zones. Add stakeholders in Admin Panel."
        elif result.get('alerts_sent', 0) == 0 and result.get('alerts_failed', 0) == 0:
            message = "No alerts sent. Check SMTP configuration in Admin Panel."
        
        return jsonify({
            "status": "success",
            "message": message,
            "zones_alerted": len(high_risk_zones),
            "alerts_sent": result.get('alerts_sent', 0),
            "alerts_failed": result.get('alerts_failed', 0),
            "recipients_found": result.get('recipients_found', 0),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in trigger_alert: {error_trace}")
        return jsonify({
            "status": "error",
            "message": f"Failed to trigger alerts: {str(e)}"
        }), 500

# ========== ADMIN PANEL ROUTES ==========

@app.route("/admin")
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    total_users = User.query.count()
    total_stakeholders = Stakeholder.query.count()
    total_alerts = AlertLog.query.count()
    
    # Get user role breakdown
    admin_count = User.query.filter_by(role='admin').count()
    operator_count = User.query.filter_by(role='emergency_operator').count()
    viewer_count = User.query.filter_by(role='viewer').count()
    active_users = User.query.filter_by(active=True).count()
    
    # Get alert statistics
    successful_alerts = AlertLog.query.filter_by(status='sent').count()
    failed_alerts = AlertLog.query.filter_by(status='failed').count()
    
    # Get recent alerts (last 24 hours)
    from datetime import timedelta
    recent_alerts = AlertLog.query.filter(
        AlertLog.timestamp >= datetime.utcnow() - timedelta(days=1)
    ).count()
    
    # Get stakeholder statistics
    subscribed_stakeholders = Stakeholder.query.filter_by(subscribed=True).count()
    
    return render_template('admin/dashboard.html', 
                         user=current_user,
                         total_users=total_users,
                         total_stakeholders=total_stakeholders,
                         total_alerts=total_alerts,
                         admin_count=admin_count,
                         operator_count=operator_count,
                         viewer_count=viewer_count,
                         active_users=active_users,
                         successful_alerts=successful_alerts,
                         failed_alerts=failed_alerts,
                         recent_alerts=recent_alerts,
                         subscribed_stakeholders=subscribed_stakeholders,
                         zones=ZONES_DATA)

@app.route("/admin/stakeholders")
@admin_required
def admin_stakeholders():
    """Stakeholder management page"""
    zone_id = request.args.get('zone_id', None)
    stakeholders = Stakeholder.query
    if zone_id:
        stakeholders = stakeholders.filter_by(zone_id=zone_id)
    stakeholders = stakeholders.all()
    
    # Debug: Print stakeholder zone_ids for troubleshooting
    if stakeholders:
        print(f"[DEBUG] Stakeholders in database: {len(stakeholders)}")
        sample_zone_ids = [s.zone_id for s in stakeholders[:5]]
        print(f"[DEBUG] Sample stakeholder zone_ids: {sample_zone_ids}")
        if ZONES_DATA:
            sample_zones = [z.get('id') for z in ZONES_DATA[:5]]
            print(f"[DEBUG] Sample ZONES_DATA zone IDs: {sample_zones}")
            
            # Check if any stakeholder zone_ids match ZONES_DATA
            all_zone_ids = [z.get('id') for z in ZONES_DATA]
            matching = [s.zone_id for s in stakeholders if s.zone_id in all_zone_ids]
            print(f"[DEBUG] Stakeholders with valid zone_ids: {len(matching)}/{len(stakeholders)}")
    
    return render_template('admin/stakeholders.html', 
                         user=current_user,
                         stakeholders=stakeholders,
                         zones=ZONES_DATA)

@app.route("/admin/stakeholders/add", methods=['POST'])
@admin_required
def admin_add_stakeholder():
    """Add new stakeholder"""
    try:
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        zone_id = request.form.get('zone_id', '').strip()
        subscribed = request.form.get('subscribed', 'true') == 'true'
        
        # Validate required fields
        if not name:
            flash('Name is required.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        if not zone_id:
            flash('Zone is required.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        # Check for duplicate email
        existing = Stakeholder.query.filter_by(email=email).first()
        if existing:
            flash(f'Stakeholder with email {email} already exists.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        # Verify zone_id exists in ZONES_DATA
        zone_exists = any(zone.get('id') == zone_id for zone in ZONES_DATA)
        if not zone_exists:
            print(f"WARNING: Zone ID '{zone_id}' not found in ZONES_DATA")
            print(f"Available zone IDs (first 5): {[z.get('id') for z in ZONES_DATA[:5]]}")
        
        # Create new stakeholder
        stakeholder = Stakeholder(
            name=name,
            email=email,
            phone=phone if phone else None,
            zone_id=zone_id,
            subscribed=subscribed
        )
        
        db.session.add(stakeholder)
        db.session.commit()
        
        print(f"Stakeholder added: {name} ({email}) in zone '{zone_id}'")
        print(f"   Zone exists in ZONES_DATA: {zone_exists}")
        flash(f'Stakeholder "{name}" added successfully in zone {zone_id}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        print(f"ERROR: Error adding stakeholder: {error_msg}")
        import traceback
        traceback.print_exc()
        flash(f'Error adding stakeholder: {error_msg}', 'error')
    
    return redirect(url_for('admin_stakeholders'))

@app.route("/admin/stakeholders/<int:stakeholder_id>/edit", methods=['POST'])
@admin_required
def admin_edit_stakeholder(stakeholder_id):
    """Edit stakeholder"""
    try:
        stakeholder = Stakeholder.query.get_or_404(stakeholder_id)
        stakeholder.name = request.form.get('name')
        stakeholder.email = request.form.get('email')
        stakeholder.phone = request.form.get('phone', '')
        stakeholder.zone_id = request.form.get('zone_id')
        stakeholder.subscribed = request.form.get('subscribed', 'true') == 'true'
        stakeholder.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Stakeholder updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating stakeholder: {str(e)}', 'error')
    
    return redirect(url_for('admin_stakeholders'))

@app.route("/admin/stakeholders/<int:stakeholder_id>/delete", methods=['POST'])
@admin_required
def admin_delete_stakeholder(stakeholder_id):
    """Delete stakeholder"""
    try:
        stakeholder = Stakeholder.query.get_or_404(stakeholder_id)
        db.session.delete(stakeholder)
        db.session.commit()
        flash('Stakeholder deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting stakeholder: {str(e)}', 'error')
    
    return redirect(url_for('admin_stakeholders'))

@app.route("/admin/stakeholders/upload", methods=['POST'])
@admin_required
def admin_upload_stakeholders():
    """Bulk upload stakeholders from CSV"""
    try:
        if 'file' not in request.files:
            flash('No file provided.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'error')
            return redirect(url_for('admin_stakeholders'))
        
        # Read CSV
        stream = file.stream.read().decode("UTF8")
        csv_reader = csv.DictReader(stream.splitlines())
        
        added = 0
        errors = 0
        
        for row in csv_reader:
            try:
                stakeholder = Stakeholder(
                    name=row.get('name', '').strip(),
                    email=row.get('email', '').strip(),
                    phone=row.get('phone', '').strip(),
                    zone_id=row.get('zone_id', '').strip(),
                    subscribed=row.get('subscribed', 'true').lower() == 'true'
                )
                db.session.add(stakeholder)
                added += 1
            except Exception as e:
                errors += 1
                print(f"Error adding row: {e}")
        
        db.session.commit()
        flash(f'Successfully added {added} stakeholders. {errors} errors.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error uploading CSV: {str(e)}', 'error')
    
    return redirect(url_for('admin_stakeholders'))

@app.route("/admin/config")
@admin_required
def admin_config():
    """System configuration page"""
    configs = {c.key: c.value for c in SystemConfig.query.all()}
    return render_template('admin/config.html', 
                         user=current_user,
                         configs=configs,
                         zones=ZONES_DATA)

@app.route("/admin/config/update", methods=['POST'])
@admin_required
def admin_update_config():
    """Update system configuration"""
    try:
        config_type = request.form.get('config_type')
        
        if config_type == 'smtp':
            # Update SMTP settings
            for key in ['SMTP_SERVER', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD']:
                value = request.form.get(key.lower(), '')
                config = SystemConfig.query.filter_by(key=key).first()
                if config:
                    config.value = value
                else:
                    config = SystemConfig(key=key, value=value)
                    db.session.add(config)
        
        elif config_type == 'thresholds':
            # Update alert thresholds
            for key in ['ALERT_THRESHOLD', 'RISK_THRESHOLD_LOW', 'RISK_THRESHOLD_MODERATE', 'RISK_THRESHOLD_HIGH']:
                value = request.form.get(key.lower(), '')
                config = SystemConfig.query.filter_by(key=key).first()
                if config:
                    config.value = value
                else:
                    config = SystemConfig(key=key, value=value)
                    db.session.add(config)
        
        db.session.commit()
        flash('Configuration updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating configuration: {str(e)}', 'error')
    
    return redirect(url_for('admin_config'))

@app.route("/admin/users")
@admin_required
def admin_users():
    """User management page"""
    users = User.query.all()
    return render_template('admin/users.html', user=current_user, users=users)

@app.route("/admin/users/<int:user_id>/update-role", methods=['POST'])
@admin_required
def admin_update_user_role(user_id):
    """Update user role"""
    try:
        user = User.query.get_or_404(user_id)
        new_role = request.form.get('role')
        
        if new_role not in ['admin', 'emergency_operator', 'viewer']:
            flash('Invalid role.', 'error')
            return redirect(url_for('admin_users'))
        
        user.role = new_role
        db.session.commit()
        flash(f'User role updated to {new_role}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating user role: {str(e)}', 'error')
    
    return redirect(url_for('admin_users'))

# Initialize background scheduler
try:
    from services.scheduler import start_scheduler
    start_scheduler(app)
except Exception as e:
    print(f"Warning: Could not start scheduler: {e}")

if __name__ == "__main__":
    app.run(debug=False)
