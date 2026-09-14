# 🚨 Avertis — AI-Powered Disaster Prevention & Early Warning System

> **Smart India Hackathon 2026**

Avertis is an **AI-powered real-time disaster prevention and early warning system** designed to identify potential safety threats before they escalate.

The current prototype uses computer vision to continuously monitor a camera feed and detect **fire, people, firearms, and knives**. When a significant threat is identified, the system can generate a real-time alert with an incident screenshot through Telegram.

The system also includes an **ESP32-based hardware integration layer**, providing a foundation for combining visual AI with environmental sensors for more reliable disaster detection.

---

## 🎯 Vision

The goal of Avertis is to move from **reactive disaster response to proactive disaster prevention**.

Instead of waiting for an incident to become severe, the system continuously monitors an environment, identifies early warning signs, and communicates the threat to responsible personnel.

```text
        CONTINUOUS MONITORING
                ↓
          AI DETECTION
                ↓
        THREAT IDENTIFICATION
                ↓
         EARLY WARNING
                ↓
        RAPID NOTIFICATION
                ↓
       FASTER HUMAN RESPONSE
```

---

## 🔥 The Problem

Fire and security incidents can escalate rapidly when they are not detected in time.

Traditional monitoring often depends on:

* Manual CCTV observation
* Separate alarm systems
* Human reporting
* Delayed response

Avertis introduces an **AI-assisted monitoring layer** that can continuously analyze camera footage and automatically identify potential threats.

---

## 💡 Our Approach

Avertis combines:

* 🤖 Artificial Intelligence
* 👁️ Computer Vision
* 📹 Real-time Camera Monitoring
* 🔌 ESP32 Hardware Integration
* 📡 Sensor Integration Capability
* 📱 Real-time Telegram Alerts

The system is designed around **early detection and early warning**, allowing human responders to act sooner.

---

# 🧠 AI-Based Threat Detection

Avertis currently uses multiple YOLO models for specialized detection tasks.

### 🔥 Fire Detection

A custom-trained YOLO model detects fire in real-time camera frames.

**Model:** `old_best.pt`

Fire detection is one of the primary components of the current disaster-prevention prototype.

### 👤 Person Detection

A YOLO model is used to identify people in the monitored environment.

**Model:** `yolo11n.pt`

Person detection provides additional context during an incident—for example, identifying whether people are present in an area where a threat has been detected.

### 🔫 Firearm & 🔪 Knife Detection

A separate custom YOLO model detects:

* Firearms
* Knives

**Model:** `best.pt`

This extends Avertis beyond fire safety into **general safety and security monitoring**.

---

# ⚡ Real-Time Prevention Pipeline

```text
📹 Camera
   ↓
🎞️ Video Frames
   ↓
🤖 YOLO Models
   ↓
🔥 Fire   👤 Person   🔫 Firearm   🔪 Knife
   ↓
🧠 Threat Analysis
   ↓
🚨 Alert Decision
   ↓
📱 Telegram Alert
   ↓
📸 Incident Screenshot
```

The system continuously processes the camera fee

