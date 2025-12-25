# Hardware Setup Guide

This guide covers the wiring and setup of sensors for the Smart Agriculture Monitoring System on Raspberry Pi.

## Components Required

| Component | Quantity | Purpose |
|-----------|----------|---------|
| Raspberry Pi (3B+/4/Zero W) | 1 | Main controller |
| DHT22 Sensor | 1 | Temperature & humidity |
| Capacitive Soil Moisture Sensor | 1 | Soil moisture level |
| MCP3008 ADC | 1 | Analog-to-digital conversion |
| 10kΩ Resistor | 1 | Pull-up for DHT22 |
| Breadboard | 1 | Prototyping |
| Jumper Wires | ~15 | Connections |

---

## Raspberry Pi GPIO Pinout Reference

```
                    ┌─────────────────┐
                    │   Raspberry Pi  │
                    │    GPIO Header  │
                    ├─────┬─────┬─────┤
        3.3V Power ─┤  1  │  2  │ 5V Power
          GPIO 2   ─┤  3  │  4  │ 5V Power
          GPIO 3   ─┤  5  │  6  │ Ground
  DHT22 → GPIO 4   ─┤  7  │  8  │ GPIO 14
               GND ─┤  9  │ 10  │ GPIO 15
          GPIO 17  ─┤ 11  │ 12  │ GPIO 18
          GPIO 27  ─┤ 13  │ 14  │ Ground
          GPIO 22  ─┤ 15  │ 16  │ GPIO 23
              3.3V ─┤ 17  │ 18  │ GPIO 24
   MOSI → GPIO 10  ─┤ 19  │ 20  │ Ground
   MISO → GPIO 9   ─┤ 21  │ 22  │ GPIO 25
   SCLK → GPIO 11  ─┤ 23  │ 24  │ GPIO 8 ← CE0
             Ground─┤ 25  │ 26  │ GPIO 7 ← CE1
                    └─────┴─────┴─────┘
```

---

## DHT22 Sensor Wiring

The DHT22 sensor has 4 pins (some modules have 3 with built-in resistor).

### Pin Connections

| DHT22 Pin | Connect To | Description |
|-----------|------------|-------------|
| VCC (+)   | Pin 1 (3.3V) or Pin 2 (5V) | Power supply |
| DATA      | Pin 7 (GPIO 4) | Data signal |
| NC        | Not connected | Unused |
| GND (-)   | Pin 9 (Ground) | Ground |

### Wiring Diagram

```
                    ┌─────────────┐
                    │    DHT22    │
                    │             │
                    │ VCC DATA NC GND
                    │  │    │   │  │
                    └──┼────┼───┼──┼──┘
                       │    │   │  │
    3.3V (Pin 1) ──────┘    │   │  └────── GND (Pin 9)
                            │   │
    GPIO 4 (Pin 7) ─────────┤   │
                            │   │
         10kΩ Resistor ─────┤   
              │             │
    3.3V ─────┘             │ (Not Connected)
```

**Note**: The 10kΩ pull-up resistor between DATA and VCC is optional if your DHT22 module has a built-in resistor.

---

## MCP3008 ADC + Soil Moisture Sensor Wiring

The MCP3008 is an 8-channel 10-bit ADC that converts analog soil moisture readings to digital.

### MCP3008 Pin Connections

| MCP3008 Pin | Pin # | Connect To | Description |
|-------------|-------|------------|-------------|
| VDD         | 16    | 3.3V (Pin 17) | Power |
| VREF        | 15    | 3.3V (Pin 17) | Reference voltage |
| AGND        | 14    | GND (Pin 20) | Analog ground |
| CLK         | 13    | GPIO 11 (Pin 23) | SPI Clock |
| DOUT        | 12    | GPIO 9 (Pin 21) | SPI MISO |
| DIN         | 11    | GPIO 10 (Pin 19) | SPI MOSI |
| CS/SHDN     | 10    | GPIO 8 (Pin 24) | SPI CE0 |
| DGND        | 9     | GND (Pin 25) | Digital ground |
| CH0         | 1     | Soil Sensor OUT | Analog input |
| CH1-CH7     | 2-8   | (Available) | Other sensors |

### Soil Moisture Sensor Connections

