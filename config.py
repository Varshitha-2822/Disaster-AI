import os


class Config:
    SECRET_KEY = "flood-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///flood.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ALERT_THRESHOLD = 0.75

    # Flask-Login settings
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # SMTP Configuration (can be overridden by SystemConfig)
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = "vandhanatruprojects@gmail.com"
    SMTP_PASSWORD = "pahksvxachlnoopc"
    
    # Risk classification parameters
    RISK_THRESHOLD_LOW = 0.4
    RISK_THRESHOLD_MODERATE = 0.6
    RISK_THRESHOLD_HIGH = 0.8

    # X / feed fetch: rss = NEWS_RSS_FEEDS only (no login). twikit = free logged-in session (Cookies/auth.json).
    # Override anytime with env TWITTER_FETCH_MODE=rss|twikit
    TWITTER_FETCH_MODE = os.environ.get("TWITTER_FETCH_MODE", "twikit")
