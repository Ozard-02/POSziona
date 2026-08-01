"""
Order model for Party POS.
"""

from app.models import BaseModel


class OrderItem(BaseModel):
    _fields = ['id', 'product_id', 'quantity', 'unit_price']
    
    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Order(BaseModel):
    _fields = ['id', 'timestamp', 'subtotal', 'discount_amount', 'discount_type',
               'total', 'payment_method', 'operator_id']
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.items = []


class Payment(BaseModel):
    _fields = ['id', 'order_id', 'method', 'amount', 'tendered', 'change_due', 'timestamp']
