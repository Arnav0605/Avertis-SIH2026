import cv2
import os
import time
import requests
import threading

from ultralytics import YOLO
from datetime import datetime
from dotenv import load_dotenv
from esp32_bridge import ESP32Bridge


# =========================================================
# DETECTION CONFIDENCE THRESHOLDS (TUNED TO PREVENT FALSE ALARMS)
# =========================================================

CONF_FIRE = 0.55     # Raised from 0.35 to eliminate false positives from ambient lights
CONF_PERSON = 0.45   # Raised from 0.30 for cleaner person tracking
CONF_WEAPON = 0.68   # Raised from 0.60 for high-precision gun/knife detection

INFERENCE_INTERVAL = 2  # Run YOLO every 2 frames to keep camera feed 100% current and realtime


# =========================================================
# LOAD YOLO MODELS
# =========================================================

fire_model = YOLO("old_best.pt")
person_model = YOLO("yolo11n.pt")
weapon_model = YOLO("best.pt")

print("Fire model:", fire_model.names)
print("Person model:", person_model.names)
print("Weapon model:", weapon_model.names)


# =========================================================
# HARDWARE INTEGRATION (ESP32 NODE)
# =========================================================

esp32 = ESP32Bridge()
esp32.start()


# =========================================================
# TELEGRAM CONFIGURATION
# =========================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TELEGRAM_COOLDOWN = 60

last_telegram_alert = {
    "FIRE": 0,
    "GUN": 0,
    "KNIFE": 0,
    "SMOKE": 0,
    "HEAT": 0
}


# =========================================================
# ASYNCHRONOUS NON-BLOCKING TELEGRAM ALERT DISPATCHER
# =========================================================

def _async_send_telegram(frame_copy, severity, threat, confidence, env_info=""):
    """Runs in background thread so main camera loop NEVER freezes."""
    try:
        success, buffer = cv2.imencode(".jpg", frame_copy)
        if not success:
            return

        caption = (
            f"{severity} ALERT\n\n"
            f"Threat: {threat}\n"
            f"Confidence: {confidence:.0%}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        if env_info:
            caption += f"\nTelemetry: {env_info}"

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption
            },
            files={
                "photo": (
                    "alert.jpg",
                    buffer.tobytes(),
                    "image/jpeg"
                )
            },
            timeout=8
        )
        print(f"[TELEGRAM] Alert sent: {threat}")
    except Exception as e:
        print(f"[TELEGRAM] Error sending notification: {e}")


def send_telegram_alert(frame, severity, threat, confidence, env_info=""):
    """Dispatches Telegram alert asynchronously without blocking."""
    threading.Thread(
        target=_async_send_telegram,
        args=(frame.copy(), severity, threat, confidence, env_info),
        daemon=True
    ).start()


# =========================================================
# THREADED CAMERA STREAM (PREVENTS FRAME BUFFER BACKLOG)
# =========================================================

