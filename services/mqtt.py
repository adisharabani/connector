#!/usr/bin/python3

from .connector import Connector
from .service import Service
import subprocess
import re
from typing import Any
from dataclasses import dataclass
from logger import get_logger
from shell_listener import ShellListener

logger = get_logger(__name__)


mqtt_protocols = {  "plain": {
                        "state_suffix": "",
                        "command_suffix": "",
                        "states" : [],
                        "commands": []
                    }, 
                    "covering": {
                        "state_suffix" : "/state",
                        "command_suffix" : "/command",
                        "states" : ["closed", "open"],
                        "commands" : ["close", "open"]
                    }
                }

class MQTTDevice(Connector):
    def __init__(self, mqtt: 'MQTT', topic: str, protocol = None):
        super().__init__()
        self.mqtt = mqtt
        self.topic = topic
        self.protocol = protocol
        self.name = f"MQTTDevice<{topic}>"
        
        # Register the listener for state updates
        self.listener = self.mqtt.listener.filter(f"{self.topic}{self.protocol['state_suffix']} ({'|'.join(map(str,self.protocol['states'])) if self.protocol['states'] else '.*'})")
        self.listener.register(self._on_state_update)
        
    def _on_state_update(self, line: str, match: str):
        """Handle state updates from MQTT"""
        try:
            logger.debug("on_state_update %s %s", line, match)
            index = self.protocol['states'].index(match) if self.protocol['states'] else match
            self.set(index, act=False)
        except ValueError:
            logger.warning("Unrecognized state '%s' for device %s", match, self.topic)
            self.set(match, act=False)
            
    
    def _set_action(self, value: Any) -> None:
        """Override _set_action to send MQTT command when value changes"""
        message = self.protocol['commands'][value] if self.protocol['commands'] else value
        command_topic = f"{self.topic}{self.protocol['command_suffix']}"

        logger.info("Setting %s to %s", command_topic, message)
        self.mqtt.send(topic=command_topic, message=message)

class MQTT(Service):
    def __init__(self, host: str, username: str, password: str, topics: None, protocols = mqtt_protocols):
        super().__init__()
        logger.info("Creating MQTT Listener (%s) (%s)", host, topics)
        self.host = host
        self.username = username
        self.password = password
        self.protocols = protocols
        
        # Create the listener for state updates
        self.listener = ShellListener(f"mosquitto_sub -h {host} -u {username} -P {password} -t {' -t '.join(topics) if topics else '#'} -v")
    
    def device(self, topic: str, protocol: str = "plain") -> MQTTDevice:
        return MQTTDevice(self, topic, self.protocols[protocol] if protocol else mqtt_protocols["plain"])
    
    def send(self, topic: str, message: str):
        logger.info("Sending MQTT command: topic=%s message=%s", topic, message)
        cmd = f'mosquitto_pub -h {self.host} -u {self.username} -P {self.password} -t "{topic}" -m "{message}"'
        subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
    
    def stop(self):
        logger.info("Stopping MQTT Listener")
        self.listener.stop()
