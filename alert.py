import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load secrets from the .env file securely
load_dotenv()

def send_sms_alert(item_name: str, stock: int):
    """Sends SMS using Twilio credentials hidden in the .env file."""
    try:
        # Fetch credentials from environment variables
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_phone = os.getenv("TWILIO_FROM_NUMBER")
        to_phone = os.getenv("MANAGER_PHONE")

        client = Client(account_sid, auth_token)
        alert_body = f"🚨 WAREHOUSE ALERT 🚨\nItem: {item_name}\nStock Level: {stock} (CRITICAL)\nAction: Reorder immediately."
        
        message = client.messages.create(
            body=alert_body,
            from_=from_phone,
            to=to_phone
        )
        print(f"✅ SMS sent! SID: {message.sid}")
    except Exception as e:
        print(f"❌ Failed to send SMS: {str(e)}")

def send_analytics_sms(report_text: str):
    """Sends a formatted analytics report via SMS."""
    try:
        # Fetch credentials from environment variables to match the first function
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_phone = os.getenv("TWILIO_FROM_NUMBER")
        to_phone = os.getenv("MANAGER_PHONE")

        client = Client(account_sid, auth_token) 
        message = client.messages.create(
            body=report_text,
            from_=from_phone,
            to=to_phone 
        )
        print(f"✅ Analytics SMS sent successfully! SID: {message.sid}")
    except Exception as e:
        print(f"❌ Failed to send Twilio Analytics SMS: {e}")