#!/usr/bin/python3

from typing import Optional, Callable, Any, List
from logger import get_logger

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
    """
    
    def __init__(self):
        self.name = f"{self.__class__.__name__}<{id(self)}>"
        self._value = None
        self._listeners: List[Callable[[Any], None]] = []
    
    def get(self) -> Any:
        return self._value
    
    def _set_action(self, value: Any) -> None:
        pass
    
    def set(self, value: Any, act=True) -> bool:
        if value != self._value:
            original_value = self._value
            self._value = value
            if act: self._set_action(value)
            logger.info(f"{BLUE}{self.name} value changed from {original_value} to {value}{RESET}")
            self.notify_set()
    
    def notify_set(self):
        # Notify our listeners
        for listener in self._listeners:
            listener(self._value)
            
    def on_set(self, callback: Callable[[Any], None], filter=None) -> None:
        self._listeners.append(lambda val, filter=filter, callback=callback: (filter==None or val in filter) and callback(val))
        # If we already have a value, call the callback immediately
        if self._value is not None and (filter==None or self._value in filter):
            callback(self._value)

    def bind(self, other_connector, name=None):
        if name:
            self.name = name
            other_connector.name = name
        self.on_set(other_connector.set)
        other_connector.on_set(self.set)

    def process_event(self, line: str) -> None:
        """Process an event line for this connector.
        
        Args:
            line: The raw event line from the Lutron system
        """
        pass
    
    def inverse(self):
        return Inverse(self)


class Inverse(Connector):
    def __init__(self, source: Connector):
        super().__init__()
        self.name = f"Inverse({source.name})"
        self._source = source 
        self._source.on_set(lambda val: self.set(not val, act=False))

    def _set_action(self, value: Any) -> None:
        # When our value changes, update the source with the opposite value
        self._source.set(not value)

