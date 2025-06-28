#!/usr/bin/python3

from .connector import Connector
from .service import Service
import subprocess
import re
from typing import Any
from dataclasses import dataclass
from logger import get_logger
from shell_listener import ShellListener
import json
import threading

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
    def __init__(self, mqtt: 'MQTT', topic: str, protocol = {"state_suffix": "", "command_suffix": "", "states": [], "commands": []}, retain = False, process_same_value_events = False):
        super().__init__(name = f"MQTTDevice<{topic}>", process_same_value_events = process_same_value_events)
        self.mqtt = mqtt

        self.topic = topic
        self.protocol = protocol
        self.retain = retain
        
        # Register the listener for state updates
        self.mqtt.topics.add(topic)
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
        self.mqtt.send(topic=command_topic, message=message, retain = self.retain)



class UserPresense:
    def __init__(self, mqtt, name, inside_room, outside_room, outside_reset_time=None, outside_distance=None):
        self.mqtt = mqtt
        self.name = name
        self.inside_room = inside_room
        self.outside_room = outside_room
        self.outside_reset_time = outside_reset_time
        self.outside_distance = outside_distance

        bool_protocol = {"state_suffix": "", "command_suffix": "", "states": ["false","true"], "commands": ["false", "true"]}
        self.inside = MQTTDevice(mqtt=mqtt, topic=f"presense/{name}/inside", protocol=bool_protocol, retain=True)
        self.outside = MQTTDevice(mqtt=mqtt, topic=f"presense/{name}/outside", protocol=bool_protocol, retain=True)

        self.timer = None

    def parse_esp32_message(self, room, message):
        if room == self.inside_room:
            self.inside.set(True)
        elif room == self.outside_room:
            message = json.loads(message)
            # If not home, than we are definitely outside
            if not self.inside.get(): 
                self.outside.set(True)
                
            # If we are home, then we are outside only if we are close to the outside sensor
            elif self.outside_distance is None or message["distance"] < self.outside_distance:
                self.inside.set(False)
                self.outside.set(True)    

            self.reset_outside_timer()

    def reset_outside_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.outside_reset_time and self.outside.get():
            self.timer = threading.Timer(self.outside_reset_time, lambda: self.outside.set(False))
            self.timer.start()



class ESPresense(Service):
    def __init__(self, service: 'MQTT', inside_room, outside_room, outside_reset_time=3, outside_distance=4):
        logger.info(f"Creating ESPresense (Inside room: {inside_room}, Outside room: {outside_room})")
        self.mqtt = service
        self.inside_room = inside_room
        self.outside_room = outside_room
        self.outside_reset_time = outside_reset_time
        self.outside_distance = outside_distance

        self.sensors = {}
        
        # Register the listener for state updates
        self.mqtt.topics.add(f"espresense/devices")
        self.listener = self.mqtt.listener.filter(f"espresense/devices/(?P<name>[^/]*)/(?P<room>{inside_room}{f'|{outside_room}' if outside_room else ''}) (?P<message>.*)", log=False)
        self.listener.register(self._on_esp32_update)

        self.anybody = UserPresense(self.mqtt, "anybody", self.inside_room, self.outside_room)
        
    def __getattr__(self, name):
        return self._get_sensor(name)

    def device(self,name):
        return self._get_sensor(name)
        
    def _get_sensor(self,name):
        if name not in self.sensors:
            self.sensors[name]  = UserPresense(self.mqtt, name, self.inside_room, self.outside_room, self.outside_reset_time, self.outside_distance)
            self.sensors[name].inside.on_set(self.update_anybody_sensor)
            self.sensors[name].outside.on_set(self.update_anybody_sensor)

        return self.sensors[name]
        
    def update_anybody_sensor(self, value):
        self.anybody.outside.set(any(sensor.outside.get() for sensor in self.sensors.values()))
        self.anybody.inside.set(any(sensor.inside.get() for sensor in self.sensors.values()))
        
    def _on_esp32_update(self, line: str, match: dict):
        """Handle espresenses state updates received from MQTT"""
        try:
            sensor = self._get_sensor(match["name"])
            sensor.parse_esp32_message(match["room"], match["message"])
        except ValueError:
            logger.warning("Problematic espresense line: '%s' (Match: %s)", line, match)


class MQTT(Service):
    def __init__(self, host: str, username: str, password: str, protocols = mqtt_protocols):
        super().__init__()
        logger.info("Creating MQTT service (%s@%s)", username, host)
        self.host = host
        self.username = username
        self.password = password
        self.protocols = protocols
        self.topics = set()
        # Create the listener for state updates
        self.listener = ShellListener(f"")
        
    def start(self):
        # Create the listener for state updates
        if self.topics:
            self.listener.shell_command = f"mosquitto_sub -h {self.host} -u {self.username} -P {self.password} -t {('/# -t '.join(self.topics)+'/#') if self.topics else '#'} -v"
            #logger.info(self.listener.shell_command)
            logger.info(f"Starting MQTT listener for {self.username}@{self.host} with topics: {', '.join(self.topics) if self.topics else '#'}")
            self.listener.start()
        else:
            logger.error("No devices/topics found so no need to start MQTT service")
    

    def device(self, topic: str, protocol: str = None, process_same_value_events = None) -> MQTTDevice:
        protocol = self.protocols.get(protocol) if protocol is not None else {"state_suffix": "", "command_suffix": "", "states": [], "commands": []}
        return MQTTDevice(self, topic, protocol, process_same_value_events=process_same_value_events)
        
    def send(self, topic: str, message: str, retain = False):
        logger.debug("Sending MQTT command: topic=%s message=%s", topic, message)
        cmd = f'mosquitto_pub -h {self.host} -u {self.username} -P {self.password} -t "{topic}" -m "{message}" {"-r" if retain else ""}'
        subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
    
    def stop(self):
        logger.info("Stopping MQTT Listener")
        self.listener.stop()
