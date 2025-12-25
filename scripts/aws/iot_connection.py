"""
AWS IoT Core Connection Handler

This module manages the connection lifecycle to AWS IoT Core,
including certificate loading, connection establishment, and health monitoring.
"""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConnectionConfig:
    """Configuration for AWS IoT Core connection."""
    endpoint: str
    client_id: str
    root_ca_path: str
    cert_path: str
    key_path: str
    region: str = "us-east-1"
    keep_alive_seconds: int = 30
    ping_timeout_ms: int = 3000
    reconnect_min_seconds: int = 1
    reconnect_max_seconds: int = 128


class IoTConnectionHandler:
    """
    AWS IoT Core Connection Handler.
    
    Manages secure MQTT connections to AWS IoT Core using X.509 certificates.
    Provides connection lifecycle management, health checks, and auto-reconnection.
    
    Attributes:
        config: ConnectionConfig with AWS IoT settings
        is_connected: Current connection status
    
    Example:
        >>> config = ConnectionConfig(
        ...     endpoint="YOUR_ENDPOINT.iot.us-east-1.amazonaws.com",
        ...     client_id="farm-sensor-001",
        ...     root_ca_path="certs/AmazonRootCA1.pem",
        ...     cert_path="certs/device.pem.crt",
        ...     key_path="certs/device-private.pem.key"
        ... )
        >>> handler = IoTConnectionHandler(config)
        >>> handler.connect()
    """
    
    def __init__(
        self,
        config: ConnectionConfig,
        on_connection_success: Optional[Callable] = None,
        on_connection_failure: Optional[Callable] = None,
        on_connection_interrupted: Optional[Callable] = None,
        on_connection_resumed: Optional[Callable] = None,
        simulate: bool = False
    ):
        """
        Initialize the IoT connection handler.
        
        Args:
            config: Connection configuration
            on_connection_success: Callback for successful connection
            on_connection_failure: Callback for connection failure
            on_connection_interrupted: Callback when connection is interrupted
            on_connection_resumed: Callback when connection is resumed
            simulate: If True, simulate connection without actual AWS connection
        """
        self.config = config
        self.simulate = simulate
        self._is_connected = False
        self._connection = None
        self._mqtt_client = None
        
        # Callbacks
        self._on_connection_success = on_connection_success
        self._on_connection_failure = on_connection_failure
        self._on_connection_interrupted = on_connection_interrupted
        self._on_connection_resumed = on_connection_resumed
        
        # Connection metrics
        self._connection_attempts = 0
        self._last_connection_time: Optional[float] = None
        self._last_disconnect_time: Optional[float] = None
    
    def _validate_certificates(self) -> bool:
        """
        Validate that all required certificate files exist.
        
        Returns:
            True if all certificates are present, False otherwise
        """
        cert_files = [
            ("Root CA", self.config.root_ca_path),
            ("Device Certificate", self.config.cert_path),
            ("Private Key", self.config.key_path)
        ]
        
        all_valid = True
        for name, path in cert_files:
            if not os.path.exists(path):
                logger.error(f"{name} not found: {path}")
                all_valid = False
            else:
                logger.debug(f"{name} found: {path}")
        
        return all_valid
    
    def _build_connection(self):
        """Build AWS IoT Core MQTT connection."""
        try:
            from awscrt import io, mqtt
            from awsiot import mqtt_connection_builder
            
            # Create event loop group
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
            
            # Build MQTT connection
            self._connection = mqtt_connection_builder.mtls_from_path(
                endpoint=self.config.endpoint,
                cert_filepath=self.config.cert_path,
                pri_key_filepath=self.config.key_path,
                ca_filepath=self.config.root_ca_path,
                client_bootstrap=client_bootstrap,
                client_id=self.config.client_id,
                clean_session=False,
                keep_alive_secs=self.config.keep_alive_seconds,
                on_connection_interrupted=self._handle_connection_interrupted,
                on_connection_resumed=self._handle_connection_resumed
            )
            
            return True
            
        except ImportError:
            logger.error(
                "AWS IoT SDK not found. "
                "Install with: pip install awsiotsdk"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to build connection: {e}")
            return False
    
    def _handle_connection_interrupted(self, connection, error, **kwargs):
        """Handle connection interruption."""
        self._is_connected = False
        self._last_disconnect_time = time.time()
        logger.warning(f"Connection interrupted: {error}")
        
        if self._on_connection_interrupted:
            self._on_connection_interrupted(error)
    
    def _handle_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """Handle connection resumption."""
        self._is_connected = True
        self._last_connection_time = time.time()
        logger.info(f"Connection resumed (session_present={session_present})")
        
        if self._on_connection_resumed:
            self._on_connection_resumed(return_code, session_present)
    
    def connect(self) -> bool:
        """
        Establish connection to AWS IoT Core.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self.simulate:
            logger.info("Simulating AWS IoT connection")
            self._is_connected = True
            self._last_connection_time = time.time()
            return True
        
        self._connection_attempts += 1
        
        # Validate certificates
        if not self._validate_certificates():
            logger.error("Certificate validation failed")
            if self._on_connection_failure:
                self._on_connection_failure("Certificate validation failed")
            return False
        
        # Build connection if not already built
        if self._connection is None:
            if not self._build_connection():
                return False
        
        try:
            logger.info(f"Connecting to {self.config.endpoint}...")
            connect_future = self._connection.connect()
            connect_future.result()
            
            self._is_connected = True
            self._last_connection_time = time.time()
            logger.info("Successfully connected to AWS IoT Core")
            
            if self._on_connection_success:
                self._on_connection_success()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._is_connected = False
            
            if self._on_connection_failure:
                self._on_connection_failure(str(e))
            
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from AWS IoT Core.
        
        Returns:
            True if disconnection successful, False otherwise
        """
        if self.simulate:
            logger.info("Simulating AWS IoT disconnection")
            self._is_connected = False
            self._last_disconnect_time = time.time()
            return True
        
        if self._connection is None:
            return True
        
        try:
            disconnect_future = self._connection.disconnect()
            disconnect_future.result()
            
            self._is_connected = False
            self._last_disconnect_time = time.time()
            logger.info("Disconnected from AWS IoT Core")
            return True
            
        except Exception as e:
            logger.error(f"Disconnection error: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test the connection to AWS IoT Core.
        
        Returns:
            True if connection test successful, False otherwise
        """
        if self.simulate:
            logger.info("Connection test simulated: OK")
            return True
        
        if not self._validate_certificates():
            logger.error("Connection test failed: Invalid certificates")
            return False
        
        if self.connect():
            logger.info("Connection test: OK")
            self.disconnect()
            return True
        
        logger.error("Connection test: FAILED")
        return False
    
    @property
    def is_connected(self) -> bool:
        """Get current connection status."""
        return self._is_connected
    
    @property
    def connection(self):
        """Get the MQTT connection object."""
        return self._connection
    
    def get_status(self) -> dict:
        """
        Get connection status information.
        
        Returns:
            Dictionary with connection status details
        """
        return {
            "is_connected": self._is_connected,
            "endpoint": self.config.endpoint,
            "client_id": self.config.client_id,
            "connection_attempts": self._connection_attempts,
            "last_connection_time": self._last_connection_time,
            "last_disconnect_time": self._last_disconnect_time,
            "simulate_mode": self.simulate
        }


def load_config_from_yaml(config_path: str, project_root: str = None) -> ConnectionConfig:
    """
    Load connection configuration from YAML file.
    
    Args:
        config_path: Path to config.yaml
        project_root: Project root directory for resolving relative paths
    
    Returns:
        ConnectionConfig object
    """
    import yaml
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if project_root is None:
        project_root = Path(config_path).parent.parent
    
    aws_config = config.get('aws_iot', {})
    certs = aws_config.get('certificates', {})
    conn = aws_config.get('connection', {})
    
    return ConnectionConfig(
        endpoint=aws_config.get('endpoint', ''),
        client_id=config.get('device', {}).get('id', 'default-device'),
        root_ca_path=str(Path(project_root) / certs.get('root_ca', '')),
        cert_path=str(Path(project_root) / certs.get('device_cert', '')),
        key_path=str(Path(project_root) / certs.get('private_key', '')),
        region=aws_config.get('region', 'us-east-1'),
        keep_alive_seconds=conn.get('keep_alive_seconds', 30),
        ping_timeout_ms=conn.get('ping_timeout_ms', 3000),
        reconnect_min_seconds=conn.get('reconnect_min_seconds', 1),
        reconnect_max_seconds=conn.get('reconnect_max_seconds', 128)
    )


if __name__ == "__main__":
    # Test the connection handler in simulation mode
    logging.basicConfig(level=logging.DEBUG)
    
    config = ConnectionConfig(
        endpoint="test-endpoint.iot.us-east-1.amazonaws.com",
        client_id="test-device-001",
        root_ca_path="certs/AmazonRootCA1.pem",
        cert_path="certs/device.pem.crt",
        key_path="certs/device-private.pem.key"
    )
    
    handler = IoTConnectionHandler(config, simulate=True)
    
    print("Testing IoT Connection Handler (Simulation Mode)")
    print("=" * 50)
    
    # Test connection
    if handler.connect():
        print("Connection successful!")
        print(f"Status: {handler.get_status()}")
        handler.disconnect()
        print("Disconnected.")
    else:
        print("Connection failed!")
