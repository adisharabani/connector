#!/usr/bin/python3

import logging
import sys

def setup_logger():
    """Configure the root logger to log INFO and above messages."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(name)s:%(levelname)s:%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout
    )

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    return logging.getLogger(name) 

