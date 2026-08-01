"""
Tag model for Party POS.
Tags are assigned to products and carry styling rules (bg color, text color).
"""

from app.models import BaseModel


class Tag(BaseModel):
    _fields = ['id', 'name', 'color', 'bg_color', 'text_color', 'is_active']

    @property
    def display_name(self):
        return self.name

    @property
    def has_bg_color(self):
        return self.bg_color is not None

    @property
    def has_text_color(self):
        return self.text_color is not None

    @property
    def effective_color(self):
        """The badge color (default or custom)."""
        return self.color or '#3498db'
