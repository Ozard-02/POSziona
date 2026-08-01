"""
Data models for Party POS.
"""

class BaseModel:
    """Base class for all data models."""
    
    _fields = []
    
    def __init__(self, **kwargs):
        for field in self._fields:
            setattr(self, field, kwargs.get(field))
    
    def to_dict(self):
        return {field: getattr(self, field, None) for field in self._fields}
    
    @classmethod
    def from_row(cls, row):
        """Create model instance from a database row."""
        if row is None:
            return None
        if hasattr(row, 'keys'):
            return cls(**{key: row[key] for key in row.keys()})
        else:
            return cls(**dict(zip(cls._fields, row)))
