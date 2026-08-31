"""
Dependency Injection Container for IPTV-Check
Provides centralized lifecycle management and service registration.
"""
import logging
from contextlib import AsyncExitStack
from typing import Optional

logger = logging.getLogger(__name__)


class DIContainer:
    """Dependency Injection Container with lifecycle management"""
    
    def __init__(self):
        self._services = {}
        self._singletons = {}
        self._exit_stack = AsyncExitStack()
        self._is_initialized = False

    def register_singleton(self, name: str, factory):
        """Register a singleton service (created once, shared across app)"""
        self._services[name] = {"type": "singleton", "factory": factory}

    def register_transient(self, name: str, factory):
        """Register a transient service (created on each resolution)"""
        self._services[name] = {"type": "transient", "factory": factory}

    def register_instance(self, name: str, instance):
        """Register an already-created instance"""
        self._singletons[name] = instance
        self._services[name] = {"type": "instance", "instance": instance}

    async def initialize(self):
        """Initialize all singleton services"""
        if self._is_initialized:
            return
        
        await self._exit_stack.__aenter__()
        
        for name, config in self._services.items():
            if config["type"] == "singleton" and name not in self._singletons:
                try:
                    service = config["factory"]()
                    if hasattr(service, "__aenter__"):
                        service = await service.__aenter__()
                        self._exit_stack.push_async_exit(service.__aexit__)
                    elif hasattr(service, "initialize"):
                        if hasattr(service.initialize, "__await__"):
                            await service.initialize()
                        else:
                            service.initialize()
                    self._singletons[name] = service
                    logger.debug("Service initialized: %s", name)
                except Exception as e:
                    logger.error("Failed to initialize service %s: %s", name, e)
                    raise
        
        self._is_initialized = True
        logger.info("DI Container initialized with %d services", len(self._singletons))

    async def shutdown(self):
        """Shutdown all services in reverse order"""
        if not self._is_initialized:
            return
        
        await self._exit_stack.__aexit__(None, None, None)
        self._singletons.clear()
        self._is_initialized = False
        logger.info("DI Container shut down complete")

    def resolve(self, name: str):
        """Resolve a service by name"""
        if name in self._singletons:
            return self._singletons[name]
        
        config = self._services.get(name)
        if not config:
            raise KeyError(f"Service not registered: {name}")
        
        if config["type"] == "instance":
            return config["instance"]
        elif config["type"] == "singleton":
            if name not in self._singletons:
                raise RuntimeError(f"Singleton not initialized: {name}")
            return self._singletons[name]
        elif config["type"] == "transient":
            return config["factory"]()
        
        raise KeyError(f"Unknown service type: {config['type']}")

    def has(self, name: str) -> bool:
        """Check if a service is registered"""
        return name in self._services

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
