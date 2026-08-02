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
    const dashboardBtn = document.getElementById('dashboard-btn');
    const logoutBtn = document.getElementById('logout-btn');
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
        translatePage();
    }

    function translatePage() {
        // Header buttons
        if (logoutBtn) logoutBtn.textContent = t('logout');
        if (dashboardBtn) dashboardBtn.textContent = t('reports');
        if (adminBtn) adminBtn.textContent = t('admin_panel');

        // Cart sidebar
        var currentOrderEl = document.querySelector('.order-summary h3');
        if (currentOrderEl) currentOrderEl.textContent = t('current_order');
        var subtotalLabel = document.querySelector('.cart-totals .total-row');
        if (subtotalLabel) subtotalLabel.querySelector('span').textContent = t('subtotal');
        var discountRow = document.querySelector('#discount-row');
        if (discountRow) discountRow.querySelector('span').textContent = t('discount');
        var totalRow = document.querySelector('.grand-total');
        if (totalRow) totalRow.querySelector('span').textContent = t('total');

        // Cart buttons
        if (checkoutBtn) checkoutBtn.textContent = t('checkout');
        if (discountBtn) discountBtn.textContent = t('discount_btn');
        if (clearBtn) clearBtn.textContent = t('clear');

        // Checkout modal
        var checkoutTitle = checkoutModal.querySelector('h3');
        if (checkoutTitle) checkoutTitle.textContent = t('checkout_title');

        // Cash tender modal
        var tenderTitle = cashTenderModal.querySelector('h3');
        if (tenderTitle) tenderTitle.textContent = t('cash_title');
        var tenderTotalLabel = cashTenderModal.querySelector('.grand-total span');
        if (tenderTotalLabel) {
            var spans = cashTenderModal.querySelector('.grand-total').querySelectorAll('span');
            if (spans.length > 0) spans[0].textContent = t('total_due');
        }
        var tenderLabel = cashTenderModal.querySelector('label');
        if (tenderLabel) tenderLabel.textContent = t('amount_received');
        var changeLabel = cashTenderModal.querySelector('#change-due');
        var changeParent = changeLabel && changeLabel.parentElement;
        if (changeParent) changeParent.querySelector('span').textContent = t('change_due');

        // Cash tender buttons
        var cancelTenderBtn = cashTenderModal.querySelector('#cancel-tender');
        if (cancelTenderBtn) cancelTenderBtn.textContent = t('cancel');
        var completeBtn = cashTenderModal.querySelector('#complete-cash-sale');
        if (completeBtn) completeBtn.textContent = t('complete_sale');

        // Receipt modal
        var receiptTitle = receiptModal.querySelector('h3');
        if (receiptTitle) receiptTitle.textContent = t('receipt_title');
        var printReceiptBtn = receiptModal.querySelector('#print-receipt');
        if (printReceiptBtn) printReceiptBtn.textContent = t('print_receipt');
        var closeReceiptBtn = receiptModal.querySelector('#close-receipt');
        if (closeReceiptBtn) closeReceiptBtn.textContent = t('done');

        // Cancel checkout button
        var cancelCheckoutBtn = checkoutModal.querySelector('#cancel-checkout');
        if (cancelCheckoutBtn) cancelCheckoutBtn.textContent = t('cancel');
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
            
            // Determine stock/availability
            const isOutOfStock = product.stock_count !== null && product.stock_count <= 0;
            const isInactive = !product.is_active;
            
            if (isOutOfStock || isInactive) {
                btn.classList.add('out-of-stock');
            }
            
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
            
            // Build availability dot
            let availDot = '';
            if (product.stock_count !== null) {
                availDot = `<span class="product-avail-dot${isOutOfStock ? ' out-of-stock' : ''}"></span>`;
            }
            
            // Build inner HTML with tag badges and availability dot
            let stockText = '';
            if (product.stock_count !== null && product.stock_count !== undefined) {
                stockText = `<span class="product-stock">${t('stock')}: ${product.stock_count}</span>`;
            }
            let availText = '';
            if (!product.is_active) {
                availText = `<span class="product-unavailable">${t('unavailable')}</span>`;
            }
            btn.innerHTML = `
                ${availDot}
                <div class="product-name">${product.name}</div>
                <div class="product-price">${formatCurrency(product.price)}</div>
                ${stockText ? `<div class="product-stock-row">${stockText}</div>` : ''}
                ${availText ? `<div class="product-avail-row">${availText}</div>` : ''}
                ${tagLabels ? `<div class="product-tags">${tagLabels}</div>` : ''}
            `;
            if (bgStyle) {
                btn.style.cssText = `${bgStyle}${textColor}`;
            }
            
            // Right-click context menu for price/availability editing
            btn.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                showPosContextMenu(e.pageX, e.pageY, product, btn);
            });
            
            // Only allow clicking to add if in stock and active
            if (isOutOfStock || isInactive) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                });
            } else {
                btn.addEventListener('click', () => addToCart(product));
            }
            
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
                ? subtotal * (Math.min(discount.value, 100) / 100)
                : Math.min(discount.value, subtotal)
        ) : 0;
        const total = Math.max(0, subtotal - discountAmount);

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
    if (dashboardBtn) {
        dashboardBtn.addEventListener('click', () => {
            window.location.href = '/dashboard';
        });
    }
    
    // Logout button — available to all operators (not just admin)
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            if (confirm(t('log_out_confirm'))) {
                try {
                    await fetchJSON(`${API_BASE}/auth/logout?db=${db}`, { method: 'POST' });
                } catch (e) {
                    // Ignore logout errors — still redirect
                }
                window.location.href = '/';
            }
        });
    }

    async function clearCart() {
        await fetchJSON(`${API_BASE}/cart/clear?db=${db}`, { method: 'POST' });
        cart = [];
        discount = null;
        updateCartDisplay();
    }

    // --- Discount modal ---
    function openDiscountModal() {
        if (cart.length === 0) {
            showError(t('empty_cart'));
            return;
        }

        // Build a simple discount prompt
        var discountInput = prompt(
            t('discount_prompt')
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
            showError(t('invalid_discount'));
            return;
        }

        // Clamp percentage discounts to 100% to prevent negative totals
        if (isPercentage && value > 100) {
            value = 100;
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

    async function openCheckoutModal() {
        if (cart.length === 0) {
            showError('Add items to cart first');
            return;
        }
        const subtotal = cart.reduce((sum, item) => sum + item.line_total, 0);
        const discountAmount = discount ? (
            discount.type === 'percentage'
                ? subtotal * (Math.min(discount.value, 100) / 100)
                : Math.min(discount.value, subtotal)
        ) : 0;
        const total = Math.max(0, subtotal - discountAmount);

        // If both skip_cash_tender and auto_checkout are set, skip checkout modal entirely
        // and go straight to the receipt
        if (AppState.settings &&
            AppState.settings.skip_cash_tender == '1' &&
            AppState.settings.auto_checkout == '1') {
            const method = AppState.settings.default_payment_method || 'cash';
            if (method === 'cash') {
                // For cash, create the order with tendered = total (exact amount, no change)
                try {
                    const data = await fetchJSON(`${API_BASE}/orders/checkout?db=${db}`, {
                        method: 'POST',
                        body: JSON.stringify({
                            payment_method: 'cash',
                            tendered: total
                        })
                    });
                    data.change_due = 0;
                    data.tendered = total;
                    showReceipt(data);
                } catch (e) {
                    showError(e.message || t('checkout_failed'));
                }
            } else {
                completeSale(method, total);
            }
            return;
        }

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
                    <button class="tab-btn active" onclick="selectPaymentTab('cash')">${t('cash')}</button>
                    <button class="tab-btn" onclick="selectPaymentTab('card')">${t('card')}</button>
                    <button class="tab-btn" onclick="selectPaymentTab('wallet')">${t('wallet')}</button>
                    <button class="tab-btn" onclick="selectPaymentTab('tab')">${t('tab')}</button>
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
                ? total * (Math.min(discount.value, 100) / 100)
                : Math.min(discount.value, total)
        ) : 0;
        total = total - discountAmount;

        if (method === 'cash') {
            contentEl.innerHTML = `
                <div class="total-row grand-total">
                    <span>${t('total_due')}</span>
                    <span>${formatCurrency(total)}</span>
                </div>
                <button class="btn-primary btn-block" onclick="startCashTender()">
                    ${t('enter_amount_received')}
                </button>
            `;
        } else if (method === 'card') {
            contentEl.innerHTML = `
                <button class="btn-primary btn-block" onclick="completeSale('${method}', ${total})">
                    ${t('process_card')}
                </button>
            `;
        } else if (method === 'wallet') {
            contentEl.innerHTML = `
                <button class="btn-primary btn-block" onclick="completeSale('${method}', ${total})">
                    ${t('generate_qr')}
                </button>
            `;
        } else if (method === 'tab') {
            contentEl.innerHTML = `
                <div class="form-group">
                    <label for="tab-guest">${t('guest_name')}</label>
                    <input type="text" id="tab-guest" placeholder="${t('guest_name_placeholder')}" class="form-input-block">
                </div>
                <button class="btn-primary btn-block" onclick="completeSale('${method}', ${total})">
                    ${t('charge_to_tab')}
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
        
        // Check if skip_cash_tender setting is enabled
        if (AppState.settings && AppState.settings.skip_cash_tender == '1') {
            // Auto-accept: tendered = total (exact change, no change due)
            cashTenderModal.querySelector('#tender-total').textContent = formatCurrency(total);
            cashTenderModal.querySelector('#tender-input').value = total.toFixed(2);
            cashTenderModal.querySelector('#change-due').textContent = formatCurrency(0);
            checkoutModal.classList.add('hidden');
            cashTenderModal.classList.remove('hidden');
            
            // Auto-focus and select the tender input for quick adjustment
            const tenderInput = cashTenderModal.querySelector('#tender-input');
            tenderInput.focus();
            tenderInput.select();
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
                ? subtotal * (Math.min(discount.value, 100) / 100)
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
            showError(e.message || t('checkout_failed'));
        }
    };

    // Complete cash sale with tendered amount
    window.completeCashSale = async function() {
        // Guard against double-execution: the complete-cash-sale button has both
        // an onclick handler in the HTML and an addEventListener in this module,
        // which would fire twice and create a duplicate order (double stock deduction).
        if (window._completeCashSaleInProgress) return;
        window._completeCashSaleInProgress = true;

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
            showError(e.message || t('checkout_failed'));
        }
    };

    window.cancelCheckout = function() {
        checkoutModal.classList.add('hidden');
    };

    // Build receipt text using a helper to avoid template literal escaping issues
    function buildReceipt(orderData, items, kitchenSlip) {
        // `items` defaults to the full cart; callers can pass a subset (e.g. one
        // section's items) to generate per-section mini-receipts.
        // `kitchenSlip` — when true, produce a minimal slip with just a header
        // and item quantity/name lines (no totals), suitable for giving to the
        // kitchen / cuochine. The last printed receipt is always the full
        // customer receipt.
        var receiptItems = items || cart;
        var lines = [];
        var separator = '=================================';
        if (kitchenSlip) {
            // Minimal kitchen slip: section header + item lines only
            lines.push(separator);
            lines.push('  ' + (orderData.section_name || t('items')));
            lines.push(separator);
            receiptItems.forEach(item => {
                lines.push(`  ${item.quantity} x ${item.name}`);
            });
            lines.push(separator);
            return lines.join('\n');
        }
        var subtotal = receiptItems.reduce((sum, item) => sum + item.line_total, 0);
        lines.push(separator);
        lines.push('           PARTY POS RECEIPT        ');
        lines.push(separator);
        lines.push(t('items'));
        receiptItems.forEach(item => {
            lines.push(`  ${item.name} x${item.quantity} @ ${formatCurrency(item.unit_price)}`);
        });
        lines.push('');
        lines.push(t('subtotal') + ' ' + formatCurrency(subtotal));
        if (discount) {
            var discountAmt = discount.type === 'percentage'
                ? subtotal * (discount.value / 100)
                : Math.min(discount.value, subtotal);
            lines.push(t('discount') + ' -' + formatCurrency(discountAmt));
        }
        lines.push(t('total') + ' ' + formatCurrency(orderData.total));
        lines.push(t('payment') + ' ' + orderData.payment_method);
        if (orderData.payment_method === 'cash' && orderData.change_due !== undefined) {
            lines.push(t('tendered') + ' ' + formatCurrency(orderData.tendered));
            lines.push(t('change') + ' ' + formatCurrency(orderData.change_due));
        }
        lines.push(t('order_num') + ' ' + orderData.order_id);
        lines.push(separator);
        lines.push('  ' + t('thank_you') + '  ');
        lines.push(separator);
        return lines.join('\n');
    }

    async function showReceipt(orderData) {
        var settings = AppState.settings || {};
        var splitReceipts = settings.split_receipts == '1';
        var showRecovery = settings.print_recovery_receipt == '1';

        // Fetch all products to build a product_id -> section_name map
        // so we can group cart items by section (in section order).
        var productToSection = {};
        try {
            var allProducts = await fetchJSON(`${API_BASE}/products/all?db=${db}`);
            allProducts.forEach(function(p) {
                productToSection[p.id] = p.section_name;
            });
        } catch (e) {
            console.error('Could not fetch products for receipt splitting:', e);
        }

        // Group cart items by section, following the section order loaded in
        // the POS sidebar. Items that don\'t map to a section go in "Other".
        var sectionsWithItems = [];
        sections.forEach(function(sec) {
            var items = cart.filter(function(item) {
                return productToSection[item.product_id] === sec.name;
            });
            if (items.length > 0) {
                sectionsWithItems.push({ section: sec.name, items: items });
            }
        });
        var unmatched = cart.filter(function(item) {
            return !productToSection[item.product_id];
        });
        if (unmatched.length > 0) {
            sectionsWithItems.push({ section: t('other'), items: unmatched });
        }

        var receiptEl = document.getElementById('receipt-content');
        checkoutModal.classList.add('hidden');
        receiptModal.classList.remove('hidden');

        // Always build and log the recovery (full) receipt to the server.
        var recoveryReceipt = buildReceipt(orderData);
        fetchJSON(`${API_BASE}/orders/log-receipt?db=${db}`, {
            method: 'POST',
            body: JSON.stringify({
                order_id: orderData.order_id,
                receipt: recoveryReceipt
            })
        }).catch(function(e) {
            console.error('Failed to log recovery receipt:', e);
        });

        // Display: kitchen slips per section if split_receipts is on,
        // followed by the full customer receipt. If split_receipts is off,
        // just show the single full receipt.
        if (splitReceipts) {
            var slips = sectionsWithItems.map(function(s) {
                var slipData = { section_name: s.section };
                return buildReceipt(slipData, s.items, true); // kitchen slip per section
            });
            slips.push(buildReceipt(orderData)); // full receipt last
            receiptEl.textContent = slips.join('\n\n' + t('separator') + '\n\n');
        } else {
            receiptEl.textContent = buildReceipt(orderData);
        }

        // Clear cart and reset state after showing receipt
        cart = [];
        discount = null;
        fetchJSON(`${API_BASE}/cart/clear?db=${db}`, { method: 'POST' });
        fetchJSON(`${API_BASE}/cart/remove-discount?db=${db}`, { method: 'POST' });
        updateCartDisplay();
        // Reload the product grid so stock counts and out-of-stock states
        // reflect the items that were just sold. Without this, the displayed
        // stock/availability is stale until the operator manually re-selects
        // the subsection.
        const activeSub = document.querySelector('.subsection.active');
        if (activeSub) {
            loadProducts(activeSub.dataset.subsectionId);
        }
    }

    window.closeReceipt = function() {
        receiptModal.classList.add('hidden');
        // Re-enable the complete-cash-sale button for the next checkout
        window._completeCashSaleInProgress = false;
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

    // Complete cash sale button — note: the onclick handler in pos.html already
    // calls window.completeCashSale(), so no duplicate listener is needed here.
    // (Previously both onclick and addEventListener were attached, causing the
    // function to fire twice and create a duplicate order.)

    // Cancel tender button
    const cancelTenderBtn = cashTenderModal.querySelector('#cancel-tender');
    if (cancelTenderBtn) {
        cancelTenderBtn.addEventListener('click', () => {
            window.cancelTender();
        });
    }

    // --- POS Product Context Menu (right-click) ---
    // Checks if the current operator is admin before enabling price/availability edits
    let _isAdminCache = null;
    async function checkAdmin() {
        if (_isAdminCache !== null) return _isAdminCache;
        try {
            const data = await fetchJSON(`${API_BASE}/auth/status`);
            _isAdminCache = data.operator && data.operator.role === 'admin';
        } catch (e) {
            _isAdminCache = false;
        }
        return _isAdminCache;
    }
    
    function showPosContextMenu(pageX, pageY, product, buttonEl) {
        // Remove any existing context menu
        const existing = document.getElementById('pos-context-menu');
        if (existing) existing.remove();
        
        const menu = document.createElement('div');
        menu.id = 'pos-context-menu';
        menu.className = 'pos-context-menu';
        menu.style.left = pageX + 'px';
        menu.style.top = pageY + 'px';
        
        const makeItem = (label, onclick, icon) => {
            const item = document.createElement('div');
            item.className = 'menu-item';
            item.innerHTML = `${icon || ''} <span>${label}</span>`;
            item.onclick = () => { menu.remove(); onclick(); };
            return item;
        };
        
        // Edit Price
        menu.appendChild(makeItem(
            'Edit Price',
            () => editProductPrice(product),
            '💰'
        ));
        
        // Toggle Availability
        const availLabel = product.is_active ? 'Set Unavailable' : 'Set Available';
        menu.appendChild(makeItem(
            availLabel,
            () => toggleProductAvailability(product),
            '👁️'
        ));
        
        // Close menu on outside click
        const closeMenu = () => { menu.remove(); document.removeEventListener('click', closeMenu); };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
        
        document.body.appendChild(menu);
    }
    
    async function editProductPrice(product) {
        const admin = await checkAdmin();
        if (!admin) {
            showError(t('admin_access_required'));
            return;
        }
        
        const newPriceStr = prompt('Enter new price:', String(product.price));
        if (!newPriceStr) return;
        
        const newPrice = parseFloat(newPriceStr);
        if (isNaN(newPrice) || newPrice < 0) {
            showError(t('invalid_price'));
            return;
        }
        
        try {
            await fetchJSON(`${API_BASE}/products/products/${product.id}?db=${db}`, {
                method: 'PUT',
                body: JSON.stringify({ price: newPrice })
            });
            product.price = newPrice;
            // Re-render to update displayed price
            const activeSub = document.querySelector('.subsection.active');
            if (activeSub) {
                loadProducts(activeSub.dataset.subsectionId);
            }
        } catch (e) {
            showError(e.message || t('price_update_failed'));
        }
    }
    
    async function toggleProductAvailability(product) {
        const admin = await checkAdmin();
        if (!admin) {
            showError(t('admin_access_required'));
            return;
        }
        
        const newActive = !product.is_active;
        try {
            await fetchJSON(`${API_BASE}/products/products/${product.id}?db=${db}`, {
                method: 'PUT',
                body: JSON.stringify({ is_active: newActive ? 1 : 0 })
            });
            product.is_active = newActive;
            // Re-render to update displayed state
            const activeSub = document.querySelector('.subsection.active');
            if (activeSub) {
                loadProducts(activeSub.dataset.subsectionId);
            }
        } catch (e) {
            showError(e.message || t('availability_update_failed'));
        }
    }
    
    // --- Init ---
    loadSettings();
    loadSections();
    
    // Hide admin button if user is not admin
    fetchJSON(`${API_BASE}/auth/status`)
        .then(function(data) {
            if (data.operator && data.operator.role !== 'admin') {
                if (adminBtn) {
                    adminBtn.style.display = 'none';
                }
            }
        })
        .catch(function() {
            // If auth status fails, just leave the button visible
        });
});
