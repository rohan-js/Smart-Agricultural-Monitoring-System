"""
MQTT Publisher for AWS IoT Core

This module provides a class for publishing sensor data to AWS IoT Core
using MQTT protocol with TLS encryption.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .iot_connection import ConnectionConfig, IoTConnectionHandler

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of a publish operation."""
    success: bool
    topic: str
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = 0.0


class MQTTPublisher:
    """
    MQTT Publisher for AWS IoT Core.
    
    Publishes sensor data and alerts to AWS IoT Core topics.
    Supports JSON message formatting with timestamps and device metadata.
    
    Attributes:
        connection_handler: IoTConnectionHandler instance
        device_id: Device identifier
        qos: MQTT Quality of Service level
    
    Example:
        >>> publisher = MQTTPublisher(connection_handler, device_id="farm-001")
        >>> publisher.publish_telemetry({"temperature": 25.5, "humidity": 60})
    """
    
    def __init__(
        self,
        connection_handler: IoTConnectionHandler,
        device_id: str,
        topic_prefix: str = "agriculture/sensors",
        qos: int = 1,
        retain: bool = False
    ):
        """
        Initialize the MQTT publisher.
        
        Args:
            connection_handler: Configured IoTConnectionHandler
            device_id: Unique device identifier
            topic_prefix: Base topic prefix
            qos: MQTT QoS level (0, 1, or 2)
            retain: Whether to retain messages
        """
        self.connection_handler = connection_handler
        self.device_id = device_id
        self.topic_prefix = topic_prefix
        self.qos = qos
        self.retain = retain
        
        # Topic templates
        self._topics = {
            "telemetry": f"{topic_prefix}/{device_id}/telemetry",
            "status": f"{topic_prefix}/{device_id}/status",
            "alerts": f"{topic_prefix}/{device_id}/alerts"
        }
        
        # Publishing metrics
        self._publish_count = 0
        self._error_count = 0
        self._last_publish_time: Optional[float] = None
    
    @staticmethod
    def format_message(
        data: Dict[str, Any],
        device_id: str = None,
        location: str = None,
        include_timestamp: bool = True
    ) -> str:
        """
        Format sensor data as JSON message.
        
        Args:
            data: Sensor data dictionary
            device_id: Device identifier
            location: Device location
            include_timestamp: Whether to include ISO timestamp
        
        Returns:
            JSON formatted string
        """
        message = {
            "data": data
        }
        
        if device_id:
            message["device_id"] = device_id
        
        if location:
            message["location"] = location
        
        if include_timestamp:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
            message["epoch"] = time.time()
        
        return json.dumps(message, indent=None, separators=(',', ':'))
    
    def _publish(self, topic: str, message: str) -> PublishResult:
        """
        Internal publish method.
        
        Args:
            topic: MQTT topic
            message: JSON message string
        
        Returns:
            PublishResult with status
        """
        timestamp = time.time()
        
        if self.connection_handler.simulate:
            logger.info(f"[SIMULATED] Publishing to {topic}")
            logger.debug(f"Message: {message}")
            self._publish_count += 1
            self._last_publish_time = timestamp
            return PublishResult(
                success=True,
                topic=topic,
                message_id=f"sim-{self._publish_count}",
                timestamp=timestamp
            )
        
        if not self.connection_handler.is_connected:
            logger.error("Not connected to AWS IoT Core")
            self._error_count += 1
            return PublishResult(
                success=False,
                topic=topic,
                error_message="Not connected",
                timestamp=timestamp
            )
        
        try:
            from awscrt.mqtt import QoS
            connection = self.connection_handler.connection
            
            # Convert int to QoS enum
            qos_level = QoS.AT_LEAST_ONCE if self.qos == 1 else QoS.AT_MOST_ONCE
            
            publish_future, packet_id = connection.publish(
                topic=topic,
                payload=message,
                qos=qos_level
            )
            
            # Wait for publish to complete
            publish_future.result(timeout=10)
            
            self._publish_count += 1
            self._last_publish_time = timestamp
            
            logger.info(f"Published to {topic} (packet_id={packet_id})")
            logger.debug(f"Message: {message}")
            
            return PublishResult(
                success=True,
                topic=topic,
                message_id=str(packet_id),
                timestamp=timestamp
            )
            
        except Exception as e:
            logger.error(f"Publish failed: {e}")
            self._error_count += 1
            return PublishResult(
                success=False,
                topic=topic,
                error_message=str(e),
                timestamp=timestamp
            )
    
    def publish_telemetry(
        self,
        sensor_data: Dict[str, Any],
        location: str = None
    ) -> PublishResult:
        """
        Publish telemetry data to AWS IoT Core.
        
        Args:
            sensor_data: Dictionary containing sensor readings
            location: Optional location identifier
        
        Returns:
            PublishResult with status
        """
        message = self.format_message(
            data=sensor_data,
            device_id=self.device_id,
            location=location
        )
        
        return self._publish(self._topics["telemetry"], message)
    
    def publish_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        sensor_data: Dict[str, Any] = None,
        threshold: Dict[str, Any] = None
    ) -> PublishResult:
        """
        Publish an alert to AWS IoT Core.
        
        Args:
            alert_type: Type of alert (e.g., "temperature", "humidity")
            severity: Alert severity ("info", "warning", "critical")
            message: Human-readable alert message
            sensor_data: Current sensor readings
            threshold: Threshold that was exceeded
        
        Returns:
            PublishResult with status
        """
        # Create human-readable alert message for SNS
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        readable_message = f"""
AGRICULTURE ALERT - {severity.upper()}
========================================

Device: {self.device_id}
Time: {timestamp}
Type: {alert_type.replace('_', ' ').title()}

ALERT: {message}
"""
        
        if sensor_data:
            readable_message += "\nCurrent Readings:\n"
            if 'temperature' in sensor_data:
                readable_message += f"   Temperature: {sensor_data['temperature']:.1f}°C\n"
            if 'humidity' in sensor_data:
                readable_message += f"   Humidity: {sensor_data['humidity']:.1f}%\n"
            if 'soil_moisture' in sensor_data:
                readable_message += f"   Soil Moisture: {sensor_data['soil_moisture']:.1f}%\n"
        
        readable_message += "\n========================================\nSmart Agriculture Monitoring System"
        
        # Send plain text for clean SNS emails
        return self._publish(self._topics["alerts"], readable_message)
    
    def publish_status(
        self,
        status: str,
        details: Dict[str, Any] = None
    ) -> PublishResult:
        """
        Publish device status to AWS IoT Core.
        
        Args:
            status: Device status ("online", "offline", "error")
            details: Additional status details
        
        Returns:
            PublishResult with status
        """
        status_data = {
            "status": status,
            "device_id": self.device_id,
            "uptime_seconds": time.time() - self._last_publish_time if self._last_publish_time else 0
        }
        
        if details:
            status_data.update(details)
        
        payload = self.format_message(
            data=status_data,
            device_id=self.device_id
        )
        
        return self._publish(self._topics["status"], payload)
    
    def get_topics(self) -> Dict[str, str]:
        """Get all configured topics."""
        return self._topics.copy()
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get publishing metrics.
        
        Returns:
            Dictionary with publishing statistics
        """
        return {
            "publish_count": self._publish_count,
            "error_count": self._error_count,
            "success_rate": (
                self._publish_count / (self._publish_count + self._error_count)
                if self._publish_count + self._error_count > 0
                else 0.0
            ),
            "last_publish_time": self._last_publish_time
        }


if __name__ == "__main__":
    # Test the MQTT publisher in simulation mode
    logging.basicConfig(level=logging.DEBUG)
    
    # Create simulated connection handler
    config = ConnectionConfig(
        endpoint="test-endpoint.iot.us-east-1.amazonaws.com",
        client_id="test-device-001",
        root_ca_path="certs/AmazonRootCA1.pem",
        cert_path="certs/device.pem.crt",
        key_path="certs/device-private.pem.key"
    )
    
    handler = IoTConnectionHandler(config, simulate=True)
    handler.connect()
    
    publisher = MQTTPublisher(handler, device_id="farm-sensor-001")
    
    print("Testing MQTT Publisher (Simulation Mode)")
    print("=" * 45)
    
    # Test telemetry
    result = publisher.publish_telemetry({
        "temperature": 25.5,
        "humidity": 62.3,
        "soil_moisture": 45.0
    })
    print(f"Telemetry publish: {result.success}")
    
    # Test alert
    result = publisher.publish_alert(
        alert_type="temperature",
        severity="warning",
        message="Temperature above threshold",
        sensor_data={"temperature": 38.5},
        threshold={"max": 35.0}
    )
    print(f"Alert publish: {result.success}")
    
    # Test status
    result = publisher.publish_status("online", {"sensors": ["dht22", "soil_moisture"]})
    print(f"Status publish: {result.success}")
    
    print(f"\nMetrics: {publisher.get_metrics()}")
    
    handler.disconnect()
