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
    def __init__(self, mqtt: 'MQTT', topic: str, protocol = None):
        super().__init__()
        self.mqtt = mqtt

        self.topic = topic
        self.protocol = protocol
        self.name = f"MQTTDevice<{topic}>"
        
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
        self.mqtt.send(topic=command_topic, message=message)


class UserPresense:
    def __init__(self, mqtt, name, inside_room, outside_room, outside_reset_time=None, outside_distance=None):
        self.mqtt = mqtt
        self.name = name
        self.inside_room = inside_room
        self.outside_room = outside_room
        self.outside_reset_time = outside_reset_time
        self.outside_distance = outside_distance

        self.inside = Connector(f"{name}.inside")
        self.inside.on_set(lambda value: self.mqtt.send(f"presense/{self.name}/inside", "true" if value else "false", retain=True) )
        self.outside = Connector(f"{name}.outside")
        self.outside.on_set(lambda value: self.mqtt.send(f"presense/{self.name}/outside", "true" if value else "false", retain=True) )

        self.timer = None

    def parse_message(self, room, message):
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



class MQTTPresense:
    def __init__(self, mqtt: 'MQTT', inside_room, outside_room, outside_reset_time=3, outside_distance=4):
        logger.info(f"Creating MQTTPresense (Inside room: {inside_room}, Outside room: {outside_room})")
        self.mqtt = mqtt
        self.inside_room = inside_room
        self.outside_room = outside_room
        self.outside_reset_time = outside_reset_time
        self.outside_distance = outside_distance

        self.sensors = {}
        
        # Register the listener for state updates
        self.mqtt.topics.add(f"espresense/devices")
        self.listener = self.mqtt.listener.filter(f"espresense/devices/(?P<name>[^/]*)/(?P<room>{inside_room}{f'|{outside_room}' if outside_room else ''}) (?P<message>.*)", log=False)
        self.listener.register(self._on_state_update)

        self.mqtt.topics.add(f"presense")
        self.override_listener = self.mqtt.listener.filter(f"presense/(?P<name>[^/]*)/inside (?P<status>true|false)", log=False)
        self.override_listener.register(lambda line,match: self._get_sensor(match["name"]).inside.set(match["status"] == "true"))


        self.anybody = UserPresense(self.mqtt, "anybody", self.inside_room, self.outside_room)
            
    def __getattr__(self, name):
        return self._get_sensor(name)
        # if name in self.sensors:
        #     return lambda: self.sensors[name]
        
    def _get_sensor(self,name):
        if name not in self.sensors:
            self.sensors[name]  = UserPresense(self.mqtt, name, self.inside_room, self.outside_room, self.outside_reset_time, self.outside_distance)
            self.sensors[name].inside.on_set(self.sensor_updated)
            self.sensors[name].outside.on_set(self.sensor_updated)
        return self.sensors[name]
        
    def sensor_updated(self, value):
        self.anybody.outside.set(any(sensor.outside.get() for sensor in self.sensors.values()))
        self.anybody.inside.set(any(sensor.inside.get() for sensor in self.sensors.values()))

    def _on_state_update(self, line: str, match: dict):
        """Handle state updates from MQTT"""
        try:
            sensor = self._get_sensor(match["name"])
            sensor.parse_message(match["room"], match["message"])
        except ValueError:
            logger.warning("Unrecognized state '%s' for device %s", match, self.topic)
            self.set(match, act=False)
            
    def _on_status_override(self, line: str, match: dict):
        """Handle state updates from MQTT"""
        try:
            logger.debug("on_status_override %s %s", line, match)
            sensor = self._get_sensor(match["name"])
            sensor.parse_message(match["room"], match["message"])
        except ValueError:
            logger.warning("Unrecognized state '%s' for device %s", match, self.topic)
            self.set(match, act=False)

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
    

    def device(self, topic: str, protocol: str = "plain") -> MQTTDevice:
        return MQTTDevice(self, topic, self.protocols[protocol] if protocol else mqtt_protocols["plain"])

    def espresense(self, inside_room, outside_room):
        return MQTTPresense(self, inside_room, outside_room)

    def send(self, topic: str, message: str, retain = False):
        logger.info("Sending MQTT command: topic=%s message=%s", topic, message)
        cmd = f'mosquitto_pub -h {self.host} -u {self.username} -P {self.password} -t "{topic}" -m "{message}" {"-r" if retain else ""}'
        subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
    
    def stop(self):
        logger.info("Stopping MQTT Listener")
        self.listener.stop()
