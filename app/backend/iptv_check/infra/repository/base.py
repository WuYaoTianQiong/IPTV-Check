"""
Repository Pattern Implementation
Provides a clean abstraction layer for data access operations.
"""

from typing import TypeVar, Generic, Type, Optional, List, Any
from sqlmodel import SQLModel, Session, select, col
from sqlalchemy import func

T = TypeVar('T', bound=SQLModel)


class Repository(Generic[T]):
    """
    Generic repository base class implementing common CRUD operations.
    Provides a clean abstraction over SQLModel/SQLAlchemy.
    """

    def __init__(self, session: Session, model: Type[T]):
        self.session = session
        self.model = model

    def get_by_id(self, id: Any) -> Optional[T]:
        """Get entity by primary key."""
        return self.session.get(self.model, id)

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all entities with pagination."""
        statement = select(self.model).offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def count(self) -> int:
        """Count total entities."""
        statement = select(func.count(self.model.id))
        return self.session.exec(statement).one()

    def add(self, entity: T) -> T:
        """Add new entity to repository."""
        self.session.add(entity)
        return entity

    def add_all(self, entities: List[T]) -> List[T]:
        """Add multiple entities."""
        self.session.add_all(entities)
        return entities

    def update(self, entity: T, update_data: dict) -> T:
        """Update entity with provided data."""
        for key, value in update_data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self.session.add(entity)
        return entity

    def delete(self, entity: T) -> None:
        """Delete entity from repository."""
        self.session.delete(entity)

    def delete_by_id(self, id: Any) -> bool:
        """Delete entity by ID. Returns True if deleted."""
        entity = self.get_by_id(id)
        if entity:
            self.delete(entity)
            return True
        return False

    def exists(self, id: Any) -> bool:
        """Check if entity exists."""
        return self.get_by_id(id) is not None


class QueryableRepository(Repository[T]):
    """
    Extended repository with query builder capabilities.
    Supports filtering, ordering, and complex queries.
    """

    def query(self, **filters) -> List[T]:
        """Query entities with filters."""
        statement = select(self.model)
        for key, value in filters.items():
            if value is not None:
                statement = statement.where(getattr(col(self.model), key) == value)
        return list(self.session.exec(statement).all())

    def query_first(self, **filters) -> Optional[T]:
        """Query first entity matching filters."""
        results = self.query(**filters)
        return results[0] if results else None

    def query_one(self, **filters) -> Optional[T]:
        """Query exactly one entity. Raises if multiple found."""
        results = self.query(**filters)
        if len(results) > 1:
            raise ValueError(f"Expected 1 result, got {len(results)}")
        return results[0] if results else None

    def query_paginated(self, skip: int = 0, limit: int = 50, **filters) -> dict:
        """Query with pagination, returns dict with items and total."""
        total = self.count()
        items = self.query(**filters)
        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }
