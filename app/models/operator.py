"""
Operator model for Posziona.
"""

from app.models import BaseModel


class Operator(BaseModel):
    _fields = ['id', 'name', 'pin_hash', 'role', 'is_active']
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def display_role(self):
        return 'Admin' if self.is_admin else 'Operator'
