"""
Service Layer Module
Provides base service class and service lifecycle management.
"""

import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """
    Abstract base class for all application services.
    Provides common lifecycle management and logging.
    """

    def __init__(self, name: str = "BaseService"):
        self._name = name
        self._initialized = False
        self._logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self) -> None:
        """Initialize the service. Called once during application startup."""
        if self._initialized:
            return
        try:
            await self._do_initialize()
            self._initialized = True
            self._logger.info("Service initialized: %s", self._name)
        except Exception as e:
            self._logger.error("Service initialization failed: %s - %s", self._name, e)
            raise

    async def shutdown(self) -> None:
        """Shutdown the service. Called once during application shutdown."""
        if not self._initialized:
            return
        try:
            await self._do_shutdown()
            self._initialized = False
            self._logger.info("Service shutdown: %s", self._name)
        except Exception as e:
            self._logger.error("Service shutdown failed: %s - %s", self._name, e)
            raise

    @abstractmethod
    async def _do_initialize(self) -> None:
        """Override to implement service-specific initialization."""
        pass

    @abstractmethod
    async def _do_shutdown(self) -> None:
        """Override to implement service-specific cleanup."""
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if service is initialized."""
        return self._initialized

    @property
    def name(self) -> str:
        """Get service name."""
        return self._name

    @property
    def logger(self) -> logging.Logger:
        """Get service logger."""
        return self._logger


class StatelessService(BaseService):
    """
    Base class for stateless services (no async initialization needed).
    Suitable for utility services like converters, validators, etc.
    """

    async def _do_initialize(self) -> None:
        pass

    async def _do_shutdown(self) -> None:
        pass


class SingletonMixin:
    """
    Mixin to ensure only one instance of a service exists.
    Thread-safe singleton implementation.
    """
    _instance: Optional["SingletonMixin"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
