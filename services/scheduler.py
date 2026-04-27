"""
Background task scheduler using APScheduler
Handles scheduled data fetching, risk recalculation, and database cleanup
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import os
import atexit
from database.db import db, AlertLog
from services.data_fetcher import fetch_live_data
from services.twitter_ingestion import fetch_recent_tweets
from services.text_ingestion import add_records
from models.text_analyzer import analyze_text
from models.risk_predictor import predict_risk

scheduler = BackgroundScheduler()
flask_app = None

def fetch_and_update_data():
    """Scheduled task: Fetch live data and update risk scores"""
    try:
        print(f"[{datetime.now()}] Running scheduled data fetch...")
        live_data = fetch_live_data()
        print(f"[{datetime.now()}] Data fetched: {live_data}")
        # Additional processing can be added here
    except Exception as e:
        print(f"[{datetime.now()}] Error in scheduled data fetch: {e}")

def recalculate_risks():
    """Scheduled task: Recalculate risk scores using ML models"""
    try:
        print(f"[{datetime.now()}] Running scheduled risk recalculation...")
        live_data = fetch_live_data()
        features = [live_data.get("rainfall", 120), live_data.get("river", 7), live_data.get("soil", 0.8)]
        risk_level, risk_score = predict_risk(features)
        print(f"[{datetime.now()}] Risk recalculated: {risk_level} ({risk_score})")
    except Exception as e:
        print(f"[{datetime.now()}] Error in risk recalculation: {e}")

def cleanup_old_alerts():
    """Scheduled task: Clean up old alert logs (keep last 90 days)"""
    global flask_app
    try:
        print(f"[{datetime.now()}] Running scheduled database cleanup...")
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        if flask_app:
            with flask_app.app_context():
                deleted = AlertLog.query.filter(AlertLog.timestamp < cutoff_date).delete()
                db.session.commit()
                print(f"[{datetime.now()}] Cleaned up {deleted} old alert logs")
        else:
            print(f"[{datetime.now()}] Flask app not available for cleanup")
    except Exception as e:
        print(f"[{datetime.now()}] Error in database cleanup: {e}")


def ingest_text_updates():
    """Scheduled task: Fetch and analyze text/news signals."""
    global flask_app
    query = os.getenv("TEXT_DEFAULT_QUERY", "flood OR cyclone OR earthquake")
    max_results = int(os.getenv("TEXT_DEFAULT_MAX_RESULTS", "20"))
    try:
        print(f"[{datetime.now()}] Running scheduled text ingest...")
        if not flask_app:
            print(f"[{datetime.now()}] Flask app not available for text ingest")
            return
        with flask_app.app_context():
            items = fetch_recent_tweets(query=query, max_results=max_results)
            analyzed = []
            for item in items:
                try:
                    record = analyze_text(item.get("text", ""), source=item.get("type", "news"))
                    record["external_id"] = item.get("tweet_id")
                    record["created_at"] = item.get("created_at")
                    record["tweet_url"] = item.get("tweet_url", "")
                    record["extra"] = {
                        "created_at": item.get("created_at"),
                        "tweet_url": item.get("tweet_url", ""),
                        "type": item.get("type", "news"),
                    }
                    analyzed.append(record)
                except ValueError:
                    continue
            if analyzed:
                add_records(analyzed)
            print(f"[{datetime.now()}] Text ingest complete: {len(analyzed)} items")
    except Exception as e:
        print(f"[{datetime.now()}] Error in text ingest: {e}")

def start_scheduler(app=None):
    """Start the background scheduler"""
    global flask_app
    if app:
        flask_app = app
    
    # Schedule hourly data fetch
    scheduler.add_job(
        func=fetch_and_update_data,
        trigger=CronTrigger(minute=0),  # Every hour at minute 0
        id='fetch_data',
        name='Fetch Live Data',
        replace_existing=True
    )
    
    # Schedule risk recalculation every 6 hours
    scheduler.add_job(
        func=recalculate_risks,
        trigger=CronTrigger(hour='*/6'),  # Every 6 hours
        id='recalculate_risks',
        name='Recalculate Risk Scores',
        replace_existing=True
    )
    
    # Schedule daily database cleanup at 2 AM
    scheduler.add_job(
        func=cleanup_old_alerts,
        trigger=CronTrigger(hour=2, minute=0),  # Daily at 2 AM
        id='cleanup_database',
        name='Database Cleanup',
        replace_existing=True
    )

    # Schedule text/news ingestion every 30 minutes
    scheduler.add_job(
        func=ingest_text_updates,
        trigger=CronTrigger(minute='*/30'),
        id='ingest_text_updates',
        name='Ingest Text Updates',
        replace_existing=True
    )
    
    scheduler.start()
    print("Background scheduler started")
    
    # Shutdown scheduler on exit
    atexit.register(lambda: scheduler.shutdown())

def stop_scheduler():
    """Stop the background scheduler"""
    scheduler.shutdown()
    print("Background scheduler stopped")