class ThreadedCamera:
    """
    Dedicated camera reader thread that continually discards stale buffered frames.
    Guarantees the main loop ALWAYS receives the absolute freshest live frame.
    """
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        # Request minimum buffer size from hardware driver
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.ret, self.frame = self.cap.read()
        self.running = True
        self.lock = threading.Lock()

        if not self.cap.isOpened():
            print("ERROR: Could not open webcam.")
            exit()

        self.thread = threading.Thread(target=self._reader, daemon=True, name="CamReaderThread")
        self.thread.start()

    def _reader(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            with self.lock:
                self.ret = ret
                self.frame = frame

    def read(self):
        with self.lock:
            if self.frame is not None:
                return self.ret, self.frame.copy()
            return False, None

    def release(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.cap.release()


cam = ThreadedCamera(0)


# =========================================================
# EVENT LOG
# =========================================================

event_log = []

last_fire = False
last_gun = False
last_knife = False
last_smoke = False
last_heat = False

# Hardware alert debouncing state
current_hw_alert = "CLEAR"
last_sent_hw_alert = ""
last_threat_timestamp = 0.0

MAX_EVENTS = 5


def add_event(event_type):
    current_time = datetime.now().strftime("%H:%M:%S")
    event_log.insert(0, f"{current_time}  |  {event_type}")
    if len(event_log) > MAX_EVENTS:
        event_log.pop()


# =========================================================
# STATUS CARD RENDERING
# =========================================================

def draw_status_card(
    frame,
    x,
    y,
    width,
    label,
    detected,
    status_text=None,
    offline=False
):
    cv2.rectangle(
        frame,
        (x, y),
        (x + width, y + 42),
        (25, 25, 25),
        -1
    )

    if offline:
        indicator_color = (120, 120, 120)
        status = status_text or "OFFLINE"
    elif detected:
        indicator_color = (0, 0, 255)
        status = status_text or "DETECTED"
    else:
        indicator_color = (0, 190, 0)
        status = status_text or "CLEAR"

    cv2.circle(
        frame,
        (x + 13, y + 21),
        5,
        indicator_color,
        -1
    )

    cv2.putText(
        frame,
        label,
        (x + 25, y + 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (220, 220, 220),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        frame,
        status,
        (x + 25, y + 33),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        indicator_color,
        1,
        cv2.LINE_AA
    )


# =========================================================
# SENSOR TELEMETRY HUD WIDGET
# =========================================================

def draw_sensor_telemetry_panel(frame, x, y, width, height, sensor_data, siren_active):
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + width, y + height), (18, 18, 18), -1)
    cv2.rectangle(overlay, (x, y), (x + width, y + height), (60, 60, 60), 1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    connected = sensor_data.get("connected", False)
    mq2_ok = sensor_data.get("mq2_ok", False)
    dht_ok = sensor_data.get("dht_ok", False)
    smoke_val = sensor_data.get("smoke", 0)
    smoke_alert = sensor_data.get("smoke_alert", False)
    temp = sensor_data.get("temp")
    hum = sensor_data.get("hum")

    # Header
    cv2.putText(
        frame,
        "ESP32 SENSORS",
        (x + 12, y + 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.44,
        (240, 240, 240),
        1,
        cv2.LINE_AA
    )

    hw_color = (0, 210, 0) if connected else (100, 100, 100)
    hw_text = "ONLINE" if connected else "OFFLINE"
    cv2.circle(frame, (x + width - 65, y + 16), 4, hw_color, -1)
    cv2.putText(
        frame,
        hw_text,
        (x + width - 55, y + 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        hw_color,
        1,
        cv2.LINE_AA
    )

    # Line 1: MQ-2 Gas / Smoke
    y_row1 = y + 42
    if not connected or not mq2_ok:
        smoke_str = "UNPLUGGED" if connected else "OFFLINE"
        smoke_col = (130, 130, 130)
    else:
        smoke_str = f"{smoke_val} ADC"
        smoke_col = (0, 0, 255) if smoke_alert else (0, 210, 0)

    cv2.putText(
        frame,
        "MQ-2 GAS:",
        (x + 12, y_row1),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (190, 190, 190),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        frame,
        smoke_str,
        (x + 95, y_row1),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        smoke_col,
        1,
        cv2.LINE_AA
    )

    bar_x = x + 165
    bar_y = y_row1 - 9
    bar_w = width - 180
    bar_h = 9
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (40, 40, 40), -1)

    if connected and mq2_ok:
        fill_pct = min(max(smoke_val / 3500.0, 0.0), 1.0)
        fill_w = int(bar_w * fill_pct)
        bar_color = (0, 0, 255) if fill_pct > 0.50 else ((0, 180, 255) if fill_pct > 0.25 else (0, 200, 0))
        if fill_w > 0:
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), bar_color, -1)

    # Line 2: DHT22 Temperature & Humidity
    y_row2 = y + 68
    cv2.putText(
        frame,
        "TEMP:",
        (x + 12, y_row2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (190, 190, 190),
        1,
        cv2.LINE_AA
    )

    if not connected or not dht_ok or temp is None:
        temp_str = "UNPLUGGED" if connected else "OFFLINE"
        temp_col = (130, 130, 130)
    else:
        temp_str = f"{temp:.1f} C"
        temp_col = (0, 0, 255) if temp >= 48.0 else ((0, 180, 255) if temp >= 40.0 else (0, 220, 0))

    cv2.putText(
        frame,
        temp_str,
        (x + 65, y_row2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        temp_col,
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        frame,
        "HUM:",
        (x + 155, y_row2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (190, 190, 190),
        1,
        cv2.LINE_AA
    )

    if not connected or not dht_ok or hum is None:
        hum_str = "--"
        hum_col = (130, 130, 130)
    else:
        hum_str = f"{hum:.0f}% RH"
        hum_col = (220, 220, 220)

    cv2.putText(
        frame,
        hum_str,
        (x + 200, y_row2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        hum_col,
        1,
        cv2.LINE_AA
    )

    # Line 3: Siren
    y_row3 = y + 94
    cv2.putText(
        frame,
        "SIREN:",
        (x + 12, y_row3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (190, 190, 190),
        1,
        cv2.LINE_AA
    )

    if siren_active:
        siren_text = "ALARM ACTIVE!"
        siren_color = (0, 0, 255)
    elif connected:
        siren_text = "STANDBY (ARMED)"
        siren_color = (0, 190, 0)
    else:
        siren_text = "OFFLINE"
        siren_color = (130, 130, 130)

    cv2.putText(
        frame,
        siren_text,
        (x + 65, y_row3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        siren_color,
        1,
        cv2.LINE_AA
    )


# =========================================================
# MAIN LOOP (ALWAYS REAL-TIME, NEVER BACKLOGGED)
# =========================================================

frame_count = 0

# Cached detection state across interleaved frames
fire_detected = False
person_detected = False
gun_detected = False
knife_detected = False
fire_boxes = []
person_boxes = []
weapon_boxes = []
fire_max_conf = 0.0
gun_max_conf = 0.0
knife_max_conf = 0.0

try:
    while True:
        ret, frame = cam.read()

        if not ret or frame is None:
            time.sleep(0.01)
            continue

        frame_count += 1
        run_inference = (frame_count % INFERENCE_INTERVAL == 0)

        # =====================================================
        # 1. READ SENSORY TELEMETRY
        # =====================================================

        sensor_data = esp32.get_sensor_data()
        smoke_detected = sensor_data.get("smoke_alert", False)
        smoke_val = sensor_data.get("smoke", 0)
        mq2_ok = sensor_data.get("mq2_ok", False)

        current_temp = sensor_data.get("temp")
        current_hum = sensor_data.get("hum")
        dht_ok = sensor_data.get("dht_ok", False)
        esp32_connected = sensor_data.get("connected", False)

        heat_detected = (current_temp is not None and current_temp >= 48.0)

        env_summary = ""
        if current_temp is not None and current_hum is not None:
            env_summary = f"{current_temp:.1f}C | {current_hum:.0f}% RH"
        elif current_temp is not None:
            env_summary = f"{current_temp:.1f}C"

        # =====================================================
        # 2. RUN VISION INFERENCE (WHEN SCHEDULED)
        # =====================================================

        if run_inference:
            # Fire detection
            fire_results = fire_model(frame, conf=CONF_FIRE, verbose=False)
            fire_result = fire_results[0]
            fire_detected = (fire_result.boxes is not None and len(fire_result.boxes) > 0)
            fire_max_conf = 0.0
            fire_boxes = []

            if fire_result.boxes is not None:
                for box in fire_result.boxes:
                    conf = float(box.conf[0])
                    coords = map(int, box.xyxy[0])
                    fire_boxes.append((list(coords), conf))
                    fire_max_conf = max(fire_max_conf, conf)

            # Person detection
            person_results = person_model(frame, conf=CONF_PERSON, classes=[0], verbose=False)
            person_result = person_results[0]
            person_detected = (person_result.boxes is not None and len(person_result.boxes) > 0)
            person_boxes = []

            if person_result.boxes is not None:
                for box in person_result.boxes:
                    conf = float(box.conf[0])
                    coords = map(int, box.xyxy[0])
                    person_boxes.append((list(coords), conf))

            # Weapon detection
            weapon_results = weapon_model(frame, conf=CONF_WEAPON, verbose=False)
            weapon_result = weapon_results[0]
            gun_detected = False
            knife_detected = False
            gun_max_conf = 0.0
            knife_max_conf = 0.0
            weapon_boxes = []

            if weapon_result.boxes is not None:
                for box in weapon_result.boxes:
                    conf = float(box.conf[0])
                    cid = int(box.cls[0])
                    coords = list(map(int, box.xyxy[0]))

                    if cid == 0:
                        gun_detected = True
                        gun_max_conf = max(gun_max_conf, conf)
                        weapon_boxes.append((coords, "GUN", conf))
                    elif cid == 1:
                        knife_detected = True
                        knife_max_conf = max(knife_max_conf, conf)
                        weapon_boxes.append((coords, "KNIFE", conf))

        # =====================================================
        # 3. MULTI-MODAL SEVERITY FUSION
        # =====================================================

        highest_threat_conf = max(fire_max_conf, gun_max_conf, knife_max_conf)
        critical_fire_fusion = (fire_detected and smoke_detected) or (fire_detected and heat_detected)

        if critical_fire_fusion or highest_threat_conf >= 0.70:
            severity = "CRITICAL"
        elif smoke_detected or heat_detected or highest_threat_conf >= 0.50:
            severity = "WARNING"
        else:
            severity = "NORMAL"

        # =====================================================
        # 4. NEW EVENTS & LOGGING
        # =====================================================

        new_fire_event = fire_detected and not last_fire
        new_gun_event = gun_detected and not last_gun
        new_knife_event = knife_detected and not last_knife
        new_smoke_event = smoke_detected and not last_smoke
        new_heat_event = heat_detected and not last_heat

        if new_fire_event and smoke_detected and heat_detected:
            add_event("FIRE CONFIRMED (CV+MQ2+DHT)")
        elif new_fire_event and smoke_detected:
            add_event("FIRE CONFIRMED (CV+MQ2)")
        elif new_fire_event:
            add_event(f"FIRE DETECTED ({fire_max_conf:.0%})")

        if new_smoke_event:
            add_event(f"SMOKE DETECTED ({smoke_val})")

        if new_heat_event:
            add_event(f"HIGH HEAT ({current_temp:.1f}C)")

        if new_gun_event:
            add_event(f"GUN DETECTED ({gun_max_conf:.0%})")

        if new_knife_event:
            add_event(f"KNIFE DETECTED ({knife_max_conf:.0%})")

        last_fire = fire_detected
        last_gun = gun_detected
        last_knife = knife_detected
        last_smoke = smoke_detected
        last_heat = heat_detected

        # =====================================================
        # 5. HARDWARE ALARM DISPATCH (DEBOUNCED, REAL-TIME)
        # =====================================================

        now = time.time()

        if fire_detected:
            target_alert = "FIRE"
            last_threat_timestamp = now
        elif gun_detected:
            target_alert = "GUN"
            last_threat_timestamp = now
        elif knife_detected:
            target_alert = "KNIFE"
            last_threat_timestamp = now
        elif smoke_detected:
            target_alert = "SMOKE"
            last_threat_timestamp = now
        elif heat_detected:
            target_alert = "HEAT"
            last_threat_timestamp = now
        else:
            # Hold siren for only 0.7 seconds after threat ceases, then immediately silence!
            if now - last_threat_timestamp > 0.7:
                target_alert = "CLEAR"
            else:
                target_alert = current_hw_alert

        current_hw_alert = target_alert
        siren_active = (current_hw_alert != "CLEAR")

        if current_hw_alert != last_sent_hw_alert:
            esp32.send_alert(current_hw_alert)
            last_sent_hw_alert = current_hw_alert

        # =====================================================
        # 6. DRAW BOUNDING BOXES
        # =====================================================

        # Fire boxes
        for coords, conf in fire_boxes:
            x1, y1, x2, y2 = coords
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(
                frame,
                f"FIRE {conf:.0%}",
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
                cv2.LINE_AA
            )

        # Person boxes
        for coords, conf in person_boxes:
            x1, y1, x2, y2 = coords
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
            cv2.putText(
                frame,
                f"PERSON {conf:.0%}",
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 180, 0),
                2,
                cv2.LINE_AA
            )

        # Weapon boxes
        for coords, label, conf in weapon_boxes:
            x1, y1, x2, y2 = coords
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(
                frame,
                f"{label} {conf:.0%}",
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
                cv2.LINE_AA
            )

        # =====================================================
        # 7. TOP-LEFT LIVE & SEVERITY BADGES
        # =====================================================

        cv2.circle(frame, (25, 25), 6, (0, 0, 255), -1)
        cv2.putText(
            frame,
            "LIVE",
            (40, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

        if severity == "CRITICAL":
            severity_color = (0, 0, 255)
        elif severity == "WARNING":
            severity_color = (0, 165, 255)
        else:
            severity_color = (0, 190, 0)

        cv2.rectangle(frame, (25, 48), (180, 84), (25, 25, 25), -1)
        cv2.putText(
            frame,
            "SEVERITY",
            (35, 63),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (180, 180, 180),
            1,
            cv2.LINE_AA
        )
        cv2.putText(
            frame,
            severity,
            (35, 78),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            severity_color,
            1,
            cv2.LINE_AA
        )

        # =====================================================
        # 8. TOP-RIGHT STATUS CARDS
        # =====================================================

        frame_width = frame.shape[1]
        frame_height = frame.shape[0]

        card_width = 96
        card_gap = 6
        total_width = card_width * 5 + card_gap * 4
        start_x = frame_width - total_width - 15

        # Card 1: Vision Fire
        draw_status_card(frame, start_x, 15, card_width, "FIRE", fire_detected)

        # Card 2: MQ-2 Smoke
        if not esp32_connected or not mq2_ok:
            smoke_txt = "UNPLUGGED" if esp32_connected else "OFFLINE"
            draw_status_card(frame, start_x + (card_width + card_gap), 15, card_width, "MQ2 SMOKE", False, status_text=smoke_txt, offline=True)
        else:
            smoke_txt = f"GAS {smoke_val}" if smoke_detected else f"OK ({smoke_val})"
            draw_status_card(frame, start_x + (card_width + card_gap), 15, card_width, "MQ2 SMOKE", smoke_detected, status_text=smoke_txt)

        # Card 3: DHT Temperature
        if not esp32_connected or not dht_ok:
            temp_txt = "UNPLUGGED" if esp32_connected else "OFFLINE"
            draw_status_card(frame, start_x + 2 * (card_width + card_gap), 15, card_width, "DHT TEMP", False, status_text=temp_txt, offline=True)
        else:
            temp_txt = f"HOT {current_temp:.0f}C" if heat_detected else f"{current_temp:.1f}C"
            draw_status_card(frame, start_x + 2 * (card_width + card_gap), 15, card_width, "DHT TEMP", heat_detected, status_text=temp_txt)

        # Card 4: Gun
        draw_status_card(frame, start_x + 3 * (card_width + card_gap), 15, card_width, "GUN", gun_detected)

        # Card 5: Knife
        draw_status_card(frame, start_x + 4 * (card_width + card_gap), 15, card_width, "KNIFE", knife_detected)

        # =====================================================
        # 9. BOTTOM-LEFT EVENT LOG
        # =====================================================

        log_x = 20
        log_y = frame_height - 135

        cv2.rectangle(
            frame,
            (log_x, log_y),
            (290, frame_height - 15),
            (20, 20, 20),
            -1
        )

        cv2.putText(
            frame,
            "EVENT LOG",
            (log_x + 12, log_y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (200, 200, 200),
            1,
            cv2.LINE_AA
        )

        for i, event in enumerate(event_log):
            cv2.putText(
                frame,
                event,
                (log_x + 12, log_y + 40 + i * 17),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.33,
                (220, 220, 220),
                1,
                cv2.LINE_AA
            )

        # =====================================================
        # 10. BOTTOM-RIGHT SENSOR TELEMETRY PANEL
        # =====================================================

        panel_w = 290
        panel_h = 120
        panel_x = frame_width - panel_w - 15
        panel_y = frame_height - panel_h - 15

        draw_sensor_telemetry_panel(
            frame,
            panel_x,
            panel_y,
            panel_w,
            panel_h,
            sensor_data,
            siren_active
        )

        # =====================================================
        # 11. ASYNCHRONOUS TELEGRAM ALERTS (ZERO LATENCY)
        # =====================================================

        current_time = time.time()

        if new_fire_event:
            if current_time - last_telegram_alert["FIRE"] >= TELEGRAM_COOLDOWN:
                last_telegram_alert["FIRE"] = current_time
                alert_title = "CONFIRMED FIRE HAZARD" if (smoke_detected or heat_detected) else "FIRE DETECTED"
                send_telegram_alert(
                    frame,
                    severity,
                    alert_title,
                    fire_max_conf,
                    env_info=f"Smoke: {smoke_val} | Env: {env_summary}"
                )

        if new_smoke_event:
            if current_time - last_telegram_alert["SMOKE"] >= TELEGRAM_COOLDOWN:
                last_telegram_alert["SMOKE"] = current_time
                send_telegram_alert(
                    frame,
                    severity,
                    "SMOKE / GAS HAZARD",
                    0.85,
                    env_info=f"MQ-2: {smoke_val} | Env: {env_summary}"
                )

        if new_heat_event:
            if current_time - last_telegram_alert["HEAT"] >= TELEGRAM_COOLDOWN:
                last_telegram_alert["HEAT"] = current_time
                send_telegram_alert(
                    frame,
                    severity,
                    "EXTREME TEMPERATURE ANOMALY",
                    0.90,
                    env_info=f"Temp: {current_temp:.1f}C | Humidity: {current_hum:.0f}%"
                )

        if new_gun_event:
            if current_time - last_telegram_alert["GUN"] >= TELEGRAM_COOLDOWN:
                last_telegram_alert["GUN"] = current_time
                send_telegram_alert(
                    frame,
                    severity,
                    "GUN DETECTED",
                    gun_max_conf
                )

        if new_knife_event:
            if current_time - last_telegram_alert["KNIFE"] >= TELEGRAM_COOLDOWN:
                last_telegram_alert["KNIFE"] = current_time
                send_telegram_alert(
                    frame,
                    severity,
                    "KNIFE DETECTED",
                    knife_max_conf
                )

        # =====================================================
        # 12. RENDER LIVE WINDOW
        # =====================================================

        cv2.imshow("Fire & Disaster Prevention System", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    # =========================================================
    # CLEANUP
    # =========================================================
    esp32.send_alert("CLEAR")
    esp32.stop()
    cam.release()
    cv2.destroyAllWindows()