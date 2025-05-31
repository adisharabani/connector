#!/usr/bin/python3

import subprocess
import threading
import time
import re
from typing import Callable, Any
from traceback import format_exc
from logger import get_logger

logger = get_logger(__name__)


class FilterAnalyzer:
    def __init__(self, parent_analyzer=None, pattern=None):
        logger.debug(f"Filter: {pattern}")
        self.parent = parent_analyzer
        self.pattern = re.compile(pattern) if pattern else None
        self.callbacks = []
        
        # Register with parent to receive all lines
        if self.parent:
            self.parent.register(lambda line,matched_group: self._process_line(line))
    
    def _process_line(self, line):
        if self.pattern:
            match = self.pattern.search(line)
            if not match: return 
            matched_group = match.group(1) if match.groups() else line
        else:
            matched_group = line

        return any([self.safe_callback(callback, line, matched_group) is not None for callback in self.callbacks])
                        
    
    def safe_callback(self, callback, line, matched_group):
        try:   
            return callback(line, matched_group)
        except Exception as e:
            print(f"Error in callback: {e}\n{format_exc()}")
            return False
    
    def register(self, callback):
        """Register a callback to be called when a matching line is received - callback recieves line, and matched grouped"""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
        return self
    
    def filter(self, pattern):
        """Create a nested filtered listener with an additional filter"""
        return FilterAnalyzer(self, pattern) 


class ShellListener(FilterAnalyzer):
    def __init__(self, shell_command, executable=None):
        """
        Initialize a listener that uses a shell command to receive data.
        
        Args:
            shell_command (str): Shell command to execute for listening (e.g., "echo | nc -u 192.168.1.233 30007")
        """
        super().__init__()  # Initialize with no value

        self.shell_command = shell_command
        self.executable = executable
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

    def stop(self):
        """Stop the listener."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process = None
            except:
                pass

    def _listen_loop(self):
        """Main listening loop that executes the shell command and processes output."""
        while self.running:
            try:
                logger.debug(f"Starting Shell Listener: {self.shell_command}")
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
                        #logger.debug("Processing Line: %s", line)
                        if self._process_line(line):
                            logger.debug("Processed Line: %s", line)

                        
            except Exception as e:
                logger.error("Listener error: %s", e)
            finally:
                logger.warning("Restarting listener")
                time.sleep(5)
        logger.info("Listen loop ended")













