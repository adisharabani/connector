#!/usr/bin/python3

import yaml
from logger import get_logger
from typing import Any, Dict
from services import Service  # Import Service and all service implementations
import time

# Get logger for this module
logger = get_logger(__name__)

class Configurator:
    def __init__(self, config_path: str):
        logger.info("Analyzing config file")
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize services
        self.services = self._load_services()
        self.bind_connectors()
        self.start_services()
        
    def _load_services(self) -> Dict[str, Any]:
        """Initialize all services from config."""
        logger.info("Loading Services")
        services = {}
        for name, config in self.config['services'].items():
            service_class = Service.get_service_class(name)
            if service_class is None:
                logger.error(f"No service class found for '{name}'")
                continue
            services[name] = service_class(**config)
        return services
    
    def _get_bindable_object(self, binding):
        name, config = next(iter(binding.items()))
        service = self.services.get(name)

        if isinstance(config, list):
            ret = service
            for operation in config:
                if isinstance(operation, str):
                    ret = getattr(ret, operation)()
                else:
                    method_name, args = next(iter(operation.items()))
                    method = getattr(ret,method_name)
                    if isinstance(args, dict):
                        ret = method(**args)
                    elif isinstance(args, list):
                        ret = method(*args)
                    else:
                        ret = method(args)
            return ret
        elif hasattr(service, "device"):
            return service.device(config)
        else:
            logger.error(f"No device found for service {name=} {service=}")
            logger.info(f"{self.services=}")

    def bind_connectors(self):
        """Execute all bindings from the config."""
        logger.info("Binding Connectors")
        for binding in self.config['bindings']:
            # Get binding type (sync or one_waycontrollers
            # filter = binding.get("filter")
            one_way = binding.get("direction") == "one-way"
            sequence = binding.get("direction") == "sequence"

            controllers = [self._get_bindable_object(x) for x in binding["binding"]]

            if sequence:
                self.sequences= Sequencer(controllers)

            else:
                for source, target in zip(controllers, controllers[1:]):
                    source.on_set(target.set)#, filter=filter)

                    if not one_way:
                        target.on_set(source.set)#, filter=filter)
                    
                    logger.info(f"Binding set: {source.name} {'-->' if one_way else '<-->' } {target.name}")

    def start_services(self):
        logger.info("Starting Services")
        [service.start() for service in self.services.values()]


class Sequencer:
    def __init__(self, controllers):
        self.controllers = controllers
        for i in range(len(controllers)-1):
            self.controllers[i].on_set(lambda v,i=i: self.set(v,i))
        self.state=0
        logger.info(f"Sequence set: {' -> '.join([x.name for x in controllers])}")
    def set(self,value,index):
        if index==self.state:
            if value:
                self.state+=1
                logger.debug(f"Sequence state increased {self.state=}")
            elif index>0:
                self.state-=1
                logger.debug(f"Sequence state reset {self.state=}")
            if self.state==len(self.controllers)-1:
                logger.debug(f"Sequence completed")
                self.controllers[-1].set(value)
                self.state=0






