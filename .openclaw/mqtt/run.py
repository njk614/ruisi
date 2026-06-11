import paho.mqtt.client as mqtt
import time
import logging
import os
import sys
import json
import requests
from datetime import datetime, timedelta

# Load .env file if exists (parent directory, not scripts subdir)
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s [%(levelname)s] %(message)s")

BROKER    = os.getenv('MQTT_BROKER', 'localhost')
PORT      = int(os.getenv('MQTT_PORT', '1883'))
TOPIC     = os.getenv('MQTT_TOPIC', '#')
USER      = os.getenv('MQTT_USERNAME', '')
PASSWORD  = os.getenv('MQTT_PASSWORD', '')
KEEPALIVE = 60

# XMPP forward endpoint
XMPP_ENDPOINT = 'http://127.0.0.1:18900/send'
FORWARD_TO    = 'a01@im.tuguan.net'
FROM_JID      = 'ae01@im.tuguan.net'

# Meetings file path
MEETINGS_FILE = os.path.expanduser('~/.openclaw/workspace/SimulatedData/meetings.json')

# Forward cooldown: (zone, expected_count) -> meeting_end_datetime
_cooldown = {}  # {(zone, expected_count): datetime}

def load_meetings():
    """Load meetings from JSON file"""
    try:
        with open(MEETINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load meetings: {e}")
        return []

def check_meeting_match(event_time_str, count_value):
    """
    Check if event_time falls within any meeting's time_range
    and countValue >= internal_staff + visitor_count.
    Returns (matched_zone, expected_count, end_dt) if matched, else None.
    """
    meetings = load_meetings()
    try:
        # Parse event time: "2026-06-02 14:25:34"
        event_dt = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logging.warning(f"Failed to parse eventTime: {event_time_str}, {e}")
        return None

    for meeting in meetings:
        room_name = meeting.get('room_name', '')
        zone = meeting.get('zone', '')
        time_range = meeting.get('time_range', '')
        internal_staff = meeting.get('internal_staff', 0)
        visitor_count = meeting.get('visitor_count', 0)
        expected_count = internal_staff + visitor_count

        # Only match room_name = "大会议室"
        if room_name != '大会议室':
            continue

        # Parse time_range: "2026-06-02 15:30~20:00"
        try:
            start_str, end_str = time_range.split('~')
            start_dt = datetime.strptime(start_str.strip(), "%Y-%m-%d %H:%M")
            # Use start date + end time
            end_str_stripped = end_str.strip()
            # Pad single-digit hour if needed
            if len(end_str_stripped.split(':')[0]) == 1:
                end_str_stripped = '0' + end_str_stripped
            end_dt = datetime.strptime(start_str.strip().split(' ')[0] + ' ' + end_str_stripped, "%Y-%m-%d %H:%M")
        except Exception as e:
            logging.warning(f"Failed to parse time_range: {time_range}, {e}")
            continue

        # Check if eventTime is within range (extended 30min earlier) and count >= expected
        if start_dt - timedelta(minutes=30) <= event_dt <= end_dt and count_value >= expected_count:
            logging.info(f"Meeting matched: room={room_name}, zone={zone}, time_range={time_range}, "
                        f"expected_count={expected_count}, actual_count={count_value}")
            return (zone, expected_count, end_dt)

    return None

def forward_to_a01(msg_data):
    """Forward parsed alarm to A01 via XMPP with fixed structure"""
    try:
        video_source = msg_data.get('videoSourceName', '')
        event_time = msg_data.get('eventTime', '')
        count_value = msg_data.get('countValue', 0)

        # Condition 1: videoSourceName must be "大会议室1"
        if video_source != '大会议室1':
            logging.info(f"Skipped: videoSourceName={video_source} (not 大会议室1)")
            return False

        # Condition 2: countValue must be non-zero
        if count_value == 0:
            logging.info(f"Skipped: countValue={count_value} (zero)")
            return False

        # Condition 3: check meeting match (returns zone and expected_count)
        match_result = check_meeting_match(event_time, count_value)
        if match_result is None:
            logging.info(f"Skipped: no matching meeting for eventTime={event_time}, countValue={count_value}")
            return False

        zone, expected_count, meeting_end_dt = match_result

        # Parse event_dt for cooldown check
        try:
            event_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logging.warning(f"Failed to parse eventTime: {event_time}, {e}")
            return False

        # Cooldown check: (zone, expected_count) -> until meeting end_dt
        cooldown_key = (zone, expected_count)
        cached_end_dt = _cooldown.get(cooldown_key)
        if cached_end_dt and event_dt <= cached_end_dt:
            remaining = (cached_end_dt - event_dt).total_seconds()
            logging.info(f"Cooldown active for {cooldown_key}: {int(remaining)}s until meeting end, skipped")
            return False

        # Convert eventTime to ISO format
        if event_time:
            timestamp = event_time.replace(' ', 'T') + '+08:00'
        else:
            timestamp = ''

        # Build fixed structure with zone from matched meeting
        forward_body = {
            'event': 'enter',
            'zone': zone,
            'timestamp': timestamp,
            'total_count': count_value
        }

        data = {
            'jid': FORWARD_TO,
            'body': json.dumps(forward_body, ensure_ascii=False),
            'from': FROM_JID
        }
        resp = requests.post(XMPP_ENDPOINT, json=data, timeout=5)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('success'):
                logging.info(f"Forwarded to {FORWARD_TO}: {forward_body} -> {result.get('messageId', 'OK')}")
                # Store meeting_end_dt for cooldown: forward again only after meeting ends
                _cooldown[cooldown_key] = meeting_end_dt
                return True
        logging.warning(f"Forward failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logging.error(f"Forward error: {e}")
    return False

# Callback functions for VERSION2 API
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.warning(f"Connected successfully to {BROKER}:{PORT}")
        client.subscribe(TOPIC)
        logging.warning(f"Subscribed to topic: {TOPIC}")
    else:
        logging.error(f"Connection failed, result code {rc}. Will retry...")

def on_disconnect(client, userdata, disconnect_flags, rc, properties=None):
    """Handle disconnect with proper signature for paho-mqtt 2.x"""
    if rc != 0:
        logging.warning(f"Unexpected disconnection (rc={rc}). Automatic reconnection will be attempted.")

def on_message(client, userdata, msg, properties=None):
    try:
        payload = msg.payload.decode('utf-8')
        logging.info(f"Received message: {msg.topic} - {payload}")
        try:
            msg_data = json.loads(payload)
            # Handle both single object and array of objects
            if isinstance(msg_data, list):
                for item in msg_data:
                    forward_to_a01(item)
            else:
                forward_to_a01(msg_data)
        except json.JSONDecodeError:
            logging.warning("Non-JSON message, skipped")
    except Exception as e:
        logging.error(f"Message processing error: {e}")

# Main execution
logging.info(f"Starting MQTT client, broker={BROKER}:{PORT}, topic={TOPIC}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.username_pw_set(USER, PASSWORD)

try:
    client.connect(BROKER, PORT, KEEPALIVE)
    client.loop_start() 
    
    logging.info(f"MQTT client running. Listening for messages on {TOPIC}...")
    logging.info(f"Alarm forward target: {FORWARD_TO}")

    # Keep running indefinitely
    while True:
        time.sleep(10)

except KeyboardInterrupt:
    logging.info("Shutting down...")
finally:
    client.disconnect()
    client.loop_stop()
    logging.info("Client disconnected.")