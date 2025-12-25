"""
Smart Agriculture Monitoring System - Main Application

This is the main entry point for the agricultural monitoring system.
It orchestrates sensor reading, data publishing, and alert generation.

Usage:
    python -m scripts.main                    # Run with hardware
    python -m scripts.main --simulate         # Run in simulation mode
    python -m scripts.main --test-connection  # Test AWS IoT connection
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.sensors import DHT22Sensor, SoilMoistureSensor
from scripts.aws import MQTTPublisher
from scripts.aws.iot_connection import (
    ConnectionConfig,
    IoTConnectionHandler,
    load_config_from_yaml
)

# CloudWatch metrics client
try:
    import boto3
    CLOUDWATCH_AVAILABLE = True
except ImportError:
    CLOUDWATCH_AVAILABLE = False


class AlertManager:
    """Manages threshold-based alerting for sensor data."""
    
    def __init__(self, thresholds_path: str):
        """Load alert thresholds from YAML file."""
        with open(thresholds_path, 'r') as f:
            self.thresholds = yaml.safe_load(f)
        
        self._alert_history: Dict[str, float] = {}
        self._consecutive_counts: Dict[str, int] = {}
        self.cooldown_seconds = self.thresholds.get('alerts', {}).get('cooldown_seconds', 300)
        self.consecutive_required = self.thresholds.get('alerts', {}).get('consecutive_readings', 2)
    
    def check_thresholds(self, sensor_data: Dict[str, Any]) -> list:
        """
        Check sensor data against thresholds and return any alerts.
        
        Returns:
            List of alert dictionaries
        """
        alerts = []
        current_time = time.time()
        
        # Check temperature
        if 'temperature' in sensor_data:
            temp = sensor_data['temperature']
            temp_thresholds = self.thresholds.get('temperature', {})
            
            alert = self._check_value(
                'temperature', temp, temp_thresholds, current_time, '°C'
            )
            if alert:
                alerts.append(alert)
        
        # Check humidity
        if 'humidity' in sensor_data:
            humidity = sensor_data['humidity']
            humidity_thresholds = self.thresholds.get('humidity', {})
            
            alert = self._check_value(
                'humidity', humidity, humidity_thresholds, current_time, '%'
            )
            if alert:
                alerts.append(alert)
        
        # Check soil moisture
        if 'soil_moisture' in sensor_data:
            moisture = sensor_data['soil_moisture']
            moisture_thresholds = self.thresholds.get('soil_moisture', {})
            
            alert = self._check_value(
                'soil_moisture', moisture, moisture_thresholds, current_time, '%'
            )
            if alert:
                alerts.append(alert)
        
        return alerts
    
    def _check_value(
        self,
        metric: str,
        value: float,
        thresholds: dict,
        current_time: float,
        unit: str
    ) -> Optional[dict]:
        """Check a single value against its thresholds."""
        warning = thresholds.get('warning', {})
        critical = thresholds.get('critical', {})
        
        severity = None
        threshold_info = {}
        
        # Check critical first (more severe)
        if critical:
            if value < critical.get('min', float('-inf')):
                severity = 'critical'
                threshold_info = {'type': 'min', 'value': critical['min']}
            elif value > critical.get('max', float('inf')):
                severity = 'critical'
                threshold_info = {'type': 'max', 'value': critical['max']}
        
        # Check warning if not critical
        if not severity and warning:
            if value < warning.get('min', float('-inf')):
                severity = 'warning'
                threshold_info = {'type': 'min', 'value': warning['min']}
            elif value > warning.get('max', float('inf')):
                severity = 'warning'
                threshold_info = {'type': 'max', 'value': warning['max']}
        
        if not severity:
            self._consecutive_counts[metric] = 0
            return None
        
        # Track consecutive readings
        self._consecutive_counts[metric] = self._consecutive_counts.get(metric, 0) + 1
        
        if self._consecutive_counts[metric] < self.consecutive_required:
            return None
        
        # Check cooldown
        alert_key = f"{metric}_{severity}"
        last_alert = self._alert_history.get(alert_key, 0)
        
        if current_time - last_alert < self.cooldown_seconds:
            return None
        
        # Generate alert
        self._alert_history[alert_key] = current_time
        
        comparison = 'below' if threshold_info['type'] == 'min' else 'above'
        message = f"{metric.replace('_', ' ').title()} is {comparison} {severity} threshold: {value}{unit} (threshold: {threshold_info['value']}{unit})"
        
        return {
            'alert_type': metric,
            'severity': severity,
            'message': message,
            'value': value,
            'threshold': threshold_info
        }


class AgriculturalMonitor:
    """Main monitoring system orchestrator."""
    
    def __init__(
        self,
        config_path: str,
        thresholds_path: str,
        simulate: bool = False,
        log_level: str = "INFO"
    ):
        """
        Initialize the agricultural monitoring system.
        
        Args:
            config_path: Path to config.yaml
            thresholds_path: Path to thresholds.yaml
            simulate: Enable simulation mode
            log_level: Logging level
        """
        self.project_root = Path(config_path).parent.parent
        self.simulate = simulate
        self.running = False
        
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Override simulation mode if requested
        if simulate:
            self.config['simulation']['enabled'] = True
        
        self.simulate = self.config.get('simulation', {}).get('enabled', False)
        
        # Setup logging
        self._setup_logging(log_level)
        
        # Initialize components
        self._init_sensors()
        self._init_aws_connection()
        self.alert_manager = AlertManager(thresholds_path)
        
        # Publishing settings
        self.publish_interval = self.config.get('publishing', {}).get('interval_seconds', 30)
        
        # Device info
        device_config = self.config.get('device', {})
        self.device_id = device_config.get('id', 'unknown-device')
        self.location = device_config.get('location', 'unknown')
        
        # Initialize CloudWatch client
        self._init_cloudwatch()
        
        self.logger.info(f"Agricultural Monitor initialized (simulate={self.simulate})")
    
    def _init_cloudwatch(self) -> None:
        """Initialize CloudWatch metrics client."""
        self.cloudwatch_client = None
        cw_config = self.config.get('cloudwatch', {})
        
        if not cw_config.get('enabled', True):
            self.logger.info("CloudWatch metrics disabled in config")
            return
        
        if not CLOUDWATCH_AVAILABLE:
            self.logger.warning("boto3 not installed, CloudWatch metrics disabled")
            return
        
        try:
            region = self.config.get('aws_iot', {}).get('region', 'eu-north-1')
            self.cloudwatch_client = boto3.client('cloudwatch', region_name=region)
            self.cloudwatch_namespace = cw_config.get('namespace', 'SmartAgriculture')
            self.logger.info(f"CloudWatch client initialized (namespace={self.cloudwatch_namespace})")
        except Exception as e:
            self.logger.warning(f"Failed to initialize CloudWatch client: {e}")
            self.cloudwatch_client = None
    
    def publish_cloudwatch_metrics(self, sensor_data: Dict[str, Any]) -> bool:
        """Publish sensor data to CloudWatch metrics."""
        if self.cloudwatch_client is None:
            return False
        
        try:
            metric_data = []
            timestamp = datetime.now(timezone.utc)
            
            if 'temperature' in sensor_data:
                metric_data.append({
                    'MetricName': 'Temperature',
                    'Value': sensor_data['temperature'],
                    'Unit': 'None',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'DeviceId', 'Value': self.device_id},
                        {'Name': 'Location', 'Value': self.location}
                    ]
                })
            
            if 'humidity' in sensor_data:
                metric_data.append({
                    'MetricName': 'Humidity',
                    'Value': sensor_data['humidity'],
                    'Unit': 'Percent',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'DeviceId', 'Value': self.device_id},
                        {'Name': 'Location', 'Value': self.location}
                    ]
                })
            
            if 'soil_moisture' in sensor_data:
                metric_data.append({
                    'MetricName': 'SoilMoisture',
                    'Value': sensor_data['soil_moisture'],
                    'Unit': 'Percent',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'DeviceId', 'Value': self.device_id},
                        {'Name': 'Location', 'Value': self.location}
                    ]
                })
            
            if metric_data:
                self.cloudwatch_client.put_metric_data(
                    Namespace=self.cloudwatch_namespace,
                    MetricData=metric_data
                )
                self.logger.debug(f"Published {len(metric_data)} metrics to CloudWatch")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to publish CloudWatch metrics: {e}")
            return False
    
    def _setup_logging(self, log_level: str) -> None:
        """Configure logging with file and console handlers."""
        log_config = self.config.get('logging', {})
        
        # Create logger
        self.logger = logging.getLogger('agricultural_monitor')
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        # Console handler
        if log_config.get('console', {}).get('enabled', True):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(console_handler)
        
        # File handler
        if log_config.get('file', {}).get('enabled', True):
            log_path = Path(self.project_root) / log_config.get('file', {}).get('path', 'logs/monitoring.log')
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=log_config.get('file', {}).get('max_bytes', 10485760),
                backupCount=log_config.get('file', {}).get('backup_count', 5)
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(file_handler)
    
    def _init_sensors(self) -> None:
        """Initialize sensor objects."""
        sim_config = self.config.get('simulation', {})
        dht_config = self.config.get('sensors', {}).get('dht22', {})
        soil_config = self.config.get('sensors', {}).get('soil_moisture', {})
        
        # DHT22 sensor
        self.dht22 = DHT22Sensor(
            gpio_pin=dht_config.get('gpio_pin', 4),
            simulate=self.simulate,
            retry_count=dht_config.get('retry_count', 3),
            retry_delay=dht_config.get('retry_delay_seconds', 2),
            sim_temp_range=tuple(sim_config.get('temperature_range', [20, 35])),
            sim_humidity_range=tuple(sim_config.get('humidity_range', [40, 80]))
        )
        
        # Soil moisture sensor
        calibration = soil_config.get('calibration', {})
        self.soil_moisture = SoilMoistureSensor(
            channel=soil_config.get('adc_channel', 0),
            spi_bus=soil_config.get('spi_bus', 0),
            spi_device=soil_config.get('spi_device', 0),
            dry_value=calibration.get('dry_value', 1023),
            wet_value=calibration.get('wet_value', 300),
            simulate=self.simulate,
            sim_moisture_range=tuple(sim_config.get('soil_moisture_range', [30, 70]))
        )
        
        self.logger.info("Sensors initialized")
    
    def _init_aws_connection(self) -> None:
        """Initialize AWS IoT connection and publisher."""
        aws_config = self.config.get('aws_iot', {})
        certs = aws_config.get('certificates', {})
        conn_config = aws_config.get('connection', {})
        
        connection_config = ConnectionConfig(
            endpoint=aws_config.get('endpoint', ''),
            client_id=self.config.get('device', {}).get('id', 'default-device'),
            root_ca_path=str(self.project_root / certs.get('root_ca', '')),
            cert_path=str(self.project_root / certs.get('device_cert', '')),
            key_path=str(self.project_root / certs.get('private_key', '')),
            region=aws_config.get('region', 'us-east-1'),
            keep_alive_seconds=conn_config.get('keep_alive_seconds', 30)
        )
        
        self.connection_handler = IoTConnectionHandler(
            connection_config,
            simulate=self.simulate,
            on_connection_success=lambda: self.logger.info("Connected to AWS IoT"),
            on_connection_failure=lambda e: self.logger.error(f"Connection failed: {e}"),
            on_connection_interrupted=lambda e: self.logger.warning(f"Connection interrupted: {e}"),
            on_connection_resumed=lambda *args: self.logger.info("Connection resumed")
        )
        
        # Get topic configuration
        topics = aws_config.get('topics', {})
        topic_prefix = '/'.join(topics.get('telemetry', 'agriculture/sensors/{device_id}/telemetry').split('/')[:-2])
        
        pub_config = self.config.get('publishing', {})
        self.publisher = MQTTPublisher(
            self.connection_handler,
            device_id=self.config.get('device', {}).get('id', 'default-device'),
            topic_prefix=topic_prefix,
            qos=pub_config.get('qos', 1),
            retain=pub_config.get('retain', False)
        )
        
        self.logger.info("AWS IoT connection configured")
    
    def read_sensors(self) -> Dict[str, Any]:
        """Read all sensor data."""
        data = {}
        
        # Read DHT22
        dht_reading = self.dht22.read()
        if dht_reading.is_valid:
            data['temperature'] = dht_reading.temperature
            data['humidity'] = dht_reading.humidity
        
        # Read soil moisture
        soil_reading = self.soil_moisture.read()
        if soil_reading.is_valid:
            data['soil_moisture'] = soil_reading.moisture_percent
        
        return data
    
    def run(self, duration: Optional[int] = None, force_alert: bool = False) -> None:
        """
        Run the monitoring loop.
        
        Args:
            duration: Optional duration in seconds (None = run indefinitely)
            force_alert: Force an alert for testing
        """
        self.running = True
        start_time = time.time()
        
        # Connect to AWS IoT
        if not self.connection_handler.connect():
            self.logger.error("Failed to connect to AWS IoT Core")
            if not self.simulate:
                return
        
        # Publish online status
        self.publisher.publish_status("online", {
            "sensors": ["dht22", "soil_moisture"],
            "location": self.location
        })
        
        self.logger.info(f"Starting monitoring loop (interval={self.publish_interval}s)")
        
        try:
            iteration = 0
            while self.running:
                iteration += 1
                
                # Check duration limit
                if duration and (time.time() - start_time) >= duration:
                    self.logger.info(f"Duration limit ({duration}s) reached")
                    break
                
                # Read sensors
                sensor_data = self.read_sensors()
                
                if sensor_data:
                    self.logger.info(f"Sensor readings: {sensor_data}")
                    
                    # Publish telemetry
                    result = self.publisher.publish_telemetry(sensor_data, self.location)
                    if result.success:
                        self.logger.debug(f"Telemetry published to {result.topic}")
                    
                    # Publish to CloudWatch metrics
                    self.publish_cloudwatch_metrics(sensor_data)
                    
                    # Check for alerts
                    alerts = self.alert_manager.check_thresholds(sensor_data)
                    
                    # Force alert for testing
                    if force_alert and iteration == 1:
                        alerts.append({
                            'alert_type': 'test',
                            'severity': 'warning',
                            'message': 'This is a test alert',
                            'value': 0,
                            'threshold': {'type': 'test', 'value': 0}
                        })
                    
                    for alert in alerts:
                        self.logger.warning(f"ALERT: {alert['message']}")
                        self.publisher.publish_alert(
                            alert_type=alert['alert_type'],
                            severity=alert['severity'],
                            message=alert['message'],
                            sensor_data=sensor_data,
                            threshold=alert['threshold']
                        )
                else:
                    self.logger.warning("No valid sensor data available")
                
                # Wait for next interval
                time.sleep(self.publish_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the monitoring loop and cleanup."""
        self.running = False
        
        # Publish offline status
        if self.connection_handler.is_connected:
            self.publisher.publish_status("offline")
        
        # Disconnect from AWS IoT
        self.connection_handler.disconnect()
        
        # Close soil moisture SPI connection
        self.soil_moisture.close()
        
        self.logger.info("Agricultural Monitor stopped")
        
        # Print metrics
        metrics = self.publisher.get_metrics()
        self.logger.info(f"Publishing metrics: {metrics}")
    
    def test_connection(self) -> bool:
        """Test AWS IoT connection."""
        return self.connection_handler.test_connection()


