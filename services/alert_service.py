"""
Emergency Alert Service
Objective 3: Automated alert dissemination to stakeholders in high-risk zones
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import json
from database.db import db, AlertLog, Stakeholder, SystemConfig

def get_smtp_config():
    """Get SMTP configuration from database or environment"""
    from flask import current_app
    
    smtp_config = SystemConfig.query.filter(SystemConfig.key.like('SMTP_%')).all()
    config_dict = {c.key: c.value for c in smtp_config}
    
    # Get from Flask config if available
    app_config = {}
    try:
        app_config = {
            'server': current_app.config.get('SMTP_SERVER', ''),
            'port': current_app.config.get('SMTP_PORT', 587),
            'user': current_app.config.get('SMTP_USER', ''),
            'password': current_app.config.get('SMTP_PASSWORD', '')
        }
    except:
        pass
    
    return {
        'server': config_dict.get('SMTP_SERVER', app_config.get('server', os.getenv('SMTP_SERVER', 'smtp.gmail.com'))),
        'port': int(config_dict.get('SMTP_PORT', app_config.get('port', os.getenv('SMTP_PORT', '587')))),
        'user': config_dict.get('SMTP_USER', app_config.get('user', os.getenv('SMTP_USER', ''))),
        'password': config_dict.get('SMTP_PASSWORD', app_config.get('password', os.getenv('SMTP_PASSWORD', '')))
    }

def get_stakeholders_for_zones(zone_ids):
    """Get stakeholders for specific zones from database"""
    if not zone_ids:
        print("[DEBUG] No zone IDs provided")
        return []
    
    print(f"[DEBUG] Looking for stakeholders in zones: {zone_ids[:5]}... (showing first 5 of {len(zone_ids)})")
    
    # Get all subscribed stakeholders
    all_stakeholders = Stakeholder.query.filter(
        Stakeholder.subscribed == True
    ).all()
    
    print(f"[DEBUG] Total subscribed stakeholders in database: {len(all_stakeholders)}")
    
    # Filter by zone_id
    matching_stakeholders = [
        s for s in all_stakeholders 
        if s.zone_id in zone_ids
    ]
    
    print(f"[DEBUG] Matching stakeholders found: {len(matching_stakeholders)}")
    if matching_stakeholders:
        print(f"[DEBUG] Sample stakeholder zone_ids: {[s.zone_id for s in matching_stakeholders[:3]]}")
        print(f"[DEBUG] Sample zone_ids being searched: {zone_ids[:3]}")
    
    return [s.email for s in matching_stakeholders if s.email]

def send_emergency_alerts(high_risk_zones):
    """
    Send emergency alerts to stakeholders in high-risk zones
    
    Args:
        high_risk_zones: List of zone dictionaries with risk information
    
    Returns:
        dict: Results of alert sending operation
    """
    results = {
        'alerts_sent': 0,
        'alerts_failed': 0,
        'zones_covered': len(high_risk_zones),
        'timestamp': datetime.now().isoformat(),
        'recipients_found': 0
    }
    
    # Check SMTP configuration first
    smtp_config = get_smtp_config()
    if not smtp_config['user'] or not smtp_config['password']:
        print("[WARNING] SMTP not configured. Alerts will be logged but not sent.")
        print("[INFO] Configure SMTP in Admin Panel > Configuration")
        # Still process and log alerts even if SMTP is not configured
    
    # Get zone IDs
    zone_ids = [zone.get('id') for zone in high_risk_zones if zone.get('id')]
    
    print(f"[DEBUG] High-risk zones found: {len(high_risk_zones)}")
    print(f"[DEBUG] Zone IDs extracted: {len(zone_ids)}")
    if zone_ids:
        print(f"[DEBUG] Sample zone IDs: {zone_ids[:5]}")
    
    # Get stakeholders from database
    all_recipients = get_stakeholders_for_zones(zone_ids)
    results['recipients_found'] = len(all_recipients)
    
    print(f"[DEBUG] Recipients found: {len(all_recipients)}")
    
    # Fallback to hardcoded list if database is empty (for testing)
    if not all_recipients:
        print("[INFO] No stakeholders found in database for these zones.")
        print("[INFO] Add stakeholders in Admin Panel > Stakeholders")
        # Don't use hardcoded emails in production - require database entries
        # STAKEHOLDER_EMAILS = {
        #     'emergency_operators': [
        #         'operator1@example.com',
        #         'operator2@example.com',
        #     ],
        # }
        # for category, emails in STAKEHOLDER_EMAILS.items():
        #     all_recipients.extend(emails)
    
    # Remove duplicates
    all_recipients = list(set(all_recipients))
    
    if not all_recipients:
        print("[WARNING] No recipients found. No alerts will be sent.")
        return results
    
    # Create alert message
    alert_message = create_alert_message(high_risk_zones)
    
    # Send alerts
    for recipient in all_recipients:
        try:
            send_email_alert(recipient, alert_message)
            results['alerts_sent'] += 1
            
            # Log alert
            log_alert(recipient, 'sent', high_risk_zones)
        except Exception as e:
            results['alerts_failed'] += 1
            print(f"Failed to send alert to {recipient}: {e}")
            log_alert(recipient, 'failed', high_risk_zones, error=str(e))
    
    return results

def create_alert_message(high_risk_zones):
    """Create alert message content"""
    zone_names = [zone.get('name', 'Unknown') for zone in high_risk_zones]
    
    message = f"""
