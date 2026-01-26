#!/usr/bin/python3

import subprocess
from .connector import Connector
from .service import Service
from shell_listener import ShellListener

from logger import get_logger
import threading
import requests
import traceback
import socket
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    # Fallback for Python < 3.7
    ThreadingHTTPServer = HTTPServer
from queue import Queue


logger = get_logger(__name__)

class NukiAutoLock(Connector):
    def __init__(self, nuki: 'Nuki', nuki_id: str):
        super().__init__()  # Initialize with no value
        self.nuki = nuki
        self.nuki_id = nuki_id
        self.name = f"NukiAutoLock<{nuki_id}>"
    
    def _set_action(self, value: bool) -> None:
        """Set the auto-lock state on Nuki"""
        CNUKI = lambda cmd="": f'curl -sS "https://api.nuki.io/smartlock/{self.nuki_id}{cmd}" -H "Authorization: Bearer {self.nuki.api_key}" -H "Content-Type: application/json"'
        
        # Construct the command based on whether we're enabling or disabling
        if value:
            #Enable autolock, and lock door (if unlocked)
            logger.info("Enable Autolock")
            #cmd = f'output=$({CNUKI()}) && [[ "$output" =~ "\\"advancedConfig\\":(\\{{[^}}]*\\"autoLock\\":([^,]*)[^}}]*\\}})" ]] && adv_conf="${{${{match[1]/$match[2]/true}}/,\\"operationId\\":[^\}},]/}}" && {CNUKI("/advanced/config")} -X POST -d "$adv_conf" && [[ "$output" =~ "\\"state\\":\\{{[^}}]*\\"state\\":([^1])" ]] && {CNUKI("/action")} -X POST -d "{{action: 2}}"'
            cmd = f'output=$({CNUKI()}) && {CNUKI("/advanced/config")} -X POST -d "$(jq -c \'.advancedConfig | .autoLock=true | del(.operationId)\' <<< $output)" && [[ $(jq -c .state.state <<< $output) != 1 ]] && {CNUKI("/action")} -X POST -d "{{action: 2}}"'            
        else:
            #Disable autolock, and Unlock door (if locked)
            logger.info("Disable Autolock")
            #cmd = f'output=$({CNUKI()}) && [[ "$output" =~ "\\"advancedConfig\\":(\\{{[^}}]*\\"autoLock\\":([^,]*)[^}}]*\\}})" ]] && adv_conf="${{${{match[1]/$match[2]/false}}/,\\"operationId\\":[^\}},]/}}" && {CNUKI("/advanced/config")} -X POST -d "$adv_conf" && [[ "$output" =~ "\\"state\\":\\{{[^}}]*\\"state\\":(1)" ]] && {CNUKI("/action")} -X POST -d "{{action: 1}}"'
            cmd = f'output=$({CNUKI()}) && {CNUKI("/advanced/config")} -X POST -d "$(jq -c \'.advancedConfig | .autoLock=false | del(.operationId)\' <<< $output)" && [[ $(jq -c .state.state <<< $output) == 1 ]] && {CNUKI("/action")} -X POST -d "{{action: 1}}"'

        logger.debug("Running Command: %s", self.nuki.reduct(cmd))
        result = subprocess.run(cmd, shell=True, executable='/bin/zsh', capture_output=True, text=True)

class NukiDevice(Connector):
    def __init__(self, nuki: 'Nuki', nuki_id: str):
        super().__init__()  # Initialize with no value
        self.nuki = nuki
        self.nuki_id = nuki_id
        self.name = f"NukiDevice<{nuki_id}>"
    
    def _set_action(self, value: bool) -> None:
        """Set the lock state on Nuki - True for unlock, False for lock"""
        CNUKI = lambda cmd="": f'curl -sS "https://api.nuki.io/smartlock/{self.nuki_id}{cmd}" -H "Authorization: Bearer {self.nuki.api_key}" -H "Content-Type: application/json"'
        
        # 1 - unlock, 2 - lock
        # Construct the command based on whether we're locking or unlocking
        logger.info("%s the door (%s)", 'Unlocking' if value else 'Locking', self.nuki_id)
        cmd = f'{CNUKI("/action")} -X POST -d "{{action: {1 if value else 2}}}"'
        
        logger.debug("Running Command: %s", self.nuki.reduct(cmd))
        result = subprocess.run(cmd, shell=True, executable='/bin/zsh', capture_output=True, text=True)

    def autolock(self) -> 'NukiAutoLock':
        """Get a NukiAutoLock instance for this device"""
        return NukiAutoLock(self.nuki, self.nuki_id)


