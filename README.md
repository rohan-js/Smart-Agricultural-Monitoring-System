# Smart Agriculture Monitoring System 🌱

A distributed IoT monitoring system for agricultural environments using Raspberry Pi sensors and AWS IoT Core for real-time data collection, visualization, and alerting.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![AWS IoT](https://img.shields.io/badge/AWS-IoT%20Core-orange.svg)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Compatible-red.svg)

## Features

- 🌡️ **Temperature & Humidity Monitoring** - DHT22 sensor integration
- 💧 **Soil Moisture Tracking** - Capacitive sensor with MCP3008 ADC
- ☁️ **AWS IoT Core Integration** - Secure MQTT publishing with TLS
- 📊 **CloudWatch Dashboards** - Real-time visualization
- 🚨 **Threshold Alerts** - Configurable warning and critical alerts via SNS
- 🔄 **Simulation Mode** - Test without hardware

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi                             │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
│  │   DHT22      │  │  Soil Moisture  │  │   Python App     │   │
│  │   Sensor     │──│     Sensor      │──│  (main.py)       │   │
│  └──────────────┘  └─────────────────┘  └────────┬─────────┘   │
└───────────────────────────────────────────────────┼─────────────┘
                                                    │ MQTT/TLS
                                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
│  │  IoT Core    │──│  IoT Analytics  │──│   CloudWatch     │   │
│  │  (MQTT)      │  │  (Storage)      │  │   (Dashboard)    │   │
│  └──────┬───────┘  └─────────────────┘  └──────────────────┘   │
│         │                                                        │
│  ┌──────▼───────┐  ┌─────────────────┐                          │
│  │  IoT Rules   │──│      SNS        │──► Email/SMS Alerts     │
│  │  Engine      │  │  (Alerts)       │                          │
│  └──────────────┘  └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and Install Dependencies

```bash
cd Smart-Agricultural-Monitoring-System
pip install -r requirements.txt
```

### 2. Configure AWS IoT (see detailed guide)

Follow [AWS Setup Instructions](aws/setup_instructions.md) to:
- Create IoT Thing and certificates
- Create and attach IoT policy
- Set up CloudWatch dashboard

### 3. Update Configuration

Edit `config/config.yaml`:
```yaml
aws_iot:
  endpoint: "YOUR_ENDPOINT.iot.YOUR_REGION.amazonaws.com"

device:
  id: "farm-sensor-001"
  location: "Field-A"
```

### 4. Run in Simulation Mode (No Hardware)

```bash
python -m scripts.main --simulate
```

### 5. Run with Hardware (Raspberry Pi)

```bash
python -m scripts.main
```

## Usage

```bash
# Run with simulated sensors
python -m scripts.main --simulate

# Run for specific duration (60 seconds)
python -m scripts.main --simulate --duration 60

# Test AWS IoT connection
python -m scripts.main --test-connection

# Test alert system
python -m scripts.main --simulate --force-alert

# Enable debug logging
python -m scripts.main --simulate --log-level DEBUG
```

## Project Structure

```
Smart-Agricultural-Monitoring-System/
├── config/
│   ├── config.yaml          # Main configuration
│   └── thresholds.yaml      # Alert thresholds
├── scripts/
│   ├── sensors/
│   │   ├── dht22_sensor.py  # DHT22 temperature/humidity
│   │   └── soil_moisture.py # Soil moisture sensor
│   ├── aws/
│   │   ├── mqtt_publisher.py    # MQTT publishing
│   │   └── iot_connection.py    # AWS IoT connection
│   └── main.py              # Main application
├── aws/
│   ├── iot-policy.json      # IoT policy template
│   ├── iot-rule-alerts.json # IoT rule for alerts
│   ├── cloudwatch-dashboard.json
│   └── setup_instructions.md
├── certs/                   # AWS certificates (not in git)
├── docs/
│   └── hardware_setup.md    # Wiring guide
└── requirements.txt
```

## Configuration

### Sensor Thresholds (config/thresholds.yaml)

| Metric | Warning | Critical |
|--------|---------|----------|
| Temperature | 10-35°C | 5-40°C |
| Humidity | 30-80% | 20-90% |
| Soil Moisture | 25-85% | 15-95% |

### Publishing Settings

- **Interval**: 30 seconds (configurable)
- **QoS Level**: 1 (at least once delivery)
- **Topics**:
  - `agriculture/sensors/{device_id}/telemetry`
  - `agriculture/sensors/{device_id}/alerts`
  - `agriculture/sensors/{device_id}/status`

## Hardware Requirements

- Raspberry Pi (3B+, 4, or Zero W)
- DHT22 Temperature/Humidity Sensor
- Capacitive Soil Moisture Sensor
- MCP3008 ADC (for soil moisture analog reading)
- Jumper wires and breadboard

See [Hardware Setup Guide](docs/hardware_setup.md) for wiring instructions.

## Sample Output

```
Starting Smart Agriculture Monitoring System...
  Device ID: farm-sensor-001
  Location: Field-A
  Simulation Mode: True
  Publish Interval: 30s

2024-12-24 12:30:00 - INFO - Sensor readings: {'temperature': 28.3, 'humidity': 62.5, 'soil_moisture': 45.2}
2024-12-24 12:30:00 - INFO - [SIMULATED] Publishing to agriculture/sensors/farm-sensor-001/telemetry
2024-12-24 12:30:30 - INFO - Sensor readings: {'temperature': 27.9, 'humidity': 63.1, 'soil_moisture': 44.8}
```

## Deliverables

| Item | Location | Status |
|------|----------|--------|
| Sensor reading scripts | `scripts/sensors/` | ✅ |
| MQTT publishing | `scripts/aws/` | ✅ |
| AWS IoT policy | `aws/iot-policy.json` | ✅ |
| AWS setup guide | `aws/setup_instructions.md` | ✅ |
| CloudWatch dashboard | `aws/cloudwatch-dashboard.json` | ✅ |
| Alert configuration | `aws/iot-rule-alerts.json` | ✅ |
| Screenshots | `docs/screenshots/` | ✅ |

## Screenshots

All screenshots are located in `docs/screenshots/`:

| Screenshot | Description |
|------------|-------------|
| IoT Thing Details.png | AWS IoT Core Thing configuration |
| Certificate Attached.png | Device certificate attachment |
| IoT Policy.png | IoT security policy |
| IoT Rules.png | IoT message routing rules |
| MQTT Test Client.png | Real-time MQTT messages |
| CloudWatch Dashboard.png | Sensor data visualization |
| CloudWatch Metrics.png | SmartAgriculture namespace metrics |
| SNS Topic.png | Alert notification topic |
| Email Alert.png | Sample email alert notification |
| Terminal.png | System running terminal output |

## License

MIT License - see LICENSE file for details.