def setup_signal_handlers(monitor: AgriculturalMonitor) -> None:
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        print("\nShutdown signal received...")
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Smart Agriculture Monitoring System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.main                      Run with hardware
  python -m scripts.main --simulate           Run in simulation mode
  python -m scripts.main --simulate --duration 60  Run simulation for 60 seconds
  python -m scripts.main --test-connection    Test AWS IoT connection
  python -m scripts.main --simulate --force-alert  Test alert system
        """
    )
    
    parser.add_argument(
        '--simulate', '-s',
        action='store_true',
        help='Run in simulation mode (no hardware required)'
    )
    
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=None,
        help='Run for specified duration in seconds (default: indefinite)'
    )
    
    parser.add_argument(
        '--test-connection', '-t',
        action='store_true',
        help='Test AWS IoT connection and exit'
    )
    
    parser.add_argument(
        '--force-alert', '-a',
        action='store_true',
        help='Force a test alert on first reading'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to config.yaml'
    )
    
    parser.add_argument(
        '--log-level', '-l',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Determine paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    config_path = args.config or str(project_root / 'config' / 'config.yaml')
    thresholds_path = str(project_root / 'config' / 'thresholds.yaml')
    
    # Validate config files exist
    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found: {config_path}")
        sys.exit(1)
    
    if not os.path.exists(thresholds_path):
        print(f"Error: Thresholds file not found: {thresholds_path}")
        sys.exit(1)
    
    # Create monitor
    monitor = AgriculturalMonitor(
        config_path=config_path,
        thresholds_path=thresholds_path,
        simulate=args.simulate,
        log_level=args.log_level
    )
    
    # Setup signal handlers
    setup_signal_handlers(monitor)
    
    # Test connection mode
    if args.test_connection:
        print("Testing AWS IoT connection...")
        if monitor.test_connection():
            print("✓ AWS IoT Core connection successful!")
            sys.exit(0)
        else:
            print("✗ AWS IoT Core connection failed!")
            sys.exit(1)
    
    # Run monitoring loop
    print(f"Starting Smart Agriculture Monitoring System...")
    print(f"  Device ID: {monitor.device_id}")
    print(f"  Location: {monitor.location}")
    print(f"  Simulation Mode: {monitor.simulate}")
    print(f"  Publish Interval: {monitor.publish_interval}s")
    if args.duration:
        print(f"  Duration: {args.duration}s")
    print()
    print("Press Ctrl+C to stop...")
    print()
    
    monitor.run(duration=args.duration, force_alert=args.force_alert)


if __name__ == "__main__":
    main()
