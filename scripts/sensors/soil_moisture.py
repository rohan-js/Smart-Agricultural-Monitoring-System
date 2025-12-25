"""
Soil Moisture Sensor Module

This module provides a class for reading soil moisture data from a
capacitive soil moisture sensor connected via MCP3008 ADC to Raspberry Pi.

Supports simulation mode for testing without hardware.
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SoilMoistureReading:
    """Data class representing a soil moisture sensor reading."""
    moisture_percent: float   # Percentage (0-100)
    raw_value: int           # Raw ADC value (0-1023)
    timestamp: float         # Unix timestamp
    is_valid: bool           # Whether reading passed validation
    error_message: Optional[str] = None


class SoilMoistureSensor:
    """
    Soil Moisture Sensor Interface using MCP3008 ADC.
    
    This class provides methods to read soil moisture data from a
    capacitive soil moisture sensor connected to an MCP3008 ADC.
    
    The MCP3008 provides 10-bit resolution (0-1023 values).
    Calibration values are used to convert raw readings to percentage.
    
    Attributes:
        channel: ADC channel (0-7)
        spi_bus: SPI bus number
        spi_device: SPI device number
        dry_value: ADC value when sensor is in dry soil
        wet_value: ADC value when sensor is in wet soil
        simulate: If True, generates simulated readings
    
    Example:
        >>> sensor = SoilMoistureSensor(channel=0, simulate=True)
        >>> reading = sensor.read()
        >>> print(f"Soil Moisture: {reading.moisture_percent}%")
    """
    
    # MCP3008 ADC specifications
    ADC_MIN = 0
    ADC_MAX = 1023
    ADC_BITS = 10
    
    def __init__(
        self,
        channel: int = 0,
        spi_bus: int = 0,
        spi_device: int = 0,
        dry_value: int = 1023,
        wet_value: int = 300,
        simulate: bool = False,
        sim_moisture_range: Tuple[float, float] = (30.0, 70.0)
    ):
        """
        Initialize the soil moisture sensor.
        
        Args:
            channel: MCP3008 ADC channel (0-7)
            spi_bus: SPI bus number (default: 0)
            spi_device: SPI device number (default: 0)
            dry_value: ADC reading when completely dry (default: 1023)
            wet_value: ADC reading when submerged in water (default: 300)
            simulate: Enable simulation mode (default: False)
            sim_moisture_range: Moisture range for simulation
        """
        self.channel = channel
        self.spi_bus = spi_bus
        self.spi_device = spi_device
        self.dry_value = dry_value
        self.wet_value = wet_value
        self.simulate = simulate
        self.sim_moisture_range = sim_moisture_range
        
        self._spi = None
        self._last_reading: Optional[SoilMoistureReading] = None
        
        if not simulate:
            self._initialize_hardware()
    
    def _initialize_hardware(self) -> None:
        """Initialize SPI interface for MCP3008 ADC."""
        try:
            import spidev
            self._spi = spidev.SpiDev()
            self._spi.open(self.spi_bus, self.spi_device)
            self._spi.max_speed_hz = 1350000
            logger.info(
                f"MCP3008 ADC initialized on SPI{self.spi_bus}.{self.spi_device}, "
                f"channel {self.channel}"
            )
        except ImportError:
            logger.warning(
                "spidev module not found. "
                "Install with: pip install spidev"
            )
            logger.warning("Falling back to simulation mode")
            self.simulate = True
        except FileNotFoundError:
            logger.warning(
                "SPI device not found. "
                "Ensure SPI is enabled on Raspberry Pi."
            )
            logger.warning("Falling back to simulation mode")
            self.simulate = True
        except Exception as e:
            logger.error(f"Failed to initialize SPI: {e}")
            logger.warning("Falling back to simulation mode")
            self.simulate = True
    
    def _read_adc(self) -> int:
        """
        Read raw value from MCP3008 ADC.
        
        Returns:
            Raw ADC value (0-1023)
        """
        if self._spi is None:
            return 0
        
        # MCP3008 SPI communication
        # Send: [start bit, single-ended + channel, don't care]
        # Receive: [don't care, bit 9-8, bits 7-0]
        cmd = [1, (8 + self.channel) << 4, 0]
        response = self._spi.xfer2(cmd)
        
        # Extract 10-bit value
        value = ((response[1] & 3) << 8) + response[2]
        return value
    
    def _read_simulated(self) -> Tuple[float, int]:
        """
        Generate simulated sensor readings.
        
        Returns:
            Tuple of (moisture_percent, raw_value)
        """
        moisture = random.uniform(*self.sim_moisture_range)
        
        # Add some realistic variation
        moisture = moisture + random.gauss(0, 3)
        moisture = max(0, min(100, moisture))
        
        # Calculate raw value from moisture percentage
        raw_value = int(
            self.dry_value - (moisture / 100) * (self.dry_value - self.wet_value)
        )
        
        return round(moisture, 1), raw_value
    
    def _raw_to_percent(self, raw_value: int) -> float:
        """
        Convert raw ADC value to moisture percentage.
        
        Args:
            raw_value: Raw ADC reading (0-1023)
        
        Returns:
            Moisture percentage (0-100)
        """
        # Invert and scale: lower ADC value = more moisture
        if self.dry_value == self.wet_value:
            return 50.0  # Avoid division by zero
        
        percent = (self.dry_value - raw_value) / (self.dry_value - self.wet_value) * 100
        
        # Clamp to 0-100 range
        return max(0.0, min(100.0, percent))
    
    def _validate_reading(
        self,
        raw_value: int,
        moisture_percent: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate sensor reading.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not (self.ADC_MIN <= raw_value <= self.ADC_MAX):
            return False, f"Raw ADC value {raw_value} out of range"
        
        if not (0 <= moisture_percent <= 100):
            return False, f"Moisture {moisture_percent}% out of valid range"
        
        return True, None
    
    def read(self) -> SoilMoistureReading:
        """
        Read soil moisture from the sensor.
        
        Returns:
            SoilMoistureReading object containing the sensor data
        """
        timestamp = time.time()
        
        if self.simulate:
            moisture_percent, raw_value = self._read_simulated()
            logger.debug(f"Simulated reading: {moisture_percent}% (raw: {raw_value})")
        else:
            raw_value = self._read_adc()
            moisture_percent = self._raw_to_percent(raw_value)
            logger.debug(f"Hardware reading: {moisture_percent}% (raw: {raw_value})")
        
        is_valid, error_message = self._validate_reading(raw_value, moisture_percent)
        
        reading = SoilMoistureReading(
            moisture_percent=round(moisture_percent, 1),
            raw_value=raw_value,
            timestamp=timestamp,
            is_valid=is_valid,
            error_message=error_message
        )
        
        self._last_reading = reading
        
        if not is_valid:
            logger.warning(f"Invalid soil moisture reading: {error_message}")
        else:
            logger.info(f"Soil Moisture: {reading.moisture_percent}%")
        
        return reading
    
    def calibrate(self, dry_value: int = None, wet_value: int = None) -> None:
        """
        Update calibration values.
        
        Args:
            dry_value: New dry calibration value
            wet_value: New wet calibration value
        """
        if dry_value is not None:
            self.dry_value = dry_value
            logger.info(f"Dry calibration value updated to {dry_value}")
        
        if wet_value is not None:
            self.wet_value = wet_value
            logger.info(f"Wet calibration value updated to {wet_value}")
    
    @property
    def last_reading(self) -> Optional[SoilMoistureReading]:
        """Get the most recent reading."""
        return self._last_reading
    
    def to_dict(self, reading: Optional[SoilMoistureReading] = None) -> dict:
        """
        Convert reading to dictionary format for JSON serialization.
        
        Args:
            reading: SoilMoistureReading to convert (uses last_reading if None)
        
        Returns:
            Dictionary representation of the reading
        """
        if reading is None:
            reading = self._last_reading
        
        if reading is None:
            return {}
        
        return {
            "soil_moisture": {
                "value": reading.moisture_percent,
                "unit": "percent",
                "raw_adc": reading.raw_value
            },
            "timestamp": reading.timestamp,
            "is_valid": reading.is_valid,
            "error": reading.error_message
        }
    
    def close(self) -> None:
        """Close the SPI connection."""
        if self._spi is not None:
            self._spi.close()
            logger.info("SPI connection closed")


if __name__ == "__main__":
    # Test the sensor in simulation mode
    logging.basicConfig(level=logging.DEBUG)
    
    sensor = SoilMoistureSensor(simulate=True)
    
    print("Testing Soil Moisture Sensor (Simulation Mode)")
    print("=" * 45)
    
    for i in range(5):
        reading = sensor.read()
        print(f"Reading {i+1}:")
        print(f"  Moisture: {reading.moisture_percent}%")
        print(f"  Raw ADC: {reading.raw_value}")
        print(f"  Valid: {reading.is_valid}")
        print()
        time.sleep(1)
