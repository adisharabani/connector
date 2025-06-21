#!/usr/bin/python3

import logging
from logging import DEBUG, INFO, WARNING, ERROR
import sys

def setup_logger(level=logging.DEBUG):
    """Configure the root logger to log INFO and above messages."""
    logging.basicConfig(
        level=level,
        format='%(name)s:%(levelname)s:%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout
    )

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    return logging.getLogger(name) 

