#!/usr/bin/python3

import sys
import time
import threading
import socket
import re

from typing import List, Optional

from .connector import Connector
from .service import Service
from logger import get_logger

# Get logger for this module
logger = get_logger(__name__)

class LutronConnector(Connector):
    """Base class for Lutron-specific connectors that need to process events."""
    
    def process_event(self, line: str) -> None:
        pass

    def safely_process_event(self, line: str) -> bool:
        try:
            return self.process_event(line)
        except Exception as e:
            import traceback
            logger.error(f"Error processing event in {self.name}: {str(e)}\n{traceback.format_exc()}")
            return False


class LutronDevice(LutronConnector):
    def __init__(self, lutron: 'Lutron', device_id: int):
        super().__init__()  # Initialize with no value
        self.lutron = lutron
        self.device_id = device_id
        self.name = f"LutronDevice<{device_id}>"
        self.lutron.register_handler(self)
    
    def _set_action(self, value: float) -> None:
        """Override _set_action to send Lutron command when value changes"""
        # Convert from our 0-1 range to Lutron's 0-100 range
        self.lutron.send_command(f"#OUTPUT,{self.device_id},1,{(value * 100):.2f}")

    def process_event(self, line: str) -> None:
        """Process OUTPUT events for this device."""
        # OUTPUT event: ~OUTPUT,device_id,1,value
        if m := re.match(rf"~OUTPUT,{self.device_id},1,(\d+)", line):
            value = int(m.group(1))
            self.set(value / 100.0, act=False)
            return True

class LutronSysvar(LutronConnector):
    def __init__(self, lutron: 'Lutron', sysvar_id: int):
        super().__init__()  # Initialize with no value
        self.lutron = lutron
        self.sysvar_id = sysvar_id
        self.name = f"LutronSysvar<{sysvar_id}>"
        self.lutron.register_handler(self)
    
    def _set_action(self, value: int) -> None:
        """Override _set_action to send Lutron command when value changes"""
        self.lutron.send_command(f"#SYSVAR,{self.sysvar_id},1,{value}")
      
    def process_event(self, line: str) -> None:
        """Process SYSVAR events for this sysvar."""
        # SYSVAR event: ~SYSVAR,sysvar_id,1,value
        if m := re.match(rf"~SYSVAR,{self.sysvar_id},1,(\d+)", line):
            value = int(m.group(1))
            self.set(value, act=False)
            return True

class LutronKeypad(LutronConnector):
    def __init__(self, lutron: 'Lutron', keypad_id: int, button_id: int, click_type=3):
        # Click types: 3=press, 4=release, 5=long press, 6=double press
        super().__init__()  # Initialize with no value
        self.lutron = lutron
        self.keypad_id = keypad_id
        self.button_id = button_id
        self.click_type = click_type
        self._value = False
        self.name = f"LutronKeypad<{keypad_id}, {button_id}, {click_type}>"

        self.lutron.register_handler(self)
        
    def _set_action(self, value: bool) -> None:
        """Override _set_action to send Lutron command when value changes"""
        if value:  # Only send command on press (True)
            cmd = f"#DEVICE,{self.keypad_id},{self.button_id},{self.click_type}"
            logger.debug("Running command: %s", cmd)
            self.lutron.send_command(cmd)
            self._value = False

    def process_event(self, line: str) -> None:
        """Process DEVICE events for this keypad button."""
        # DEVICE event: ~DEVICE,keypad_id,button_id,event_type
        if m := re.match(rf"~DEVICE,{self.keypad_id},{self.button_id},{self.click_type}", line):
            self.set(True, act=False)
            return True

class ToggleCommand(LutronConnector):
    def __init__(self,lutron,cmd_on=None, cmd_off=None):
        super().__init__()  # Initialize with no value
        self.cmd_on = cmd_on
        self.cmd_off = cmd_off
        self.name = f"ToggleCommand<{cmd_on}, {cmd_off}>"
        self.lutron=lutron

    def _set_action(self, value):
        cmd = self.cmd_on if value else self.cmd_off
        if cmd is not None:
            self.lutron.send_command(cmd)

