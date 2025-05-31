
class ServiceMeta(type):
    """Metaclass for Service that automatically registers service classes."""
    _registry = {}
    
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        # Only register if it's not the Service class itself
        if name != 'Service':
            # Register with lowercase name
            ServiceMeta._registry[name.lower()] = cls
        return cls

class Service(metaclass=ServiceMeta):
    """Base class for all services in the connector system."""
    
    # Registry of all service classes - now using the metaclass registry
    _registry = ServiceMeta._registry
    
    def __init__(self):
        """Initialize the service."""
        pass
    
    def start(self):
        """Start the service. Override in subclasses if needed."""
        pass
        
    def stop(self):
        """Stop the service and clean up resources. Override in subclasses if needed."""
        pass

    @classmethod
    def get_service_class(cls, name: str):
        """Get a service class by name (case-insensitive)."""
        return cls._registry.get(name.lower())