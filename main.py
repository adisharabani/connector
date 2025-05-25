import time

from logger import setup_logger, get_logger
from services import *  # This will import all services defined in services/__init__.py
from config import ConfigExecutor

# Setup logging
setup_logger()
logger = get_logger(__name__)
logger.info("Starting connector service (YAML config)")


def main():
    executor = ConfigExecutor('config.yaml')
    executor.execute()
    
    logger.info("Press Ctrl+C to exit...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Cleaning up...")
        for service in executor.services.values():
            service.stop()
        logger.info("Done!")

if __name__ == "__main__":
    main() 