class Lutron(Service):
    def __init__(self, host: str, port: int, username: str, password: str):
        """Initialize a Lutron connection."""
        logger.info("Creating Lutron service (%s@%s:%s)", username, host, port)
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sock: Optional[socket.socket] = None
        
        # Single list of all handlers
        self._handlers: List[LutronConnector] = []
        

    def start(self):
        logger.info(f"Starting Lutron listener for {self.username}@{self.host}:{self.port}")
        # Connect and start listening
        self.connect()
        self._start_listener()

    def connect(self) -> bool:
        """Establish connection to the Lutron system."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(60*10)  # 10 minutes timeout
            
            # Handle authentication
            self._read_prompt()  # Username prompt
            self.send_command(self.username, secret=True)
            self._read_prompt()  # Password prompt
            self.send_command(self.password,secret=True)
            self._read_prompt()  # Login success
            
            # Enable monitoring for sysvars
            self.send_command("#MONITORING,10,1")
            return True
        except Exception as e:
            logger.error("Failed to connect: %s", e)
            return False
    
    def _read_prompt(self) -> str:
        """Read and return server prompt."""
        try:
            data = self.sock.recv(1024).decode('utf-8')
            if data:
                logger.debug("Server prompt: %s", data.strip())
        except Exception as e:
            logger.error("Error reading prompt: %s", e)
    
    def send_command(self, cmd: str, secret = False) -> None:
        """Send a command to the Lutron system."""
        if not secret: logger.debug("Running command: %s", cmd)
        if not self.sock:
            raise ConnectionError("Not connected to Lutron system")
        self.sock.send(f"{cmd}\r\n".encode())
    
    def _start_listener(self):
        """Start the listener thread for processing events."""
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def _listen_loop(self):
        """Main listening loop that processes incoming events."""
        while self.running:
            try:
                data = self.sock.recv(1024).decode('utf-8')
                if not data:
                    logger.warning("Connection closed by server. Reconnecting...")
                    time.sleep(5)
                    self.connect()
                    continue
                
                for line in data.strip().split("\r\n"):
                    self._process_event(line)
                    
            except socket.timeout:
                continue
            except Exception as e:
                logger.error("Error in listen loop: %s", e)
                time.sleep(5)
                self.connect()
    
    def register_handler(self, handler: LutronConnector):
        """Register a handler for Lutron events."""
        self._handlers.append(handler)

    def _process_event(self, line: str):
        """Process a single event line by passing it to all handlers."""
        # logger.debug("Processing Line: %s", line)

        # Pass the event to all handlers - they'll decide if they want to handle it
        had_positive_handler = False
        if any([handler.safely_process_event(line) is not None for handler in self._handlers]):
            logger.debug("Processed Line: %s", line)
            return True
    
    def device(self, device_id: int) -> LutronDevice:
        """Create and return a new LutronDevice instance for the given device ID."""
        return LutronDevice(self, device_id)
    
    def sysvar(self, sysvar_id: int) -> LutronSysvar:
        """Create and return a new LutronSysvar instance for the given sysvar ID."""
        return LutronSysvar(self, sysvar_id)
    
    def keypad(self, keypad_id: int, button_id: int) -> LutronKeypad:
        """Create and return a new LutronKeypad instance for the given keypad and button IDs."""
        return LutronKeypad(self, keypad_id, button_id)
    
    def toggle(self,cmd_on,cmd_off):
        return ToggleCommand(self,cmd_on,cmd_off)

    def keypad(self, id: int, button: int, action: int = 1):
        return self.toggle(f'#DEVICE,{id},{button},9,{action}', f'#DEVICE,{id},{button},9,0')

    def stop(self):
        """Stop the listener and clean up resources."""
        self.running = False
        if self.sock:
            self.sock.close()
