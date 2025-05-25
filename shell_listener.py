#!/usr/bin/python3

import subprocess
import threading
import time
import re
from typing import Callable, Any
from traceback import format_exc
from logger import get_logger

logger = get_logger(__name__)

class ShellListener:
    def __init__(self, shell_command, executable=None):
        """
        Initialize a listener that uses a shell command to receive data.
        
        Args:
            shell_command (str): Shell command to execute for listening (e.g., "echo | nc -u 192.168.1.233 30007")
        """
        self.shell_command = shell_command
        self.executable = executable
        self.callbacks = []
        self.running = False
        self.process = None
        self.start()
        
    def start(self):
        """Start the listener process."""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def _listen_loop(self):
        """Main listening loop that executes the shell command and processes output."""
        while self.running:
            try:
                logger.debug("Starting Shell Listener",)
                self.process = subprocess.Popen(
                    self.shell_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1, 
                    executable=self.executable
                )
                while self.running:
                    line = self.process.stdout.readline().strip()
                    if not line and self.process.poll() is not None:
                        break
                    if line:
                        self._process_line(line)
                        
            except Exception as e:
                logger.error("Listener error: %s", e)
            finally:
                logger.warning("Restarting listener")
                time.sleep(5)
        logger.info("Listen loop ended")
    
    def _process_line(self, line):
        """Process a received line of data through filters and callbacks."""
        logger.debug("Processing: %s", line)
        for callback in self.callbacks:
            try:
                callback(line,line)
            except Exception as e:
                logger.error("Error in callback: %s\n%s", e, format_exc())
    
    def register(self, callback):
        """
        Add a callback function to be called when data passes through filters.
        
        Args:
            callback (callable): Function to call with (line, match) arguments
        """
        self.callbacks.append(callback)
        
    def filter(self, pattern):
        """ Filter the listener with a regex pattern """
        return FilteredListener(self, pattern)

    def stop(self):
        """Stop the listener."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process = None
            except:
                pass


class FilteredListener:
    def __init__(self, parent_listener, pattern):
        self.parent = parent_listener
        self.pattern = re.compile(pattern)
        self.callbacks = []
        
        # Register with parent to receive all lines
        self.parent.register(self._process_line)
    
    def _process_line(self, line, dummy):
        match = self.pattern.search(line)
        if match:
            # If there's a capture group, pass the first group, otherwise the whole line
            result = match.group(1) if match.groups() else line
            for callback in self.callbacks:
                try:   
                    callback(line, result)
                except Exception as e:
                    print(f"Error in callback: {e}\n{format_exc()}")
    
    def register(self, callback):
        """Register a callback to be called when a matching line is received"""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
        return self
    
    def filter(self, pattern):
        """Create a nested filtered listener with an additional filter"""
        return FilteredListener(self, pattern) 