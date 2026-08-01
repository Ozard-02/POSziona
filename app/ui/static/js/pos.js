/* POS screen JavaScript */
document.addEventListener('DOMContentLoaded', function() {
    const db = 'default';
    
    // DOM elements
    const sectionsTree = document.getElementById('sections-tree');
    const productsGrid = document.getElementById('products-grid');
    const cartItemsEl = document.getElementById('cart-items');
    const cartSubtotalEl = document.getElementById('cart-subtotal');
    const cartDiscountEl = document.getElementById('cart-discount');
    const cartTotalEl = document.getElementById('cart-total');
    const discountRow = document.getElementById('discount-row');
    const checkoutBtn = document.getElementById('checkout-btn');
    const clearBtn = document.getElementById('clear-btn');
    const discountBtn = document.getElementById('discount-btn');
    const adminBtn = document.getElementById('admin-btn');
    const checkoutModal = document.getElementById('checkout-modal');
    const receiptModal = document.getElementById('receipt-modal');
    const cashTenderModal = document.getElementById('cash-tender-modal');
    
    // Current cart state
    let cart = [];
    let discount = null;
    let sections = [];

    // --- Load settings ---
    async function loadSettings() {
        try {
            AppState.settings = await fetchJSON(`${API_BASE}/settings/?db=${db}`);
        } catch (e) {
            console.error('Failed to load settings:', e);
            AppState.settings = {};
        }
    }
    
    // --- Load sections ---
    async function loadSections() {
        try {
            const data = await fetchJSON(`${API_BASE}/products/?db=${db}`);
            sections = data;
            renderSections();
        } catch (e) {
            console.error('Failed to load sections:', e);
        }
    }

    function renderSections() {
        sectionsTree.innerHTML = '';
        sections.forEach(section => {
            const sectionDiv = document.createElement('div');
            sectionDiv.className = 'section';
            sectionDiv.innerHTML = `<h3>${section.name}</h3>`;
            
            const subsectionsDiv = document.createElement('div');
            subsectionsDiv.className = 'subsections';
            
            (section.subsections || []).forEach(sub => {
                const subDiv = document.createElement('div');
                subDiv.className = 'subsection';
                subDiv.textContent = sub.name;
                subDiv.dataset.subsectionId = sub.id;
                subDiv.addEventListener('click', () => {
                    document.querySelectorAll('.subsection').forEach(s => s.classList.remove('active'));
                    subDiv.classList.add('active');
                    loadProducts(sub.id);
                });
                subsectionsDiv.appendChild(subDiv);
            });
            
            sectionDiv.appendChild(subsectionsDiv);
            sectionsTree.appendChild(sectionDiv);
        });
        
        // Select first subsection by default
        const firstSub = sectionsTree.querySelector('.subsection');
        if (firstSub) {
            firstSub.click();
        }
    }

    // --- Load products ---
    async function loadProducts(subsectionId) {
        try {
            const data = await fetchJSON(`${API_BASE}/products/${subsectionId}/products?db=${db}`);
            renderProducts(data);
        } catch (e) {
            console.error('Failed to load products:', e);
        }
    }

    function renderProducts(products) {
        productsGrid.innerHTML = '';
        products.forEach(product => {
            const btn = document.createElement('button');
            btn.className = 'product-btn';
            btn.dataset.productId = product.id;

            // Apply tag-based background color if any tag has bg_color
            let bgStyle = '';
            let textColor = '';
            let tagLabels = '';
            if (product.tags && product.tags.length > 0) {
                // Use the first tag's bg_color/text_color for the product button background
                const primaryTag = product.tags[0];
                if (primaryTag.bg_color) {
                    bgStyle = `background-color: ${primaryTag.bg_color};`;
                    if (primaryTag.text_color) {
                        textColor = `color: ${primaryTag.text_color};`;
                    }
                }
                // Build tag label badges
                tagLabels = product.tags.map(t =>
                    `<span class="tag-badge" style="background-color: ${t.color || '#3498db'};">${t.name}</span>`
                ).join('');
            }

            // Build inner HTML with tag badges
            btn.innerHTML = `
                <div class="product-name">${product.name}</div>
                <div class="product-price">${formatCurrency(product.price)}</div>
                ${tagLabels ? `<div class="product-tags">${tagLabels}</div>` : ''}
            `;
            if (bgStyle) {
                btn.style.cssText = `${bgStyle}${textColor}`;
            }
            btn.addEventListener('click', () => addToCart(product));
            productsGrid.appendChild(btn);
        });
    }

    // --- Cart operations ---
    async function addToCart(product) {
        try {
            const data = await fetchJSON(`${API_BASE}/cart/add?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ product_id: product.id, quantity: 1 })
            });
            cart = data.cart;
            updateCartDisplay();
        } catch (e) {
            console.error('Failed to add to cart:', e);
            if (e.includes) {
                showError(e);
            }
        }
    }

    function updateCartDisplay() {
        cartItemsEl.innerHTML = '';
        cart.forEach(item => {
            const div = document.createElement('div');
            div.className = 'cart-item';
            div.innerHTML = `
                <div class="item-info">
                    <span class="item-name">${item.name}</span>
                    <span class="item-price">${formatCurrency(item.unit_price)} × ${item.quantity}</span>
                </div>
                <div class="item-controls">
                    <button class="qty-btn qty-minus" data-id="${item.product_id}" title="Decrease">−</button>
                    <button class="qty-btn qty-plus" data-id="${item.product_id}" title="Increase">+</button>
                    <button class="remove-btn" data-id="${item.product_id}" title="Remove item">×</button>
                    <span class="item-total">${formatCurrency(item.line_total)}</span>
                </div>
            `;
            cartItemsEl.appendChild(div);
        });

        const subtotal = cart.reduce((sum, item) => sum + item.line_total, 0);
        const discountAmount = discount ? (
            discount.type === 'percentage'
                ? subtotal * (discount.value / 100)
                : Math.min(discount.value, subtotal)
        ) : 0;
        const total = subtotal - discountAmount;

        cartSubtotalEl.textContent = formatCurrency(subtotal);
        cartTotalEl.textContent = formatCurrency(total);

        if (discount) {
            discountRow.style.display = 'block';
            cartDiscountEl.textContent = `-${formatCurrency(discountAmount)}`;
        } else {
            discountRow.style.display = 'none';
        }
    }

    // --- Cart item event handlers ---
    cartItemsEl.addEventListener('click', async function(e) {
        const minusBtn = e.target.closest('.qty-minus');
        const plusBtn = e.target.closest('.qty-plus');
        const removeBtn = e.target.closest('.remove-btn');

        if (minusBtn) {
            const productId = parseInt(minusBtn.dataset.id);
            const item = cart.find(i => i.product_id === productId);
            if (item && item.quantity > 1) {
                const data = await fetchJSON(`${API_BASE}/cart/update?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({ product_id: productId, quantity: item.quantity - 1 })
                });
                cart = data.cart;
                updateCartDisplay();
            }
        }

        if (plusBtn) {
            const productId = parseInt(plusBtn.dataset.id);
            const item = cart.find(i => i.product_id === productId);
            if (item) {
                const data = await fetchJSON(`${API_BASE}/cart/update?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({ product_id: productId, quantity: item.quantity + 1 })
                });
                cart = data.cart;
                updateCartDisplay();
            }
        }

        if (removeBtn) {
            const productId = parseInt(removeBtn.dataset.id);
            const data = await fetchJSON(`${API_BASE}/cart/remove?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ product_id: productId })
            });
            cart = data.cart;
            discount = null;
            updateCartDisplay();
            // Also clear discount on backend
            fetchJSON(`${API_BASE}/cart/remove-discount?db=${db}`, { method: 'POST' });
        }
    });

    // --- Button handlers ---
    checkoutBtn.addEventListener('click', openCheckoutModal);
    clearBtn.addEventListener('click', clearCart);
    discountBtn.addEventListener('click', openDiscountModal);
    adminBtn.addEventListener('click', () => {
        window.location.href = '/admin';
    });

    async function clearCart() {
        await fetchJSON(`${API_BASE}/cart/clear?db=${db}`, { method: 'POST' });
        cart = [];
        discount = null;
        updateCartDisplay();
    }

    // --- Discount modal ---
    function openDiscountModal() {
        if (cart.length === 0) {
            showError('Add items to cart first');
            return;
        }

        // Build a simple discount prompt
        var discountInput = prompt(
            "Enter discount:\n" +
            "For percentage: enter like '10%'\n" +
            "For fixed amount: enter like '5' (€5 off total)\n" +
            "Leave blank to remove discount"
        );

        if (discountInput === null) return; // User cancelled

        discountInput = discountInput.trim();

        if (discountInput === '') {
            // Remove discount
            fetchJSON(`${API_BASE}/cart/remove-discount?db=${db}`, { method: 'POST' });
            discount = null;
            updateCartDisplay();
            return;
        }

        // Parse discount
        var isPercentage = discountInput.endsWith('%');
        var value = parseFloat(discountInput.replace('%', '').trim());

        if (isNaN(value) || value < 0) {
            showError('Invalid discount value');
            return;
        }

        // Apply discount via API
        var discountType = isPercentage ? 'percentage' : 'fixed';
        fetchJSON(`${API_BASE}/cart/discount?db=${db}`, {
            method: 'POST',
            body: JSON.stringify({ type: discountType, value: value })
        }).then(function(data) {
            discount = {
                type: discountType,
                value: value
            };
            updateCartDisplay();
        }).catch(function(e) {
            console.error('Failed to apply discount:', e);
        });
    }

    function openCheckoutModal() {
        const subtotal = cart.reduce((sum, item) => sum + item.line_total, 0);
        const discountAmount = discount ? (
            discount.type === 'percentage'
                ? subtotal * (discount.value / 100)
                : Math.min(discount.value, subtotal)
        ) : 0;
        const total = subtotal - discountAmount;

        // Show subtotal, discount, and total in checkout modal
        const checkoutSubtotalEl = checkoutModal.querySelector('#checkout-subtotal');
        const checkoutDiscountRow = checkoutModal.querySelector('#checkout-discount-row');
        const checkoutDiscountEl = checkoutModal.querySelector('#checkout-discount');
        const checkoutTotalEl = checkoutModal.querySelector('#checkout-total');

        if (checkoutSubtotalEl) checkoutSubtotalEl.textContent = formatCurrency(subtotal);
        if (discount) {
            if (checkoutDiscountRow) checkoutDiscountRow.style.display = 'block';
            if (checkoutDiscountEl) checkoutDiscountEl.textContent = `-${formatCurrency(discountAmount)}`;
        } else {
            if (checkoutDiscountRow) checkoutDiscountRow.style.display = 'none';
        }
        if (checkoutTotalEl) checkoutTotalEl.textContent = formatCurrency(total);

        // Check for default payment method — if set, skip payment selection
        fetchJSON(`${API_BASE}/settings/default-payment?db=${db}`)
            .then(function(settingsData) {
                var defaultMethod = settingsData.default_payment_method;
                if (defaultMethod) {
                    // Skip payment selection, go straight to sale
                    completeSale(defaultMethod, total);
                } else {
                    // Show payment method tabs
                    renderPaymentMethods(total);
                }
            })
            .catch(function() {
                // If API fails, just show payment methods
                renderPaymentMethods(total);
            });

        checkoutModal.classList.remove('hidden');
    }

    // Phase 2: Payment method tabs instead of flat buttons
    function renderPaymentMethods(total) {
        var container = checkoutModal.querySelector('#payment-methods');
        container.innerHTML = `
            <div class="payment-tabs">
                <div class="payment-tab-nav">
                    <button class="tab-btn active" onclick="selectPaymentTab('cash')">Cash</button>
                    <button class="tab-btn" onclick="selectPaymentTab('card')">Card</button>
                    <button class="tab-btn" onclick="selectPaymentTab('wallet')">Digital Wallet</button>
                    <button class="tab-btn" onclick="selectPaymentTab('tab')">On Tab</button>
                </div>
                <div class="payment-tab-content" id="payment-tab-content">
                    <!-- Dynamic content based on selected tab -->
                </div>
            </div>
        `;
        // Default to cash tab
        selectPaymentTab('cash');
    }

    window.selectPaymentTab = function(method) {
        // Update active tab
        const tabs = checkoutModal.querySelectorAll('.tab-btn');
        tabs.forEach(t => t.classList.remove('active'));
        const activeTab = checkoutModal.querySelector(`.tab-btn[onclick="selectPaymentTab('${method}')"]`);
        if (activeTab) activeTab.classList.add('active');

        // Update content
        const contentEl = checkoutModal.querySelector('#payment-tab-content');
        if (!contentEl) return;

        var total = cart.reduce((sum, item) => sum + item.line_total, 0);
        const discountAmount = discount ? (
            discount.type === 'percentage'
                ? total * (discount.value / 100)
                : Math.min(discount.value, total)
        ) : 0;
        total = total - discountAmount;

        if (method === 'cash') {
            contentEl.innerHTML = `
                <div class="total-row grand-total">
                    <span>Total Due:</span>
                    <span>${formatCurrency(total)}</span>
                </div>
                <button class="btn-primary" style="width:100%; margin-top: 10px;" onclick="startCashTender()">
                    Enter Amount Received
                </button>
            `;
        } else if (method === 'card') {
            contentEl.innerHTML = `
                <button class="btn-primary" style="width:100%; margin-top: 10px;" onclick="completeSale('${method}', ${total})">
                    Process Card Payment
                </button>
            `;
        } else if (method === 'wallet') {
            contentEl.innerHTML = `
                <button class="btn-primary" style="width:100%; margin-top: 10px;" onclick="completeSale('${method}', ${total})">
                    Generate QR Code
                </button>
            `;
        } else if (method === 'tab') {
            contentEl.innerHTML = `
                <div class="form-group">
                    <label for="tab-guest">Guest Name:</label>
                    <input type="text" id="tab-guest" placeholder="Enter guest name" style="width:100%;">
                </div>
                <button class="btn-primary" style="width:100%; margin-top: 10px;" onclick="completeSale('${method}', ${total})">
                    Charge to Tab
                </button>
            `;
        }
    };

    window.startCashTender = function() {
        const total = getCartTotal();
        
        // If total is 0 (e.g. 100% discount), skip the tender screen
        if (total === 0) {
            window.completeCashSale();
            return;
        }
        
        cashTenderModal.querySelector('#tender-total').textContent = formatCurrency(total);
        cashTenderModal.querySelector('#tender-input').value = '';
        cashTenderModal.querySelector('#change-due').textContent = formatCurrency(0);

        checkoutModal.classList.add('hidden');
        cashTenderModal.classList.remove('hidden');

        // Focus and select the tender input
        const tenderInput = cashTenderModal.querySelector('#tender-input');
        tenderInput.focus();
        tenderInput.select();
    };

    window.cancelTender = function() {
        cashTenderModal.classList.add('hidden');
        checkoutModal.classList.remove('hidden');
    };

    // Handle tender input — calculate change in real-time
    const tenderInput = document.getElementById('tender-input');
    if (tenderInput) {
        tenderInput.addEventListener('input', function() {
            const tend = parseFloat(this.value) || 0;
            const total = getCartTotal();
            const change = tend - total;
            const changeEl = cashTenderModal.querySelector('#change-due');
            if (changeEl) {
                changeEl.textContent = formatCurrency(Math.max(0, change));
                changeEl.style.color = change < 0 ? '#e74c3c' : '#27ae60';
            }
        });

        // Handle Enter key
        tenderInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                window.completeCashSale();
            }
        });
    }

    function getCartTotal() {
        const subtotal = cart.reduce((sum, item) => sum + item.line_total, 0);
        const discountAmount = discount ? (
            discount.type === 'percentage'
                ? subtotal * (discount.value / 100)
                : Math.min(discount.value, subtotal)
        ) : 0;
        return subtotal - discountAmount;
    }

    // Make completeSale available globally — handles all non-cash methods
    window.completeSale = async function(paymentMethod, totalAmount) {
        try {
            if (paymentMethod === 'cash') {
                // For cash, go through the tender screen
                startCashTender();
                return;
            }

            const data = await fetchJSON(`${API_BASE}/orders/checkout?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ payment_method: paymentMethod })
            });

            showReceipt(data);
        } catch (e) {
            showError(e.message || 'Checkout failed');
        }
    };

    // Complete cash sale with tendered amount
    window.completeCashSale = async function() {
        const tenderInput = document.getElementById('tender-input');
        const tend = parseFloat(tenderInput.value) || 0;
        const total = getCartTotal();

        // If no amount entered, use total as tendered (exact amount, no change)
        let tendered = tend;
        if (total === 0) {
            tendered = 0;
        } else if (tend === 0 || tend < total) {
            tendered = total;
        }

        try {
            const data = await fetchJSON(`${API_BASE}/orders/checkout?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    payment_method: 'cash',
                    tendered: tendered
                })
            });

            // Store change due for receipt display
            data.change_due = tendered - data.total;
            data.tendered = tendered;

            cashTenderModal.classList.add('hidden');
            showReceipt(data);
        } catch (e) {
            showError(e.message || 'Checkout failed');
        }
    };

    window.cancelCheckout = function() {
        checkoutModal.classList.add('hidden');
    };

    // Build receipt text using a helper to avoid template literal escaping issues
    function buildReceipt(orderData) {
        var subtotal = cart.reduce((sum, item) => sum + item.line_total, 0);
        var lines = [];
        lines.push('=================================');
        lines.push('           PARTY POS RECEIPT        ');
        lines.push('=================================');
        lines.push('Items:');
        cart.forEach(item => {
            lines.push(`  ${item.name} x${item.quantity} @ ${formatCurrency(item.unit_price)}`);
        });
        lines.push('');
        lines.push(`Subtotal: ${formatCurrency(subtotal)}`);
        if (discount) {
            var discountAmt = discount.type === 'percentage'
                ? subtotal * (discount.value / 100)
                : Math.min(discount.value, subtotal);
            lines.push(`Discount: -${formatCurrency(discountAmt)}`);
        }
        lines.push(`Total: ${formatCurrency(orderData.total)}`);
        lines.push(`Payment: ${orderData.payment_method}`);
        if (orderData.payment_method === 'cash' && orderData.change_due !== undefined) {
            lines.push(`Tendered: ${formatCurrency(orderData.tendered)}`);
            lines.push(`Change: ${formatCurrency(orderData.change_due)}`);
        }
        lines.push(`Order #: ${orderData.order_id}`);
        lines.push('=================================');
        lines.push('  Thank you for your purchase!  ');
        lines.push('=================================');
        return lines.join('\n');
    }

    function showReceipt(orderData) {
        var receiptEl = document.getElementById('receipt-content');
        receiptEl.textContent = buildReceipt(orderData);
        checkoutModal.classList.add('hidden');
        receiptModal.classList.remove('hidden');

        // Clear cart and reset state after showing receipt
        cart = [];
        discount = null;
        fetchJSON(`${API_BASE}/cart/clear?db=${db}`, { method: 'POST' });
        fetchJSON(`${API_BASE}/cart/remove-discount?db=${db}`, { method: 'POST' });
        updateCartDisplay();
    }

    window.closeReceipt = function() {
        receiptModal.classList.add('hidden');
    };

    // --- Button event handlers (set up after DOM elements exist) ---
    // Cancel checkout button
    const cancelCheckoutBtn = checkoutModal.querySelector('#cancel-checkout');
    if (cancelCheckoutBtn) {
        cancelCheckoutBtn.addEventListener('click', () => {
            checkoutModal.classList.add('hidden');
        });
    }

    // Print receipt button
    const printReceiptBtn = receiptModal.querySelector('#print-receipt');
    if (printReceiptBtn) {
        printReceiptBtn.addEventListener('click', () => {
            // Try to print the receipt
            const receiptContent = document.getElementById('receipt-content').textContent;
            if (receiptContent) {
                const printWindow = window.open('', '_blank');
                printWindow.document.write(`<pre>${receiptContent.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>`);
                printWindow.document.title = 'Party POS Receipt';
                printWindow.focus();
                printWindow.print();
                printWindow.close();
            }
        });
    }

    // Close receipt button
    const closeReceiptBtn = receiptModal.querySelector('#close-receipt');
    if (closeReceiptBtn) {
        closeReceiptBtn.addEventListener('click', () => {
            receiptModal.classList.add('hidden');
        });
    }

    // Complete cash sale button (in cash tender modal)
    const completeCashSaleBtn = cashTenderModal.querySelector('#complete-cash-sale');
    if (completeCashSaleBtn) {
        completeCashSaleBtn.addEventListener('click', () => {
            window.completeCashSale();
        });
    }

    // Cancel tender button
    const cancelTenderBtn = cashTenderModal.querySelector('#cancel-tender');
    if (cancelTenderBtn) {
        cancelTenderBtn.addEventListener('click', () => {
            window.cancelTender();
        });
    }

    // --- Init ---
    loadSettings();
    loadSections();
});
