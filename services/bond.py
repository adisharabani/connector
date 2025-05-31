#!/usr/bin/python3

from .connector import Connector
from .service import Service
from logger import get_logger
from shell_listener import ShellListener
import subprocess
import re
from typing import Dict

# Get logger for this module
logger = get_logger(__name__)


class BondDevice(Connector):
    def __init__(self, bond: 'Bond', device_id: str):
        super().__init__()  # Initialize without parameters
        self.bond = bond
        self.device_id = device_id
        self.name = f"Bond<{device_id}>"
        
        # Register the listener for both state updates and action responses
        self.listener = self.bond.listener.filter(f'devices/{device_id}/state.*"power":(?:0|1.*"speed":(0|1|2|3|4|5|6))')
        self.listener.register(self._on_speed_update)
        # self.bond.listener.filter(f'devices/{device_id}/actions/SetSpeed.*"argument":(0|1|2|3|4|5|6)').register(self._on_speed_update)
    
    def _on_speed_update(self, line: str, match: str):
        # Convert from 0-6 range to 0-1 range
        value = round(int(match) / 6.0 *100 )/100.0 if match is not None else 0
        self.set(value, act=False)
        print(f"Speed updated to {value:.2f} (level {match}/6) for device {self.device_id}")
    
    def _set_action(self, value: float) -> None:
        """Override _set_action to send Bond command when value changes"""
        if value == 1.0: # 1.0 (as opposed to 0.99) means someone just wanted to open the device on last level
            cmd = f'sleep 0.1; curl -sS -H "BOND-Token: {self.bond.token}" http://{self.bond.address}/v2/devices/{self.device_id}/actions/TurnOn -X PUT -d "{{}}"'
        elif value == 0:
            cmd = f'sleep 0.1; curl -sS -H "BOND-Token: {self.bond.token}" http://{self.bond.address}/v2/devices/{self.device_id}/actions/TurnOff -X PUT -d "{{}}"'
        else:
            # Convert from 0-1 range to 0-6 range, rounding to nearest integer
            cmd = f'curl -sS -H "BOND-Token: {self.bond.token}" http://{self.bond.address}/v2/devices/{self.device_id}/actions/SetSpeed -X PUT -d "{{\\"argument\\": {round(value * 6)} }}"'
        
        logger.info("Running command: %s", self.bond.reduct(cmd))
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        # The actual speed update will come through the state update listener

class Bond(Service):
    def __init__(self, address: str, port: int, token: str):
        """
        Initialize a Bond connection.
        
        Args:
            address: The IP address of the Bond device
            port: The UDP port to listen on for state updates
            token: The Bond API token
        """
        super().__init__()
        logger.info("Creating Bond service (%s:%d)", address, port)

        self.address = address
        self.port = port
        self.token = token

        self.listener = ShellListener()
        

    def device(self, device_id: str) -> BondDevice:
        return BondDevice(self, device_id)

    def start(self):
        # Create the listener for state updates with a shorter sleep time for more responsive updates
        self.listener.shell_command = f"(while true; do echo ; sleep 60; done) | nc -u {self.address} {self.port}"
        logger.info("Starting Bond listener for %s:%d", self.address, self.port)
        self.listener.start()

    def stop(self):
        """Stop the listener and clean up resources."""
        logger.info("Stopping Bond listener")
        self.listener.stop()

    def reduct(self,x):
        return x.replace(self.token,"<TOKEN>")
