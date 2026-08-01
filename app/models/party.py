"""
Party model for Party POS.
"""

from app.models import BaseModel


class Party(BaseModel):
    _fields = ['db_name', 'name', 'start_date', 'end_date', 'modified', 'size']
    
    @property
    def display_dates(self):
        return f"{self.start_date} to {self.end_date}" if self.end_date else self.start_date