class NukiBridgedDevice(Connector):
    def __init__(self, bridge: 'NukiBridge', nuki_id: str):
        super().__init__()  # Initialize with no value
        self.bridge = bridge
        self.nuki_id = nuki_id
        self.name = f"NukiBridgedDevice<{nuki_id}>"
        self._sensor = NukiBridgedSensor(self)
        self.set(False)

    def sensor(self):
        return self._sensor

class NukiBridgedSensor(Connector):
    def __init__(self, device: NukiBridgedDevice):
        super().__init__()  # Initialize with no value
        self.device = device
        self.name = f"NukiBridgedSensor<{device.nuki_id}>"
        self.set(False)


class NukiCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Nuki bridge callbacks"""
    
    def __init__(self, bridge, *args, **kwargs):
        self.bridge = bridge
        super().__init__(*args, **kwargs)
    
    def do_POST(self):
        """Handle POST requests from the Nuki bridge"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            logger.info("Received callback from bridge: %s", data)
            
            # Send success response IMMEDIATELY to prevent bridge timeout
            # Process the callback asynchronously after sending response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode())
            self.wfile.flush()
            
            # Process callback asynchronously to avoid blocking the HTTP response
            # This prevents the bridge from timing out if processing takes time
            threading.Thread(
                target=self._process_callback,
                args=(data,),
                daemon=True,
                name=f"NukiCallbackProcessor-{data.get('nukiId', 'unknown')}"
            ).start()
            
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in callback: %s", e)
            self.send_response(400)
            self.end_headers()
        except Exception as e:
            logger.exception("Error handling callback: %s", e)
            # Try to send error response if we haven't sent success yet
            try:
                self.send_response(500)
                self.end_headers()
            except:
                pass
    
    def _process_callback(self, data):
        """Process callback data asynchronously"""
        try:
            nuki_id = data.get("nukiId")
            if nuki_id:
                # Get or create device
                device = self.bridge.device(str(nuki_id))
                state = data.get("state")
                
                # Update device state: state 1 = locked, state 3 = unlocked
                # We map: locked (1) -> False, unlocked (3) -> True
                if state is not None:
                    device.set(state != 1)
                
                # Update door sensor state if available
                if "doorsensorState" in data:
                    # doorsensorState 2 = closed, 3 = opened
                    # We map: closed (2) -> False, opened (3) -> True
                    device._sensor.set(data.get("doorsensorState") != 2)
        except Exception as e:
            logger.exception("Error processing callback data: %s", e)
    
    def log_message(self, format, *args):
        """Override to use our logger instead of stderr"""
        logger.debug("Nuki callback server: %s", format % args)


