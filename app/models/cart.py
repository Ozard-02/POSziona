"""
Cart model for Posziona.
"""

from app.models import BaseModel


class CartItem(BaseModel):
    _fields = ['product_id', 'name', 'unit_price', 'quantity', 'line_total']


class Cart(BaseModel):
    _fields = ['items', '_discount_type', '_discount_amount']
    
    def __init__(self):
        self.items = []
        self._discount_type = None
        self._discount_amount = 0.0
    
    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items)
    
    @property
    def discount_amount(self):
        if self._discount_type == 'percentage':
            # Clamp to 100% to prevent negative totals
            pct = min(self._discount_amount, 100)
            return self.subtotal * (pct / 100)
        elif self._discount_type == 'fixed':
            return min(self._discount_amount, self.subtotal)
        return 0.0
    
    @property
    def total(self):
        return self.subtotal - self.discount_amount
    
    def add_item(self, product):
        """Add a product to the cart."""
        for item in self.items:
            if item.product_id == product.id:
                item.quantity += 1
                item.line_total = item.quantity * item.unit_price
                return
        self.items.append(CartItem(
            product_id=product.id,
            name=product.name,
            unit_price=product.price,
            quantity=1,
            line_total=product.price
        ))
    
    def remove_item(self, product_id):
        """Remove a product from the cart."""
        self.items = [item for item in self.items if item.product_id != product_id]
    
    def update_quantity(self, product_id, quantity):
        """Update quantity of an item in the cart."""
        if quantity < 1:
            quantity = 1
        for item in self.items:
            if item.product_id == product_id:
                item.quantity = quantity
                item.line_total = item.quantity * item.unit_price
                return
    
    def apply_discount(self, discount_type, value):
        """Apply a percentage or fixed discount."""
        self._discount_type = discount_type
        self._discount_amount = value
    
    def clear_discount(self):
        """Remove any applied discount."""
        self._discount_type = None
        self._discount_amount = 0.0
    
    def clear(self):
        """Clear the cart."""
        self.items = []
        self.clear_discount()
    
    def is_empty(self):
        return len(self.items) == 0