| Sensor Pin | Connect To | Description |
|------------|------------|-------------|
| VCC        | 3.3V (Pin 17) | Power |
| GND        | GND (Pin 25) | Ground |
| AOUT       | MCP3008 CH0 (Pin 1) | Analog output |

### Complete Wiring Diagram

```
                        ┌───────────────────┐
                        │      MCP3008      │
                        │                   │
            CH0 ────────┤ 1              16 ├──────── VDD (3.3V)
            CH1 ────────┤ 2              15 ├──────── VREF (3.3V)
            CH2 ────────┤ 3              14 ├──────── AGND
            CH3 ────────┤ 4              13 ├──────── CLK (GPIO 11)
            CH4 ────────┤ 5              12 ├──────── DOUT (GPIO 9)
            CH5 ────────┤ 6              11 ├──────── DIN (GPIO 10)
            CH6 ────────┤ 7              10 ├──────── CS (GPIO 8)
            CH7 ────────┤ 8               9 ├──────── DGND
                        └───────────────────┘
                              │
                              │ CH0
                              │
                    ┌─────────┴─────────┐
                    │   Soil Moisture   │
                    │      Sensor       │
                    │                   │
                    │  VCC  GND  AOUT   │
                    │   │    │    │     │
                    └───┼────┼────┼─────┘
                        │    │    │
               3.3V ────┘    │    └───── to MCP3008 CH0
                             │
                      GND ───┘
```

---

## Enable SPI on Raspberry Pi

1. Open Raspberry Pi configuration:
   ```bash
   sudo raspi-config
   ```

2. Navigate to: **Interface Options** → **SPI** → **Enable**

3. Reboot:
   ```bash
   sudo reboot
   ```

4. Verify SPI is enabled:
   ```bash
   ls /dev/spi*
   # Should show: /dev/spidev0.0  /dev/spidev0.1
   ```

---

## Calibration

### Soil Moisture Sensor Calibration

1. **Record dry value**: Place sensor in dry air
   ```bash
   python -c "from scripts.sensors import SoilMoistureSensor; s = SoilMoistureSensor(); print(s._read_adc())"
   ```
   Note the value (typically ~1000-1023)

2. **Record wet value**: Submerge sensor in water
   ```bash
   python -c "from scripts.sensors import SoilMoistureSensor; s = SoilMoistureSensor(); print(s._read_adc())"
   ```
   Note the value (typically ~300-400)

3. **Update config**: Edit `config/config.yaml`:
   ```yaml
   sensors:
     soil_moisture:
       calibration:
         dry_value: 1020  # Your dry reading
         wet_value: 350   # Your wet reading
   ```

---

## Testing Individual Sensors

### Test DHT22

```bash
cd Smart-Agricultural-Monitoring-System
python -c "
from scripts.sensors import DHT22Sensor
sensor = DHT22Sensor(gpio_pin=4)
reading = sensor.read()
print(f'Temperature: {reading.temperature}°C')
print(f'Humidity: {reading.humidity}%')
"
```

### Test Soil Moisture

```bash
python -c "
from scripts.sensors import SoilMoistureSensor
sensor = SoilMoistureSensor(channel=0)
reading = sensor.read()
print(f'Moisture: {reading.moisture_percent}%')
print(f'Raw ADC: {reading.raw_value}')
"
```

---

## Troubleshooting

### DHT22 Not Reading

- Check wiring, especially the data pin
- Ensure pull-up resistor is connected
- Verify GPIO 4 is not used by another process
- Try GPIO pin 17 or 27 as alternatives

### Soil Moisture Sensor Reading 0 or 1023

- Check SPI is enabled
- Verify MCP3008 wiring (CLK, MOSI, MISO, CS)
- Ensure 3.3V power supply is stable
- Check sensor analog output with multimeter

### Permission Errors

```bash
sudo usermod -a -G spi,gpio $USER
# Then logout and login again
```

---

## Power Considerations

| Component | Current Draw |
|-----------|--------------|
| DHT22 | ~1.5 mA |
| Soil Moisture Sensor | ~5 mA |
| MCP3008 | ~0.5 mA |
| **Total** | **~7 mA** |

For outdoor deployment, consider:
- Weatherproof enclosure
- Solar panel + battery for remote locations
- Long sensor cables with shielding
