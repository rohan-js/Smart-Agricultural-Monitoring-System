"""
Sensor modules for reading environmental data.
"""

from .dht22_sensor import DHT22Sensor
from .soil_moisture import SoilMoistureSensor

__all__ = ["DHT22Sensor", "SoilMoistureSensor"]
