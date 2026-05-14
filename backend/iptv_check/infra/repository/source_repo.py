"""
Source Repository
Specialized repository for OnlineSource operations.
Note: OnlineSource is not a SQLModel entity, so this repository manages JSON file storage.
"""

import json
import os
import logging
from typing import Optional, List

from iptv_check.models.source import OnlineSource

logger = logging.getLogger(__name__)


class SourceRepository:
    """
    Repository for OnlineSource entity operations.
    Manages loading and saving sources from local_sources.json.
    """

    def __init__(self, sources_file: str):
        self._sources_file = sources_file
        self._sources: List[OnlineSource] = []
        self._load_sources()

    def _load_sources(self) -> None:
        """Load sources from JSON file."""
        try:
            if os.path.exists(self._sources_file):
                with open(self._sources_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._sources = [OnlineSource.from_dict(s) for s in data.get("sources", [])]
                logger.info("Loaded %d online sources from %s", len(self._sources), self._sources_file)
            else:
                logger.warning("Sources file not found: %s", self._sources_file)
                self._sources = []
        except Exception as e:
            logger.error("Failed to load sources: %s", e)
            self._sources = []

    def save_sources(self) -> None:
        """Save sources to JSON file."""
        try:
            data = {
                "sources": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "url": s.url,
                        "isp": s.isp,
                        "protocol": s.protocol,
                        "features": s.features,
                        "description": s.description,
                        "category": s.category,
                        "mirror_url": s.mirror_url,
                        "disabled": s.disabled,
                    }
                    for s in self._sources
                ]
            }
            os.makedirs(os.path.dirname(self._sources_file), exist_ok=True)
            with open(self._sources_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Saved %d online sources to %s", len(self._sources), self._sources_file)
        except Exception as e:
            logger.error("Failed to save sources: %s", e)

    def get_all(self, enabled_only: bool = True) -> List[OnlineSource]:
        """Get all sources, optionally filtering by enabled status."""
        if enabled_only:
            return [s for s in self._sources if not s.disabled]
        return self._sources.copy()

    def get_by_id(self, source_id: str) -> Optional[OnlineSource]:
        """Get source by ID."""
        for source in self._sources:
            if source.id == source_id:
                return source
        return None

    def get_by_category(self, category: str) -> List[OnlineSource]:
        """Get sources by category."""
        return [s for s in self._sources if s.category == category and not s.disabled]

    def get_enabled(self) -> List[OnlineSource]:
        """Get all enabled sources."""
        return [s for s in self._sources if not s.disabled]

    def add_source(self, source: OnlineSource) -> None:
        """Add a new source."""
        if self.get_by_id(source.id):
            raise ValueError(f"Source with ID {source.id} already exists")
        self._sources.append(source)
        self.save_sources()
        logger.info("Added source: %s", source.name)

    def update_source(self, source_id: str, update_data: dict) -> Optional[OnlineSource]:
        """Update an existing source."""
        source = self.get_by_id(source_id)
        if not source:
            return None
        for key, value in update_data.items():
            if hasattr(source, key):
                setattr(source, key, value)
        self.save_sources()
        logger.info("Updated source: %s", source.name)
        return source

    def delete_source(self, source_id: str) -> bool:
        """Delete a source by ID."""
        for i, source in enumerate(self._sources):
            if source.id == source_id:
                self._sources.pop(i)
                self.save_sources()
                logger.info("Deleted source: %s", source.name)
                return True
        return False

    def get_categories(self) -> List[str]:
        """Get all unique source categories."""
        categories = set()
        for source in self._sources:
            if not source.disabled:
                categories.add(source.category)
        return sorted(categories)

    def count(self, enabled_only: bool = True) -> int:
        """Count total sources."""
        if enabled_only:
            return len([s for s in self._sources if not s.disabled])
        return len(self._sources)
