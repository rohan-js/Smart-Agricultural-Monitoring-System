"""
DHT22 Temperature and Humidity Sensor Module

This module provides a class for reading temperature and humidity data
from a DHT22 sensor connected to a Raspberry Pi GPIO pin.

Supports simulation mode for testing without hardware.
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DHT22Reading:
    """Data class representing a DHT22 sensor reading."""
    temperature: float  # Celsius
    humidity: float     # Percentage
    timestamp: float    # Unix timestamp
    is_valid: bool      # Whether reading passed validation
    error_message: Optional[str] = None


class DHT22Sensor:
    """
    DHT22 Temperature and Humidity Sensor Interface.
    
    This class provides methods to read temperature and humidity data
    from a DHT22 sensor. It supports both hardware mode (Raspberry Pi)
    and simulation mode for testing.
    
    Attributes:
        gpio_pin: BCM GPIO pin number where sensor is connected
        simulate: If True, generates simulated readings
        retry_count: Number of retries on failed readings
        retry_delay: Delay between retries in seconds
    
    Example:
        >>> sensor = DHT22Sensor(gpio_pin=4, simulate=True)
        >>> reading = sensor.read()
        >>> print(f"Temperature: {reading.temperature}°C")
    """
    
    # Valid ranges for DHT22 sensor
    TEMP_MIN = -40.0
    TEMP_MAX = 80.0
    HUMIDITY_MIN = 0.0
    HUMIDITY_MAX = 100.0
    
    def __init__(
        self,
        gpio_pin: int = 4,
        simulate: bool = False,
        retry_count: int = 3,
        retry_delay: float = 2.0,
        sim_temp_range: Tuple[float, float] = (20.0, 35.0),
        sim_humidity_range: Tuple[float, float] = (40.0, 80.0)
    ):
        """
        Initialize the DHT22 sensor.
        
        Args:
            gpio_pin: BCM GPIO pin number (default: 4)
            simulate: Enable simulation mode (default: False)
            retry_count: Number of read retries (default: 3)
            retry_delay: Delay between retries in seconds (default: 2.0)
            sim_temp_range: Temperature range for simulation
            sim_humidity_range: Humidity range for simulation
        """
        self.gpio_pin = gpio_pin
        self.simulate = simulate
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.sim_temp_range = sim_temp_range
        self.sim_humidity_range = sim_humidity_range
        
        self._dht_module = None
        self._last_reading: Optional[DHT22Reading] = None
        
        if not simulate:
            self._initialize_hardware()
    
    def _initialize_hardware(self) -> None:
        """Initialize hardware interface for DHT22 sensor."""
        try:
            import Adafruit_DHT
            self._dht_module = Adafruit_DHT
            self._sensor_type = Adafruit_DHT.DHT22
            logger.info(f"DHT22 sensor initialized on GPIO pin {self.gpio_pin}")
        except ImportError:
            logger.warning(
                "Adafruit_DHT module not found. "
                "Install with: pip install Adafruit-DHT"
            )
            logger.warning("Falling back to simulation mode")
            self.simulate = True
        except Exception as e:
            logger.error(f"Failed to initialize DHT22 hardware: {e}")
            logger.warning("Falling back to simulation mode")
            self.simulate = True
    
    def _read_hardware(self) -> Tuple[Optional[float], Optional[float]]:
        """Read temperature and humidity from hardware sensor."""
        if self._dht_module is None:
            return None, None
        
        humidity, temperature = self._dht_module.read_retry(
            self._sensor_type,
            self.gpio_pin,
            retries=self.retry_count,
            delay_seconds=self.retry_delay
        )
        return humidity, temperature
    
    def _read_simulated(self) -> Tuple[float, float]:
        """Generate simulated sensor readings."""
        temperature = random.uniform(*self.sim_temp_range)
        humidity = random.uniform(*self.sim_humidity_range)
        
        # Add some realistic variation
        temperature = round(temperature + random.gauss(0, 0.5), 1)
        humidity = round(humidity + random.gauss(0, 2), 1)
        
        # Clamp to valid ranges
        temperature = max(self.TEMP_MIN, min(self.TEMP_MAX, temperature))
        humidity = max(self.HUMIDITY_MIN, min(self.HUMIDITY_MAX, humidity))
        
        return humidity, temperature
    
    def _validate_reading(
        self,
        temperature: Optional[float],
        humidity: Optional[float]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate sensor reading against acceptable ranges.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if temperature is None or humidity is None:
            return False, "Failed to read sensor data"
        
        if not (self.TEMP_MIN <= temperature <= self.TEMP_MAX):
            return False, f"Temperature {temperature}°C out of valid range"
        
        if not (self.HUMIDITY_MIN <= humidity <= self.HUMIDITY_MAX):
            return False, f"Humidity {humidity}% out of valid range"
        
        return True, None
    
    def read(self) -> DHT22Reading:
        """
        Read temperature and humidity from the sensor.
        
        Returns:
            DHT22Reading object containing the sensor data
        """
        timestamp = time.time()
        
        if self.simulate:
            humidity, temperature = self._read_simulated()
            logger.debug(f"Simulated reading: {temperature}°C, {humidity}%")
        else:
            humidity, temperature = self._read_hardware()
            logger.debug(f"Hardware reading: {temperature}°C, {humidity}%")
        
        is_valid, error_message = self._validate_reading(temperature, humidity)
        
        reading = DHT22Reading(
            temperature=round(temperature, 1) if temperature else 0.0,
            humidity=round(humidity, 1) if humidity else 0.0,
            timestamp=timestamp,
            is_valid=is_valid,
            error_message=error_message
        )
        
        self._last_reading = reading
        
        if not is_valid:
            logger.warning(f"Invalid DHT22 reading: {error_message}")
        else:
            logger.info(
                f"DHT22: Temperature={reading.temperature}°C, "
                f"Humidity={reading.humidity}%"
            )
        
        return reading
    
    @property
    def last_reading(self) -> Optional[DHT22Reading]:
        """Get the most recent reading."""
        return self._last_reading
    
    def to_dict(self, reading: Optional[DHT22Reading] = None) -> dict:
        """
        Convert reading to dictionary format for JSON serialization.
        
        Args:
            reading: DHT22Reading to convert (uses last_reading if None)
        
        Returns:
            Dictionary representation of the reading
        """
        if reading is None:
            reading = self._last_reading
        
        if reading is None:
            return {}
        
        return {
            "temperature": {
                "value": reading.temperature,
                "unit": "celsius"
            },
            "humidity": {
                "value": reading.humidity,
                "unit": "percent"
            },
            "timestamp": reading.timestamp,
            "is_valid": reading.is_valid,
            "error": reading.error_message
        }


if __name__ == "__main__":
    # Test the sensor in simulation mode
    logging.basicConfig(level=logging.DEBUG)
    
    sensor = DHT22Sensor(simulate=True)
    
    print("Testing DHT22 Sensor (Simulation Mode)")
    print("=" * 40)
    
    for i in range(5):
        reading = sensor.read()
        print(f"Reading {i+1}:")
        print(f"  Temperature: {reading.temperature}°C")
        print(f"  Humidity: {reading.humidity}%")
        print(f"  Valid: {reading.is_valid}")
        print()
        time.sleep(1)
