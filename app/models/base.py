"""Base model with common fields and functionality."""
from datetime import datetime
from typing import Any
from sqlalchemy import Column, Integer, DateTime, Boolean
from sqlalchemy.ext.declarative import declared_attr
from app.extensions import db


class BaseModel(db.Model):
    """Base model class with common fields."""
    
    __abstract__ = True
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert model instance to dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result
    
    def save(self) -> "BaseModel":
        """Save model instance to database."""
        db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self) -> bool:
        """Delete model instance from database."""
        db.session.delete(self)
        db.session.commit()
        return True
    
    @classmethod
    def create(cls, **kwargs) -> "BaseModel":
        """Create new model instance."""
        instance = cls(**kwargs)
        return instance.save()


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""
    
    @declared_attr
    def deleted_at(cls):
        return Column(DateTime, nullable=True)
    
    @declared_attr
    def is_deleted(cls):
        return Column(Boolean, default=False, nullable=False)
    
    def soft_delete(self) -> None:
        """Soft delete the record."""
        self.deleted_at = datetime.utcnow()
        self.is_deleted = True
        db.session.commit()
    
    def restore(self) -> None:
        """Restore soft deleted record."""
        self.deleted_at = None
        self.is_deleted = False
        db.session.commit()