EMERGENCY FLOOD ALERT

Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

HIGH-RISK FLOOD ZONES IDENTIFIED

The following zones have been identified as HIGH RISK:

{chr(10).join(f"• {name}" for name in zone_names)}

IMMEDIATE ACTIONS REQUIRED:
1. Evacuate if in immediate danger
2. Move to higher ground
3. Avoid flooded areas
4. Follow local authority instructions
5. Monitor official updates

This is an automated alert from the Flood Monitoring & Response Dashboard.

Stay safe!
"""
    return message

def send_email_alert(recipient, message):
    """Send email alert via SMTP"""
    smtp_config = get_smtp_config()
    
    if not smtp_config['user'] or not smtp_config['password']:
        # In development, just log the alert
        print(f"[DEV MODE] Would send alert to {recipient}")
        print(f"Message: {message[:200]}...")
        # Don't raise an error in dev mode, just log it
        return True  # Return True to indicate "success" in dev mode
    
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_config['user']
        msg['To'] = recipient
        msg['Subject'] = "EMERGENCY FLOOD ALERT - High Risk Zone"
        
        msg.attach(MIMEText(message, 'plain'))
        
        # Create SMTP connection with timeout
        server = smtplib.SMTP(smtp_config['server'], smtp_config['port'], timeout=30)
        server.starttls()
        server.login(smtp_config['user'], smtp_config['password'])
        server.send_message(msg)
        server.quit()
        
        print(f"Alert sent to {recipient}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"SMTP Authentication failed. Check username and password. Error: {str(e)}"
        print(f"ERROR: {error_msg}")
        raise Exception(error_msg)
    except smtplib.SMTPConnectError as e:
        error_msg = f"Failed to connect to SMTP server {smtp_config['server']}:{smtp_config['port']}. Error: {str(e)}"
        print(f"ERROR: {error_msg}")
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Failed to send email to {recipient}: {str(e)}"
        print(f"ERROR: {error_msg}")
        raise Exception(error_msg)

def log_alert(recipient, status, zones, error=None):
    """Log alert to database"""
    try:
        alert_log = AlertLog(
            recipient=recipient,
            status=status,
            zones_affected=json.dumps([z.get('id') for z in zones]),
            error_message=error,
            timestamp=datetime.now()
        )
        db.session.add(alert_log)
        db.session.commit()
    except Exception as e:
        print(f"Failed to log alert: {e}")

def get_alert_history(limit=50):
    """Get recent alert history"""
    try:
        alerts = AlertLog.query.order_by(AlertLog.timestamp.desc()).limit(limit).all()
        return [{
            'recipient': alert.recipient,
            'status': alert.status,
            'zones': json.loads(alert.zones_affected) if alert.zones_affected else [],
            'timestamp': alert.timestamp.isoformat(),
            'error': alert.error_message
        } for alert in alerts]
    except Exception as e:
        print(f"Failed to get alert history: {e}")
        return []
