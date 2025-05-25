#!/usr/bin/python3

import subprocess
from .connector import Connector
from .service import Service
from logger import get_logger

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

class Nuki(Service):
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
    
    def CMD(self,cmd=""):
        return 

    def device(self, nuki_id: str) -> NukiDevice:
        return NukiDevice(self,nuki_id)

    def reduct(self,x):
        return x.replace(self.api_key,"<API_KEY>")
