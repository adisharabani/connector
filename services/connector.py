#!/usr/bin/python3

from typing import Optional, Callable, Any, List
from logger import get_logger

import json
import threading

# Get logger for this module
logger = get_logger(__name__)

# Add color constants
# GREEN = '\033[92m'
# RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

class Connector:
    """
    A connector class that allows notifying listeners when its value changes.
    Each connector has a value and can notify listeners when the value changes.
    
    Connector derived implementations should implement the _set_action method.
    usage of connector instances should probably register to their on_set methods
    
    """
    
    def __init__(self, name=None):
        self.name = name or f"{self.__class__.__name__}<{id(self)}>"
        self._value = None
        self._listeners: List[Callable[[Any], None]] = []
    
    def get(self) -> Any:
        return self._value
    
    def _set_action(self, value: Any) -> None:
        # Override to add code when set is called externally
        pass
    
    def set(self, value: Any, act=True) -> bool:
        if value != self._value:
            original_value = self._value
            self._value = value
            if act: self._set_action(value)
            if original_value is None:
                logger.info(f"{BLUE}{self.name} first value is {value}{RESET}")
                # TODO: We don't want this, but if I remove it we can break filter and other complex automations
                self.notify_set()
            else:
                logger.info(f"{BLUE}{self.name} value changed from {original_value} to {value}{RESET}")
                self.notify_set()
    
    def notify_set(self):
        # Notify our listeners
        for listener in self._listeners:
            listener(self._value)
            
    def on_set(self, callback: Callable[[Any], None], filter=None) -> None:
        self._listeners.append(lambda val, filter=filter, callback=callback: (filter==None or val in filter) and callback(val))
        # If we already have a value, call the callback immediately
        # if self._value is not None and (filter==None or self._value in filter):
        #     callback(self._value)

    def bind(self, other_connector, name=None):
        if name:
            self.name = name
            other_connector.name = name
        self.on_set(other_connector.set)
        other_connector.on_set(self.set)
        
    def to_json(self):
        return Lambda(self, lambda v: json.loads(v), lambda v:json.dumps(v))

    def inverse(self):
        return Lambda(self, lambda v: not v, lambda v: not v)
        #return Inverse(self)

    def once(self, days=None):
        return Once(self,days=days)

    def map(self, cmd):
        cmd = eval(f"lambda value: {cmd}")
        return Lambda(self, cmd)

    def filter(self, cmd="value"):
        cmd = eval(f"lambda value: {cmd}")
        fcmd = lambda v:v if cmd(v) else None 
        return Lambda(self, fcmd, fcmd)

class Lambda(Connector):
    def __init__(self, source: Connector, cmd, reversed_cmd=None):
        super().__init__()
        self._cmd = cmd
        self._reversed_cmd = reversed_cmd
        self.name = f"{source.name}.{cmd.__qualname__.split('.')[1]}"
        self._source = source 
        self._source.on_set(self._act)

    def _act(self, value):
        lvalue = self._cmd(value)
        #if lvalue is not None:
        self.set(lvalue, act=False)

    def _set_action(self, value: Any) -> None:
        # When our value changes, update the source with the opposite value
        if self._reversed_cmd:
            rvalue = self._reversed_cmd(value)
            #if rvalue is not None:
            self._source.set(rvalue)

class Inverse(Connector):
    def __init__(self, source: Connector):
        super().__init__()
        self.name = f"Inverse({source.name})"
        self._source = source 
        self._source.on_set(lambda val: self.set(not val, act=False))

    def _set_action(self, value: Any) -> None:
        # When our value changes, update the source with the opposite value
        self._source.set(not value)

class Once(Connector):
    def __init__(self, source: Connector, days=None):
        super().__init__()
        self.name =f"{source.name}.Once({'unlimited' if days is None else f'{days} days'})"
        self._source = source
        self._source.on_set(self._act)
        self._days = days
        self._last_act = None
        self._timer = None

    def _act(self, value):
        if value:
            if self._timer is None:
                self.set(value, act=False)
                self._timer = threading.Timer(86400*self._days, lambda: self._stop_timer() or self.set(False, act=False))
        else:
            #self._stop_timer(value)
            self.set(value, act=False)

    def _set_action(self, value: Any):
        if value:
            if self._timer is None:
                self._source.set(value)
                self._timer = threading.Timer(86400*self._days, lambda: self._stop_timer() or self._source.set(False))
        else:
            #self._stop_timer(value)
            self._source.set(value)

    def _stop_timer(self, v=False):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        