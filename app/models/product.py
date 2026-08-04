"""
Product model for Posziona.
"""

from app.models import BaseModel


class Product(BaseModel):
    _fields = ['id', 'name', 'price', 'sku', 'section_id', 'subsection_id', 
               'stock_count', 'is_active', 'is_archived', 'tags']
    
    @property
    def display_name(self):
        return self.name
    
    @property
    def display_price(self):
        from app.utils.config import DEFAULT_CURRENCY
        return f"{DEFAULT_CURRENCY}{self.price:.2f}"
    
    @property
    def is_unlimited(self):
        return self.stock_count is None
    
    @property
    def is_in_stock(self):
        return self.is_unlimited or (self.stock_count is not None and self.stock_count > 0)
