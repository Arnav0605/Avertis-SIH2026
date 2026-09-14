"""
ESP32 Hardware Bridge for Multi-Threat Sensory System
Handles asynchronous USB serial communication with the ESP32 node.
Receives telemetry from MQ-2 (gas/smoke) and DHT22 (temp/humidity).
Dispatches threat alarms (siren buzzer / alert LEDs).
"""

import json
import threading
import time
import os
from typing import Optional, Dict, Any

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class ESP32Bridge:
    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        self.baudrate = baudrate
        self.port = port or os.getenv("ESP32_PORT")
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.lock = threading.Lock()

        # Telemetry State (Supports MQ-2, DHT22, Buzzer)
        self.latest_data: Dict[str, Any] = {
            "smoke": 0,
            "raw": 0,
            "smoke_alert": False,
            "mq2_ok": False,
            "temp": None,
            "hum": None,
            "dht_ok": False,
            "state": "DISCONNECTED",
            "connected": False,
            "last_seen": 0.0
        }

        # Background thread
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the background serial communication thread."""
        if not SERIAL_AVAILABLE:
            print("[ESP32] Notice: 'pyserial' not installed. Running in offline/mock mode.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="ESP32BridgeThread")
        self.thread.start()

    def stop(self):
        """Stops the communication thread and closes serial connection."""
        self.running = False
        self._disconnect()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)

    def _find_port(self) -> Optional[str]:
        """Auto-detects USB COM port corresponding to ESP32."""
        if not SERIAL_AVAILABLE:
            return None

        try:
            ports = list(serial.tools.list_ports.comports())
            if not ports:
                return None

            for p in ports:
                desc = (p.description or "").lower()
                hwid = (p.hwid or "").lower()
                mfg = (p.manufacturer or "").lower()
                combined = f"{desc} {hwid} {mfg}"
                if any(k in combined for k in ["cp210", "ch340", "ch9102", "ftdi", "usb to uart", "esp32", "silicon labs", "wch"]):
                    return p.device

            for p in ports:
                if "usb" in (p.description or "").lower():
                    return p.device
        except Exception:
            pass

        return None

    def _connect(self) -> bool:
        """Attempts connection to ESP32 without blocking."""
        target_port = self.port or self._find_port()
        if not target_port:
            return False

        try:
            self.serial_conn = serial.Serial(
                port=target_port,
                baudrate=self.baudrate,
                timeout=0.1,
                write_timeout=0.2
            )
            with self.lock:
                self.latest_data["connected"] = True
                self.latest_data["state"] = "CONNECTING"
            print(f"[ESP32] Connected to ESP32 on {target_port} at {self.baudrate} baud.")
            return True
        except Exception as e:
            self._disconnect()
            return False

    def _disconnect(self):
        """Safely closes serial port."""
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

        with self.lock:
            self.latest_data["connected"] = False
            self.latest_data["state"] = "DISCONNECTED"

    def _run_loop(self):
        """Non-blocking background loop reading telemetry."""
        last_reconnect_attempt = 0.0

        while self.running:
            if not self.serial_conn or not self.serial_conn.is_open:
                now = time.time()
                if now - last_reconnect_attempt >= 3.0:
                    last_reconnect_attempt = now
                    self._connect()
                time.sleep(0.1)
                continue

            try:
                if not self.running:
                    break

                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
                    if line:
                        self._handle_telemetry_line(line)
                else:
                    time.sleep(0.02)
            except (serial.SerialException, OSError) as e:
                print(f"[ESP32] Serial disconnected: {e}")
                self._disconnect()
                time.sleep(0.5)
            except Exception:
                time.sleep(0.05)

    def _handle_telemetry_line(self, line: str):
        """Parses JSON telemetry packets from ESP32."""
        if not (line.startswith("{") and line.endswith("}")):
            return

        try:
            payload = json.loads(line)
            with self.lock:
                # MQ-2 Data
                if "smoke" in payload:
                    self.latest_data["smoke"] = int(payload["smoke"])
                if "raw" in payload:
                    self.latest_data["raw"] = int(payload["raw"])
                if "smoke_alert" in payload:
                    self.latest_data["smoke_alert"] = bool(payload["smoke_alert"])
                if "mq2_ok" in payload:
                    self.latest_data["mq2_ok"] = bool(payload["mq2_ok"])

                # DHT22 Data (can be null if sensor unplugged)
                if "temp" in payload and payload["temp"] is not None:
                    try:
                        self.latest_data["temp"] = float(payload["temp"])
                    except (ValueError, TypeError):
                        self.latest_data["temp"] = None
                else:
                    self.latest_data["temp"] = None

                if "hum" in payload and payload["hum"] is not None:
                    try:
                        self.latest_data["hum"] = float(payload["hum"])
                    except (ValueError, TypeError):
                        self.latest_data["hum"] = None
                else:
                    self.latest_data["hum"] = None

                if "dht_ok" in payload:
                    self.latest_data["dht_ok"] = bool(payload["dht_ok"])

                if "state" in payload:
                    self.latest_data["state"] = str(payload["state"])

                self.latest_data["connected"] = True
                self.latest_data["last_seen"] = time.time()
        except json.JSONDecodeError:
            pass

    def get_sensor_data(self) -> Dict[str, Any]:
        """Returns snapshot of current sensory state (MQ-2, DHT22, Connection)."""
        with self.lock:
            data = dict(self.latest_data)
            if data["connected"] and (time.time() - data["last_seen"] > 4.0):
                data["connected"] = False
            return data

    def get_smoke_data(self) -> Dict[str, Any]:
        """Backward-compatible alias for get_sensor_data."""
        return self.get_sensor_data()

    def send_alert(self, alert_type: str):
        """Dispatches siren/alert command to ESP32: FIRE | WEAPON | GUN | KNIFE | SMOKE | HEAT | CLEAR"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        cmd = f"ALERT:{alert_type.upper()}\n"
        try:
            self.serial_conn.write(cmd.encode("utf-8"))
            self.serial_conn.flush()
        except Exception as e:
            print(f"[ESP32] Error sending command {cmd.strip()}: {e}")
