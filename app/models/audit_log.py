"""
Audit log entry model for Party POS.
"""

from app.models import BaseModel


class AuditLogEntry(BaseModel):
    _fields = ['id', 'timestamp', 'action', 'details', 'operator_id']