class NukiBridge(Connector):
    def __init__(self, nuki: 'Nuki', ip: str, token: str, localport = 18080):
        super().__init__()  # Initialize with no value
        self._value = True
        self.nuki = nuki
        self.ip = ip
        self.localport = localport
        self.token = token
        self.name = f"NukiBridge<{ip}>"
        self.devices = {}

        self.listener = ShellListener(f"(while true; do curl -sS 'http://{ip}:8080/auth' && echo '' || (echo 'nuki bridge error' >& 2; sleep 5;); sleep 1; done)")

        self.buttonListener = self.listener.filter("(true)")
        self.buttonListener.register(self.on_press)

        logger.info("Starting Nuki Bridge listener for %s:8080", self.ip)
        self.listener.start()

        
        # Start callback server and register with bridge
        self._start_callback_server()
        
        # self.update_data()
    
    def _get_local_ip(self):
        """Get the local IP address on the same network as the bridge"""
        try:
            # Connect to the bridge to determine which interface to use
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Connect doesn't actually send data, just determines routing
                s.connect((self.ip, 8080))
                local_ip = s.getsockname()[0]
            finally:
                s.close()
            return local_ip
        except Exception as e:
            logger.warning("Could not determine local IP, using 0.0.0.0: %s", e)
            return "0.0.0.0"
    
    def _start_callback_server(self):
        """Start HTTP server to receive callbacks from the bridge"""
        try:
            local_ip = self._get_local_ip()
            callback_url = f"http://{local_ip}:{self.localport}/nuki"
            
            # Create handler factory that includes bridge reference
            def handler_factory(*args, **kwargs):
                return NukiCallbackHandler(self, *args, **kwargs)
            
            # Create a custom server class with socket timeout
            class TimeoutHTTPServer(ThreadingHTTPServer):
                """HTTP server with socket timeout to prevent hanging connections"""
                def server_bind(self):
                    self.socket.settimeout(30)  # 30 second timeout
                    super().server_bind()
            
            # Start HTTP server in a separate thread
            # Use ThreadingHTTPServer to handle concurrent requests better
            self.http_server = TimeoutHTTPServer((local_ip, self.localport), handler_factory)
            self.http_server_thread = threading.Thread(
                target=self.http_server.serve_forever,
                daemon=True,
                name=f"NukiCallbackServer-{self.ip}"
            )
            self.http_server_thread.start()
            
            logger.info("Started callback server on %s:%d", local_ip, self.localport)
            
            # Register callback with bridge
            self._register_callback(callback_url)
            
        except Exception as e:
            logger.exception("Failed to start callback server: %s", e)
    
    def _register_callback(self, callback_url):
        """Register callback URL with the Nuki bridge if not already registered"""
        try:
            # First, check existing callbacks using /callback/list endpoint
            list_url = f"http://{self.ip}:8080/callback/list"
            params = {"token": self.token}
            
            response = requests.get(list_url, params=params, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            # Check if callback is already registered
            callbacks = result.get("callbacks", [])
            for callback in callbacks:
                if callback.get("url") == callback_url:
                    logger.info("Callback URL already registered: %s (id: %s)", callback_url, callback.get("id"))
                    return
            
            # Callback not found, register it
            register_url = f"http://{self.ip}:8080/callback/add"
            params = {
                "url": callback_url,
                "token": self.token
            }
            
            response = requests.get(register_url, params=params, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            if result.get("success"):
                logger.info("Successfully registered callback URL: %s", callback_url)
            else:
                logger.warning("Failed to register callback: %s", result.get("message", "Unknown error"))
                
        except Exception as e:
            logger.exception("Failed to register callback with bridge: %s", e) 

    def update_data(self):
        try:
            # logger.info(f"doorsensorState")
            response = requests.get(f"http://{self.ip}:8080/list?token={self.token}", timeout=5)
            response.raise_for_status()
            data = response.json()
            for d in data:
                nukiId = str(d["nukiId"])
                device = self.device(nukiId)
                state_data = d.get("lastKnownState", {})
                
                # Update device state: state 1 = locked, state 3 = unlocked
                # We map: locked (1) -> False, unlocked (3) -> True
                state = state_data.get("state")
                if state is not None:
                    device.set(state != 1)  # state != 1 means unlocked (True)
                
                # Update door sensor state if available
                if "doorsensorState" in state_data:
                    # doorsensorState 2 = closed, 3 = opened
                    # We map: closed (2) -> False, opened (3) -> True
                    device._sensor.set(state_data.get("doorsensorState") != 2)
        except Exception as e:
            logger.exception(f"Exception in update_data_loop: {e}")
        finally:
            # schedule next call after 30 seconds
            #threading.Timer(30, self.update_data_loop).start()            
            pass
        
    
    def device(self, nuki_id: str) -> NukiBridgedDevice:
        nuki_id = str(nuki_id)
        if nuki_id not in self.devices: 
            self.devices[nuki_id] = NukiBridgedDevice(self, nuki_id)
        return self.devices[nuki_id]
    
    def on_press(self, line, match):
        self.notify_set()
        # threading.Timer(5, lambda: self.set(False)).start()
        
        
class Nuki(Service):
    def __init__(self, api_key: str, token: str):
        logger.info(f"Nuki service created {api_key=} {token=}")
        super().__init__()
        self.api_key = api_key
        self.token = token
        self.bridges = {}

    
    def CMD(self,cmd=""):
        return 

    def device(self, nuki_id: str) -> NukiDevice:
        return NukiDevice(self,nuki_id)

    def bridge(self,bridge_ip):
        if bridge_ip not in self.bridges:
            self.bridges[bridge_ip] = NukiBridge(self, bridge_ip, self.token)
        return self.bridges[bridge_ip]

    def reduct(self,x):
        return x.replace(self.api_key,"<API_KEY>")
