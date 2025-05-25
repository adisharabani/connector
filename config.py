#!/usr/bin/python3

import yaml
from logger import get_logger
from typing import Any, Dict
from services import Service  # Import Service and all service implementations

# Get logger for this module
logger = get_logger(__name__)

class ConfigExecutor:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize services
        self.services = self._init_services()
        
    def _init_services(self) -> Dict[str, Any]:
        """Initialize all services from config."""
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
        else:
            return service.device(config)

    def execute(self):
        """Execute all bindings from the config."""
        for binding in self.config['bindings']:
            # Get binding type (sync or one_way)
            source, target = binding["binding"]
            filter = binding.get("filter")
            one_way = binding.get("direction") == "one-way"

            source_obj = self._get_bindable_object(source)
            target_obj = self._get_bindable_object(target)

            source_obj.on_set(target_obj.set, filter=filter)

            if not one_way:
                target_obj.on_set(source_obj.set, filter=filter)
            
            logger.info(f"Created binding: {source_obj.name} {'-->' if one_way else '<-->' } {target_obj.name}")
