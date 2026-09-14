🚨 Avertis — AI-Powered Disaster Prevention & Early Warning System

Smart India Hackathon 2026

Avertis is an AI-powered real-time disaster prevention and early warning system designed to identify potential safety threats before they escalate.

The current prototype uses computer vision to continuously monitor a camera feed and detect fire, people, firearms, and knives. When a significant threat is identified, the system can generate a real-time alert with an incident screenshot through Telegram.

The system also includes an ESP32-based hardware integration layer, providing a foundation for combining visual AI with environmental sensors for more reliable disaster detection.

🎯 Vision

The goal of Avertis is to move from reactive disaster response to proactive disaster prevention.

Instead of waiting for an incident to become severe, the system continuously monitors an environment, identifies early warning signs, and communicates the threat to responsible personnel.

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
🔥 The Problem

Fire and security incidents can escalate rapidly when they are not detected in time.

Traditional monitoring often depends on:

Manual CCTV observation
Separate alarm systems
Human reporting
Delayed response

Avertis introduces an AI-assisted monitoring layer that can continuously analyze camera footage and automatically identify potential threats.

💡 Our Approach

Avertis combines:

🤖 Artificial Intelligence
👁️ Computer Vision
📹 Real-time Camera Monitoring
🔌 ESP32 Hardware Integration
📡 Sensor Integration Capability
📱 Real-time Telegram Alerts

The system is designed around early detection and early warning, allowing human responders to act sooner.

🧠 AI-Based Threat Detection

Avertis currently uses multiple YOLO models for specialized detection tasks.

🔥 Fire Detection

A custom-trained YOLO model detects fire in real-time camera frames.

Model: old_best.pt

Fire detection is one of the primary components of the current disaster-prevention prototype.

👤 Person Detection

A YOLO model is used to identify people in the monitored environment.

Model: yolo11n.pt

Person detection provides additional context during an incident—for example, identifying whether people are present in an area where a threat has been detected.

🔫 Firearm & 🔪 Knife Detection

A separate custom YOLO model detects:

Firearms
Knives

Model: best.pt

This extends Avertis beyond fire safety into general safety and security monitoring.

⚡ Real-Time Prevention Pipeline
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

The system continuously processes the camera feed rather than relying on a user to manually report an incident.

📱 Early Warning & Alerts

When an alert condition is triggered, Avertis can send a Telegram notification containing relevant incident information.

The alert mechanism supports:

🚨 Threat notification
📸 Incident screenshot
⚡ Near real-time communication
⏱️ Alert cooldown to reduce repeated notifications

This allows responsible personnel to receive an early warning without continuously watching the camera feed.

🔌 ESP32 Integration

Avertis includes an ESP32 communication layer that can connect the AI system with physical hardware.

Current Components
Python AI Application
        ↓
  ESP32 Bridge
        ↓
      ESP32
        ↓
Hardware / Sensor Layer

The ESP32 architecture provides a foundation for adding environmental signals to the computer-vision system.

Potential Sensors

The hardware architecture can be extended with:

🌡️ Temperature sensors
💨 Smoke/gas sensors
🔊 Sound/noise sensors
🚨 Buzzer
💡 Warning LEDs

These additional signals can complement AI-based visual detection and help create a more robust early-warning system.

🧩 Multi-Source Disaster Prevention

A key future direction is combining visual AI + environmental sensors.

For example:

             CAMERA
                ↓
         Computer Vision
                ↓
         Fire Detection
                ↓
        ┌───────────────┐
        │ Threat Analysis│
        └───────────────┘
                ↑
                │
        ESP32 + Sensors
                ↓
    Temperature / Smoke / Sound

Instead of depending on a single detection source, the system can eventually use multiple signals to improve confidence in an incident.

📹 CCTV Scalability

Avertis is designed with future CCTV scalability in mind.

The current prototype uses a webcam as the video source. The same AI processing architecture can be extended to existing CCTV/IP camera streams.

