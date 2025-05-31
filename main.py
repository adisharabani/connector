import time

from logger import setup_logger, get_logger
from services import *  # This will import all services defined in services/__init__.py
from config import Configurator

# Setup logging
setup_logger()
logger = get_logger(__name__)
logger.info("Starting home automation connector")


def main():
    configurator = Configurator('data/config.yaml')
    
    logger.info("Press Ctrl+C to exit...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Cleaning up...")
        for service in configurator.services.values():
            service.stop()
        logger.info("Done!")

if __name__ == "__main__":
    main() 
