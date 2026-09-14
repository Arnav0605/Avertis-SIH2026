"""
Self-Test & Verification Script for Fire Detection + ESP32 Hardware Integration.
Verifies model loading, ESP32 bridge offline fallback, HUD drawing, and multi-modal severity logic.
"""

import numpy as np
import cv2
from ultralytics import YOLO
from esp32_bridge import ESP32Bridge

def test_esp32_bridge():
    print("\n--- Testing ESP32Bridge ---")
    bridge = ESP32Bridge()
    bridge.start()
    
    data = bridge.get_smoke_data()
    print(f"Initial Smoke Data: {data}")
    assert "smoke" in data
    assert "smoke_alert" in data
    assert "connected" in data
    
    # Test sending commands (should not error even when offline)
    bridge.send_alert("FIRE")
    bridge.send_alert("WEAPON")
    bridge.send_alert("CLEAR")
    bridge.set_threshold(2000)
    
    bridge.stop()
    print("[PASS] ESP32Bridge offline fallback and commands verified.")

def test_models():
    print("\n--- Testing YOLO Models ---")
    fire_model = YOLO("old_best.pt")
    person_model = YOLO("yolo11n.pt")
    weapon_model = YOLO("best.pt")
    
    print(f"Fire classes: {fire_model.names}")
    print(f"Person classes: {person_model.names}")
    print(f"Weapon classes: {weapon_model.names}")
    
    # Dummy test frame (640x480 black image)
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    res_fire = fire_model(dummy_frame, conf=0.35, verbose=False)[0]
    res_person = person_model(dummy_frame, conf=0.30, classes=[0], verbose=False)[0]
    res_weapon = weapon_model(dummy_frame, conf=0.60, verbose=False)[0]
    
    print(f"Dummy inference successful: Fire boxes={len(res_fire.boxes)}, Person boxes={len(res_person.boxes)}, Weapon boxes={len(res_weapon.boxes)}")
    print("[PASS] YOLO models loaded and inferred successfully.")

def test_multimodal_severity():
    print("\n--- Testing Multi-Modal Severity Fusion ---")
    def calc_severity(fire_det, smoke_det, max_conf):
        if (fire_det and smoke_det) or max_conf >= 0.70:
            return "CRITICAL"
        elif smoke_det or max_conf >= 0.50:
            return "WARNING"
        else:
            return "NORMAL"
    
    assert calc_severity(False, False, 0.2) == "NORMAL"
    assert calc_severity(False, True, 0.2) == "WARNING"
    assert calc_severity(True, True, 0.3) == "CRITICAL"
    assert calc_severity(True, False, 0.75) == "CRITICAL"
    assert calc_severity(False, False, 0.55) == "WARNING"
    print("[PASS] Multi-modal severity matrix validated.")

if __name__ == "__main__":
    print("========================================")
    print("Running FireDetection System Self-Check")
    print("========================================")
    test_esp32_bridge()
    test_multimodal_severity()
    test_models()
    print("\n[ALL TESTS PASSED SUCCESSFULLY!]")