Existing CCTV Cameras
        ↓
 RTSP / Video Streams
        ↓
   Avertis AI Engine
        ↓
  Multiple YOLO Models
        ↓
   Threat Analysis
        ↓
 Centralized Alerts

This approach could allow organizations to use their existing camera infrastructure instead of deploying completely new camera networks.

Future Multi-Camera Architecture
 CCTV 1 ──┐
 CCTV 2 ──┤
 CCTV 3 ──┼──→ Avertis AI Server
 CCTV 4 ──┤             ↓
 CCTV N ──┘       Threat Detection
                       ↓
                Central Alert System
📊 Project Status
✅ Implemented
Real-time webcam monitoring
YOLO-based fire detection
Person detection
Firearm detection
Knife detection
Real-time threat processing
Telegram notifications
Incident screenshot alerts
Alert cooldown mechanism
ESP32 communication foundation
ESP32 firmware
🟡 Partially Implemented
AI + physical sensor fusion
Extended environmental monitoring
Hardware-assisted threat analysis
🔮 Future Scope
Existing CCTV/IP camera integration
Multi-camera monitoring
Centralized disaster monitoring dashboard
Temperature and smoke sensor integration
Improved threat/severity classification
Automated incident logging
Building-wide deployment
Cloud-based monitoring
Integration with authorized emergency/security personnel
🛠️ Technology Stack
Category	Technology
Programming	Python
Computer Vision	OpenCV
Object Detection	YOLO
AI Framework	Ultralytics
Hardware	ESP32
Firmware	Arduino
Communication	Python ↔ ESP32
Alerts	Telegram Bot API
Development	VS Code
Version Control	Git & GitHub
📂 Project Structure
Avertis-SIH2026/
│
├── webcam.py
│       Main real-time AI monitoring application
│
├── esp32_bridge.py
│       Python ↔ ESP32 communication
│
├── esp32_firmware.ino
│       ESP32 firmware
│
├── esp32_firmware/
│       ESP32 firmware/project files
│
├── test_pipeline.py
│       Detection pipeline testing
│
├── best.pt
│       Firearm + knife detection model
│
├── old_best.pt
│       Fire detection model
│
├── yolo11n.pt
│       Person detection model
│
├── .gitignore
│
└── README.md
⚙️ Installation
1. Clone the repository
git clone https://github.com/Arnav0605/Avertis-SIH2026.git
cd Avertis-SIH2026
2. Create a virtual environment
python -m venv .venv

On Windows PowerShell:

.venv\Scripts\Activate.ps1
3. Install dependencies
pip install ultralytics opencv-python requests python-dotenv
4. Configure Telegram

Create a .env file:

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

Never upload .env or expose your credentials publicly.

5. Start the monitoring system
python webcam.py
🏆 Smart India Hackathon 2026

Project Name: Avertis
Focus: Disaster Prevention & Early Warning
Primary Application: Fire and Safety Threat Detection
Event: Smart India Hackathon 2026

Avertis demonstrates how AI-powered continuous monitoring, early threat detection, hardware integration, and real-time communication can be combined to build a proactive safety system.

🌐 Future Vision

Avertis can evolve from a single-camera prototype into a scalable disaster-prevention platform capable of monitoring multiple locations.

The long-term vision is:

       MULTIPLE DATA SOURCES
                ↓
       ┌─────────────────┐
       │   AVERTIS AI    │
       │   MONITORING    │
       └─────────────────┘
                ↓
       EARLY THREAT DETECTION
                ↓
          EARLY WARNING
                ↓
       HUMAN INTERVENTION
                ↓
       DISASTER PREVENTION

Detect early. Alert early. Respond faster. Prevent escalation.

🔐 Security

Never commit:

Telegram bot tokens
API keys
Passwords
Private credentials
.env files

Sensitive configuration is excluded through .gitignore.

📜 Project Status

Avertis is an actively developed Smart India Hackathon 2026 prototype.

The current system demonstrates the core real-time AI detection and alert pipeline. Hardware sensor fusion and large-scale CCTV deployment represent the next stages of development.

