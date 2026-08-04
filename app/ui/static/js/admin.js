/* Admin panel JavaScript */
document.addEventListener('DOMContentLoaded', function() {
    const db = 'default';
    
    // DOM elements
    const sections = document.querySelectorAll('.admin-section');
    const navLinks = document.querySelectorAll('.admin-nav a');
    const logoutBtn = document.getElementById('logout-admin');
    
    // === Navigation ===
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const target = this.dataset.section;
            
            // Hide all sections
            sections.forEach(s => s.classList.remove('active'));
            
            // Show target section
            document.getElementById(`admin-${target}`).classList.add('active');
            
            // Load section data
            switch(target) {
                case 'dashboard': loadDashboard(); break;
                case 'products': loadProducts(); break;
                case 'parties': loadParties(); break;
                case 'operators': loadOperators(); break;
                case 'settings': loadSettings(); break;
                case 'tags': loadTags(); break;
                case 'sections': loadSections(); break;
            }
        });
    });
    
    logoutBtn.addEventListener('click', function() {
        fetchJSON(`${API_BASE}/auth/logout?db=${db}`, { method: 'POST' })
            .then(() => { window.location.href = '/'; })
            .catch(() => { window.location.href = '/'; });
    });
    
    const backBtn = document.getElementById('back-to-pos');
    if (backBtn) {
        backBtn.addEventListener('click', function() {
            window.location.href = '/pos';
        });
    }
    
    // === Dashboard ===
    async function loadDashboard() {
        try {
            const summary = await fetchJSON(`${API_BASE}/orders/report/summary?db=${db}`);
            document.getElementById('stat-revenue').textContent = formatCurrency(summary.total_revenue);
            document.getElementById('stat-orders').textContent = summary.total_orders;
            
            const items = await fetchJSON(`${API_BASE}/orders/report/items?db=${db}`);
            const tbody = document.querySelector('#items-sold-table tbody');
            tbody.innerHTML = '';
            items.forEach(item => {
                const row = tbody.insertRow();
                row.dataset.productId = item.product_id;
                row.insertCell(0).textContent = item.product_name;
                row.insertCell(1).textContent = item.total_quantity;
                row.insertCell(2).textContent = formatCurrency(item.total_amount);
                row.insertCell(3).textContent = formatCurrency(item.current_price);
                const stock = item.stock_count === null ? 'Unlimited' : String(item.stock_count);
                row.insertCell(4).textContent = stock;
                const availCell = row.insertCell(5);
                availCell.textContent = item.is_active ? 'Yes' : 'No';
                availCell.style.color = item.is_active ? '#27ae60' : '#e74c3c';
                availCell.style.fontWeight = 'bold';
            });

            // Right-click context menu on dashboard item rows
            tbody.addEventListener('contextmenu', function(e) {
                e.preventDefault();
                const row = e.target.closest('tr');
                if (!row) return;
                const productId = row.dataset.productId;
                showItemContextMenu(e.pageX, e.pageY, productId, row);
            });

            // Wire up export recap button
            const exportBtn = document.getElementById('export-recap-btn-dashboard');
            if (exportBtn) {
                exportBtn.onclick = () => exportRecapCsv();
            }
        } catch (e) {
            console.error('Dashboard load failed:', e);
        }
    }

    async function exportRecapCsv() {
        try {
            const response = await fetch(`${API_BASE}/orders/report/export-csv?db=${db}`, {
                method: 'GET',
            });
            if (!response.ok) {
                throw new Error('Export failed');
            }
            const csvText = await response.text();
            const blob = new Blob([csvText], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'party-recap.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('Failed to export recap: ' + (e.message || e));
        }
    }

    function showItemContextMenu(pageX, pageY, productId, row) {
        // Remove any existing context menu
        const existing = document.getElementById('item-context-menu');
        if (existing) existing.remove();

        const menu = document.createElement('div');
        menu.id = 'item-context-menu';
        menu.className = 'admin-context-menu';
        menu.style.left = pageX + 'px';
        menu.style.top = pageY + 'px';

        const makeItem = (label, onclick) => {
            const item = document.createElement('div');
            item.textContent = label;
            item.className = 'context-menu-item';
                        item.onclick = () => { menu.remove(); onclick(); };
            return item;
        };

        menu.appendChild(makeItem('Edit Price', () => editItemPrice(productId, row)));
        menu.appendChild(makeItem('Set Available', () => setItemAvailability(productId, true, row)));
        menu.appendChild(makeItem('Set Unavailable', () => setItemAvailability(productId, false, row)));

        document.body.appendChild(menu);

        const closeMenu = () => { menu.remove(); document.removeEventListener('click', closeMenu); };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
    }

    async function editItemPrice(productId, row) {
        const currentPriceCell = row.cells[3];
        const currentPrice = parseFloat(currentPriceCell.textContent.replace(/[€$]/, ''));
        const newPriceStr = prompt('Enter new price:', String(currentPrice));
        if (!newPriceStr) return;
        const newPrice = parseFloat(newPriceStr);
        if (isNaN(newPrice) || newPrice < 0) {
            alert('Please enter a valid price');
            return;
        }
        try {
            await fetchJSON(`${API_BASE}/products/products/${productId}?db=${db}`, {
                method: 'PUT',
                body: JSON.stringify({ price: newPrice })
            });
            currentPriceCell.textContent = formatCurrency(newPrice);
        } catch (e) {
            alert('Failed to update price: ' + (e.message || e));
        }
    }

    async function setItemAvailability(productId, available, row) {
        try {
            await fetchJSON(`${API_BASE}/products/products/${productId}?db=${db}`, {
                method: 'PUT',
                body: JSON.stringify({ is_active: available ? 1 : 0 })
            });
            const availCell = row.cells[5];
            availCell.textContent = available ? 'Yes' : 'No';
            availCell.className = available ? 'status-active' : 'status-inactive';
        } catch (e) {
            alert('Failed to update availability: ' + (e.message || e));
        }
    }
    
    // === Products ===
    let allTags = [];
    let allSections = [];
    let selectedProductIds = [];

    async function loadProducts() {
        try {
            // Build filter query params
            const params = new URLSearchParams();
            const search = document.getElementById('product-search').value.trim();
            if (search) params.set('search', search);

            const sectionId = document.getElementById('filter-section').value;
            if (sectionId) params.set('section_id', sectionId);

            const subsectionId = document.getElementById('filter-subsection').value;
            if (subsectionId) params.set('subsection_id', subsectionId);

            const tagId = document.getElementById('filter-tag').value;
            if (tagId) params.set('tag_ids', tagId);

            const isActive = document.getElementById('filter-active').value;
            if (isActive) params.set('is_active', isActive);

            let products;
            if (params.toString()) {
                products = await fetchJSON(`${API_BASE}/products/search?db=${db}&${params.toString()}`);
            } else {
                products = await fetchJSON(`${API_BASE}/products/all?db=${db}`);
            }

            const tbody = document.querySelector('#products-table tbody');
            tbody.innerHTML = '';
            selectedProductIds = [];

            products.forEach(p => {
                const row = tbody.insertRow();
                row.dataset.productId = p.id;

                // Checkbox cell
                const checkboxCell = row.insertCell(0);
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'product-checkbox';
                cb.value = p.id;
                cb.addEventListener('change', updateBulkEditBar);
                checkboxCell.appendChild(cb);

                row.insertCell(1).textContent = p.name;
                row.insertCell(2).textContent = formatCurrency(p.price);
                row.insertCell(3).textContent = `${p.section_name} > ${p.subsection_name}`;

                // Tags cell
                const tagsCell = row.insertCell(4);
                if (p.tags && p.tags.length > 0) {
                    const tagsHtml = p.tags.map(t =>
                        `<span class="tag-badge" style="background-color: ${t.color || '#3498db'}">${t.name}</span>`
                    ).join('');
                    tagsCell.innerHTML = tagsHtml;
                } else {
                    tagsCell.textContent = 'No tags';
                    tagsCell.classList.add('muted-text');
                }

                row.insertCell(5).textContent = p.stock_count === null ? 'Unlimited' : p.stock_count;
                const statusCell = row.insertCell(6);
                statusCell.textContent = p.is_active ? 'Active' : 'Inactive';
                statusCell.classList.add(p.is_active ? 'status-active' : 'status-inactive');

                const actionsCell = row.insertCell(7);
                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'product-actions';
                actionsCell.appendChild(actionsDiv);
                
                const editBtn = document.createElement('button');
                editBtn.textContent = 'Edit';
                editBtn.className = 'btn-sm';
                editBtn.onclick = () => editProduct(p);
                actionsDiv.appendChild(editBtn);

                const delBtn = document.createElement('button');
                delBtn.textContent = 'Delete';
                delBtn.className = 'btn-sm btn-secondary';
                delBtn.onclick = () => deleteProduct(p.id, p.name);
                actionsDiv.appendChild(delBtn);
            });

            // Reset select-all checkbox
            const selectAll = document.getElementById('select-all-products');
            if (selectAll) selectAll.checked = false;
        } catch (e) {
            console.error('Products load failed:', e);
        }
    }

    async function editProduct(product) {
        // Get sections and subsections for the dropdown
        const sections = await fetchJSON(`${API_BASE}/products/?db=${db}`);

        // Build section > subsection options
        let sectionOptions = '<option value="">Select Section</option>';
        let subsectionOptions = '<option value="">Select Subsection</option>';

        sections.forEach(section => {
            sectionOptions += `<option value="${section.id}" ${section.id == product.section_id ? 'selected' : ''}>${section.name}</option>`;
        });

        // Get subsections for the product's section
        if (product.section_id) {
            const matchingSection = sections.find(s => s.id == product.section_id);
            if (matchingSection && matchingSection.subsections) {
                matchingSection.subsections.forEach(sub => {
                    subsectionOptions += `<option value="${sub.id}" ${sub.id == product.subsection_id ? 'selected' : ''}>${sub.name}</option>`;
                });
            }
        }

        const html = `
            <div class="form-group">
                <label>Name:</label>
                <input type="text" id="edit-product-name" value="${product.name}">
            </div>
            <div class="form-group">
                <label>Price (€):</label>
                <input type="number" id="edit-product-price" value="${product.price}" step="0.01">
            </div>
            <div class="form-group">
                <label>Section:</label>
                <select id="edit-product-section">${sectionOptions}</select>
            </div>
            <div class="form-group">
                <label>Subsection:</label>
                <select id="edit-product-subsection">${subsectionOptions}</select>
            </div>
            <div class="form-group">
                <label>SKU:</label>
                <input type="text" id="edit-product-sku" value="${product.sku || ''}">
            </div>
            <div class="form-group">
                <label>Stock (leave empty for unlimited):</label>
                <input type="number" id="edit-product-stock" value="${product.stock_count === null ? '' : product.stock_count}">
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" id="edit-product-active" value="1" ${product.is_active ? 'checked' : ''}>
                    Active (visible on POS)
                </label>
            </div>
        `;

        // Use onConfirm to collect form values BEFORE the dialog overlay is
        // removed from the DOM (showDialog destroys the overlay before
        // resolving, so reading values via getElementById afterwards returns null).
        let formData = null;
        const onConfirm = function() {
            formData = {
                name: document.getElementById('edit-product-name').value,
                price: parseFloat(document.getElementById('edit-product-price').value),
                sectionId: document.getElementById('edit-product-section').value,
                subsectionId: document.getElementById('edit-product-subsection').value,
                sku: document.getElementById('edit-product-sku').value || null,
                stock: document.getElementById('edit-product-stock').value ? parseInt(document.getElementById('edit-product-stock').value) : null,
                isActive: document.getElementById('edit-product-active').checked ? 1 : 0
            };
            if (!formData.name || isNaN(formData.price)) {
                alert('Name and price are required');
                return false;
            }
        };

        const confirmed = await showDialog('Edit Product', html, 'Save', onConfirm);
        if (!confirmed || !formData) return;

        try {
            const sectionId = formData.sectionId;
            const subsectionId = formData.subsectionId;
            await fetchJSON(`${API_BASE}/products/products/${product.id}?db=${db}`, {
                method: 'PUT',
                body: JSON.stringify({
                    name: formData.name,
                    price: formData.price,
                    section_id: sectionId ? parseInt(sectionId) : null,
                    subsection_id: subsectionId ? parseInt(subsectionId) : null,
                    sku: formData.sku,
                    stock: formData.stock,
                    is_active: formData.isActive
                })
            });
            loadProducts();
        } catch (e) {
            alert('Failed to update product: ' + (e.message || e));
        }
    }

    async function deleteProduct(productId, productName) {
        if (!confirm(`Delete "${productName}"? This cannot be undone if it has sales history.`)) return;
        try {
            await fetchJSON(`${API_BASE}/products/products/${productId}?db=${db}`, { method: 'DELETE' });
            loadProducts();
        } catch(e) {
            alert('Failed to delete product: ' + (e.message || e));
        }
    }

    // Helper to show a simple dialog with custom content
    function showDialog(title, htmlContent, confirmBtnText, onConfirm) {
        const overlay = document.createElement('div');
        overlay.className = 'dialog-overlay';

        const dialog = document.createElement('div');
        dialog.className = 'dialog-content';
        dialog.innerHTML = `
            <h3>${title}</h3>
            <div id="dialog-content">${htmlContent}</div>
            <div class="dialog-buttons">
                <button id="dialog-cancel" class="btn-secondary btn-sm">Cancel</button>
                <button id="dialog-confirm" class="btn-primary btn-sm">${confirmBtnText}</button>
            </div>
        `;

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        return new Promise((resolve) => {
            document.getElementById('dialog-cancel').onclick = () => {
                document.body.removeChild(overlay);
                resolve(false);
            };
            document.getElementById('dialog-confirm').onclick = () => {
                // Run optional onConfirm callback before removing overlay
                if (onConfirm) {
                    const result = onConfirm();
                    if (result === false) return; // Cancelled by handler
                }
                document.body.removeChild(overlay);
                resolve(true);
            };
            // Allow closing by clicking overlay
            overlay.onclick = (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                    resolve(false);
                }
            };
        });
    }

    // === CSV Import ===
    // Parse CSV text into 2D array of rows (handles quoted fields)
    function parseCsv(text) {
        const rows = [];
        let current = [];
        let field = '';
        let inQuotes = false;
        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            const next = text[i + 1];
            if (inQuotes) {
                if (char === '"') {
                    if (next === '"') {
                        field += '"';
                        i++;
                    } else {
                        inQuotes = false;
                    }
                } else {
                    field += char;
                }
            } else {
                if (char === '"') {
                    inQuotes = true;
                } else if (char === ',') {
                    current.push(field);
                    field = '';
                } else if (char === '\n') {
                    current.push(field);
                    rows.push(current);
                    current = [];
                    field = '';
                } else if (char === '\r') {
                    // Handle \r\n — skip \r, \n handles the line break
                    continue;
                } else {
                    field += char;
                }
            }
        }
        // Don't forget the last field/row
        current.push(field);
        if (current.length > 1 || current[0] !== '') {
            rows.push(current);
        }
        return { lines: rows };
    }

    async function importCsv() {
        const csvText = await showCsvImportDialog();
        if (csvText === null) return; // Cancelled

        // Parse CSV into JSON rows (handles quoted fields with embedded commas/newlines)
        const result = parseCsv(csvText);
        if (result.lines.length < 2) {
            alert('CSV must have a header row and at least one data row');
            return;
        }

        const headers = result.lines[0].map(h => h.trim().toLowerCase());
        // Validate required columns
        const requiredCols = ['section', 'name', 'price'];
        const missingCols = requiredCols.filter(c => !headers.includes(c));
        if (missingCols.length > 0) {
            alert('CSV is missing required columns: ' + missingCols.join(', ') +
                  '\n\nExpected columns: section, subsection, name, price, sku (optional), stock_count (optional), tags (optional)');
            return;
        }
        // Warn about unrecognized columns
        const knownCols = ['section', 'subsection', 'name', 'price', 'sku', 'stock_count', 'tags'];
        const unknownCols = headers.filter(h => !knownCols.includes(h));
        if (unknownCols.length > 0) {
            console.warn('Unknown CSV columns ignored:', unknownCols.join(', '));
        }

        const rows = [];
        const errors = [];
        for (let i = 1; i < result.lines.length; i++) {
            const values = result.lines[i].map(v => v.trim());
            if (values.length !== headers.length) {
                errors.push('Row ' + (i + 1) + ': expected ' + headers.length +
                            ' columns, got ' + values.length);
                continue;
            }
            const row = {};
            headers.forEach((h, idx) => {
                row[h] = values[idx];
            });
            // Validate price is numeric
            if (row.price && isNaN(parseFloat(row.price))) {
                errors.push('Row ' + (i + 1) + ': price "' + row.price + '" is not a valid number');
                continue;
            }
            // Validate stock_count if present
            if (row.stock_count !== undefined && row.stock_count !== '' &&
                isNaN(parseInt(row.stock_count))) {
                errors.push('Row ' + (i + 1) + ': stock_count "' + row.stock_count + '" is not a valid number');
                continue;
            }
            rows.push(row);
        }

        if (errors.length > 0) {
            if (confirm('Found ' + errors.length + ' validation error(s):\n\n' +
                        errors.slice(0, 10).join('\n') +
                        (errors.length > 10 ? '\n... and ' + (errors.length - 10) + ' more' : '') +
                        '\n\nImport the valid rows anyway?')) {
                // Continue with valid rows
            } else {
                return;
            }
        }

        if (rows.length === 0) {
            alert('No valid data rows found after validation');
            return;
        }

        try {
            const result = await fetchJSON(`${API_BASE}/products/import-csv?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ rows: rows })
            });
            alert(result.message);
            loadProducts();
        } catch(e) {
            alert('Import failed: ' + (e.message || e));
        }
    }

    function showCsvImportDialog() {
        const html = `
            <p class="muted-text">
                Select a CSV file or paste CSV content below.
                Expected columns: section, subsection, name, price, sku (optional), stock_count (optional), tags (optional)
            </p>
            <input type="file" id="csv-file-input" accept=".csv,.txt" class="form-control" style="margin-bottom: 10px;">
            <p class="muted-text" style="font-size: 11px;">-- or paste below --</p>
            <textarea id="csv-input" class="form-control textarea-import"></textarea>
        `;
        // Read file/textarea value in onConfirm callback (runs before overlay is removed)
        let csvText = null;
        const onConfirm = async function() {
            // Check if a file was selected
            const fileInput = document.getElementById('csv-file-input');
            if (fileInput && fileInput.files && fileInput.files.length > 0) {
                csvText = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = e => resolve(e.target.result);
                    reader.onerror = reject;
                    reader.readAsText(fileInput.files[0]);
                });
            } else {
                // Fall back to pasted text
                csvText = document.getElementById('csv-input').value.trim();
            }
            if (!csvText) {
                alert('Please select a CSV file or paste CSV content');
                return false; // Don't close the dialog
            }
        };
        return new Promise((resolve) => {
            showDialog('CSV Import', html, 'Import', onConfirm).then(confirmed => {
                if (confirmed && csvText !== null) {
                    resolve(csvText);
                } else {
                    resolve(null);
                }
            });
        });
    }

    // === CSV Export ===
    async function exportCsv() {
        try {
            const data = await fetchJSON(`${API_BASE}/products/export?db=${db}`);
            const csv = data.csv;
            const filename = data.filename;

            // Build a data URL for the CSV
            const dataUrl = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);

            // Try the anchor download approach (works in browsers)
            // In pywebview GTK, this may trigger the browser's download/save dialog
            const a = document.createElement('a');
            a.href = dataUrl;
            a.download = filename;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            // Clean up
            setTimeout(() => {
                URL.revokeObjectURL(dataUrl);
            }, 5000);
        } catch(e) {
            alert('Export failed: ' + (e.message || e));
        }
    }

    // === Parties ===
    let selectedParty = null;

    async function loadParties() {
        try {
            const parties = await fetchJSON(`${API_BASE}/parties/?db=${db}`);
            const tbody = document.querySelector('#parties-table tbody');
            tbody.innerHTML = '';
            selectedParty = null;

            parties.forEach(p => {
                const row = tbody.insertRow();
                row.dataset.partyName = p.name;

                const nameCell = row.insertCell(0);
                nameCell.textContent = p.name;

                const dateCell = row.insertCell(1);
                dateCell.textContent = p.modified || '';

                const actionsCell = row.insertCell(2);
                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'product-actions';

                // Duplicate button
                const dupBtn = document.createElement('button');
                dupBtn.textContent = 'Duplicate';
                dupBtn.className = 'btn-sm';
                dupBtn.onclick = () => duplicateParty(p.name);
                actionsDiv.appendChild(dupBtn);

                // Delete button
                const delBtn = document.createElement('button');
                delBtn.textContent = 'Delete';
                delBtn.className = 'btn-sm btn-secondary';
                delBtn.onclick = () => deleteParty(p.name);
                actionsDiv.appendChild(delBtn);

                // Row click to select
                row.addEventListener('click', () => {
                    selectedParty = p.name;
                    // Highlight selected row
                    document.querySelectorAll('#parties-table tbody tr').forEach(r => r.classList.remove('selected-party'));
                    row.classList.add('selected-party');
                });

                actionsCell.appendChild(actionsDiv);
            });

            // Wire up section-level buttons
            const sectionDupBtn = document.getElementById('duplicate-party-btn');
            if (sectionDupBtn) {
                sectionDupBtn.onclick = () => {
                    if (!selectedParty) {
                        alert('Please select a party to duplicate first.');
                        return;
                    }
                    duplicateParty(selectedParty);
                };
            }

            const exportBtn = document.getElementById('export-recap-btn-party');
            if (exportBtn) {
                exportBtn.onclick = () => exportPartyRecapCsv(selectedParty);
            }
        } catch (e) {
            console.error('Parties load failed:', e);
        }
    }

    async function duplicateParty(partyName) {
        // Fetch the original party's settings to pre-fill dates
        let origStartDate = '';
        let origEndDate = '';
        try {
            const settings = await fetchJSON(`${API_BASE}/parties/${encodeURIComponent(partyName)}/settings?db=${db}`);
            origStartDate = settings.start_date || '';
            origEndDate = settings.end_date || '';
        } catch(e) {
            // If we can't fetch settings, just use empty dates
            console.warn('Could not fetch party settings for dates:', e);
        }

        // Guess a default new name: append " (copy)" if not already a copy
        let defaultName = partyName;
        if (!defaultName.match(/\(copy\)/i)) {
            defaultName = partyName + ' (copy)';
        }

        const html = `
            <div class="form-group">
                <label>New Party Name:</label>
                <input type="text" id="dup-party-name" class="form-control" value="${defaultName}">
            </div>
            <div class="form-group">
                <label>Start Date:</label>
                <input type="date" id="dup-party-start-date" class="form-control" value="${origStartDate}">
            </div>
            <div class="form-group">
                <label>End Date (optional):</label>
                <input type="date" id="dup-party-end-date" class="form-control" value="${origEndDate}">
            </div>
        `;

        // Read form values in onConfirm callback (runs before overlay is removed)
        let formData = null;

        const onConfirm = function() {
            formData = {
                name: document.getElementById('dup-party-name').value.trim(),
                startDate: document.getElementById('dup-party-start-date').value,
                endDate: document.getElementById('dup-party-end-date').value
            };
            if (!formData.name) {
                alert('Party name is required');
                return false;
            }
        };

        const confirmed = await showDialog('Duplicate Party', html, 'Duplicate', onConfirm);
        if (!confirmed || !formData) return;

        try {
            await fetchJSON(`${API_BASE}/parties/${encodeURIComponent(partyName)}/duplicate?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    name: formData.name,
                    start_date: formData.startDate || null,
                    end_date: formData.endDate || null
                })
            });
            loadParties();
        } catch (e) {
            alert('Failed to duplicate party: ' + (e.message || e));
        }
    }

    async function exportPartyRecapCsv(partyName) {
        if (!partyName) {
            alert('Please select a party to export first.');
            return;
        }
        try {
            const response = await fetch(`${API_BASE}/parties/${encodeURIComponent(partyName)}/recap?db=${db}`, {
                method: 'GET',
            });
            if (!response.ok) {
                throw new Error('Export failed');
            }
            const csvText = await response.text();
            const blob = new Blob([csvText], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${partyName}-recap.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('Failed to export recap: ' + (e.message || e));
        }
    }
    
    async function deleteParty(partyName) {
        if (!confirm(`Delete party "${partyName}"? This cannot be undone.`)) return;
        try {
            await fetch(`${API_BASE}/parties/${partyName}?db=${db}`, { method: 'DELETE' });
            loadParties();
        } catch (e) {
            alert('Failed to delete party');
        }
    }
    
    // === Operators ===
    async function loadOperators() {
        try {
            const operators = await fetchJSON(`${API_BASE}/auth/operators?db=${db}`);
            const tbody = document.querySelector('#operators-table tbody');
            tbody.innerHTML = '';
            
            operators.forEach(op => {
                const row = tbody.insertRow();
                row.insertCell(0).textContent = op.name;
                row.insertCell(1).textContent = op.role === 'admin' ? 'Admin' : 'Operator';
                row.insertCell(2).textContent = '****';
                const actionsCell = row.insertCell(3);
                const resetBtn = document.createElement('button');
                resetBtn.textContent = 'Reset PIN';
                resetBtn.className = 'btn-sm btn-secondary';
                resetBtn.onclick = () => resetOperatorPin(op.id);
                actionsCell.appendChild(resetBtn);
            });
        } catch (e) {
            console.error('Operators load failed:', e);
        }
    }
    
    async function resetOperatorPin(operatorId) {
        const newPin = prompt('Enter new 4-digit PIN:');
        if (!newPin || !/^\d{4}$/.test(newPin)) {
            alert('PIN must be 4 digits');
            return;
        }
        
        try {
            await fetchJSON(`${API_BASE}/auth/operators/${operatorId}/reset-pin?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ pin: newPin })
            });
            loadOperators();
        } catch (e) {
            alert('Failed to reset PIN');
        }
    }
    
    // === Settings ===
    async function loadSettings() {
        try {
            const settings = await fetchJSON(`${API_BASE}/settings/?db=${db}`);
            const form = document.getElementById('settings-form');
            // Populate form fields
            for (const [key, value] of Object.entries(settings)) {
                const input = form.querySelector(`[name="${key}"]`);
                if (input) {
                    if (input.type === 'checkbox') {
                        // Checkboxes: value is '1' or '0'
                        input.checked = value == '1' || value === true;
                    } else if (input.type === 'select-one') {
                        // Find and select the option with matching value
                        const option = Array.from(input.options).find(o => o.value === value);
                        if (option) option.selected = true;
                    } else {
                        input.value = value;
                    }
                }
            }
        } catch (e) {
            console.error('Settings load failed:', e);
        }
    }
    
    // === Tags Management ===
    async function loadTags() {
        try {
            // Load all tags
            const tags = await fetchJSON(`${API_BASE}/products/tags?db=${db}`);
            const tagList = document.getElementById('tag-list');
            tagList.innerHTML = '';

            tags.forEach(tag => {
                const div = document.createElement('div');
                div.className = 'tag-item';
                div.dataset.tagId = tag.id;
                div.innerHTML = `
                    <div class="tag-color-preview" style="background-color: ${tag.color || '#3498db'};"></div>
                    <span class="tag-name">${tag.name}</span>
                    <span class="tag-bg-info">
                        bg: ${tag.bg_color || 'none'} | text: ${tag.text_color || 'default'}
                    </span>
                    <div class="tag-actions">
                        <button class="btn-sm" onclick="editTag(${tag.id})">Edit</button>
                        <button class="btn-sm btn-secondary" onclick="deleteTag(${tag.id})">Delete</button>
                    </div>
                `;
                tagList.appendChild(div);
            });

            // Load products for assignment dropdown
            const sections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
            const productSelect = document.getElementById('product-select');
            productSelect.innerHTML = '<option value="">-- Select a product --</option>';

            // Flatten all products from all sections/subsections
            for (const section of sections) {
                for (const sub of (section.subsections || [])) {
                    const products = await fetch(`${API_BASE}/products/${sub.id}/products?db=${db}`)
                        .then(r => r.json());
                    products.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p.id;
                        opt.textContent = `${p.name} (${section.name} > ${sub.name})`;
                        productSelect.appendChild(opt);
                    });
                }
            }

            // Load tag select options
            const tagSelect = document.getElementById('tag-select');
            tagSelect.innerHTML = '<option value="">-- Select a tag --</option>';
            tags.forEach(tag => {
                const opt = document.createElement('option');
                opt.value = tag.id;
                opt.textContent = tag.name;
                tagSelect.appendChild(opt);
            });

            // Setup product-select change handler
            productSelect.onchange = function() {
                const productId = this.value;
                if (productId) {
                    loadProductTags(productId);
                } else {
                    document.getElementById('product-tags-display').innerHTML = '';
                }
            };
        } catch (e) {
            console.error('Tags load failed:', e);
        }
    }

    async function loadProductTags(productId) {
        try {
            const productTags = await fetchJSON(`${API_BASE}/products/${productId}/tags?db=${db}`);
            const display = document.getElementById('product-tags-display');
            display.innerHTML = '<h5>Current Tags:</h5>';
            if (productTags.length === 0) {
                display.innerHTML += '<p class="muted-text">No tags assigned</p>';
            } else {
                productTags.forEach(t => {
                    const span = document.createElement('span');
                    span.className = 'tag-badge';
                    span.style.backgroundColor = t.color || '#3498db';
                    span.textContent = t.name;
                    const removeBtn = document.createElement('button');
                    removeBtn.textContent = '×';
                    removeBtn.style.cssText = 'margin-left:5px; padding:0 4px; font-size:12px;';
                    removeBtn.onclick = () => removeProductTag(productId, t.id);
                    span.appendChild(removeBtn);
                    display.appendChild(span);
                });
            }
        } catch (e) {
            console.error('Failed to load product tags:', e);
        }
    }

    window.editTag = async function(tagId) {
        const tag = await fetchJSON(`${API_BASE}/products/tags/${tagId}?db=${db}`);
        if (!tag) return;

        const newName = prompt('Tag name:', tag.name);
        if (newName === null) return;
        const newColor = prompt('Tag color (hex, e.g. #3498db):', tag.color || '#3498db');
        const newBgColor = prompt('Background color for products (hex, leave empty for none):', tag.bg_color || '');
        const newTextColor = prompt('Text color for products (hex, leave empty for default):', tag.text_color || '');

        if (newName === null || newColor === null) return;

        await fetchJSON(`${API_BASE}/products/tags/${tagId}?db=${db}`, {
            method: 'PUT',
            body: JSON.stringify({
                name: newName.trim() || tag.name,
                color: newColor,
                bg_color: newBgColor || null,
                text_color: newTextColor || null
            })
        });
        loadTags();
    };

    window.deleteTag = async function(tagId) {
        if (!confirm('Delete this tag? It will be removed from all products.')) return;
        await fetchJSON(`${API_BASE}/products/tags/${tagId}?db=${db}`, { method: 'DELETE' });
        loadTags();
    };

    window.removeProductTag = async function(productId, tagId) {
        await fetchJSON(`${API_BASE}/products/${productId}/tags/${tagId}?db=${db}`, { method: 'DELETE' });
        loadProductTags(productId);
    };

    // === Event Handlers ===
    document.getElementById('add-product-btn').addEventListener('click', function() {
        addProductDialog();
    });

    async function addProductDialog() {
        // Fetch existing sections for the dropdown
        const sections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
        let sectionOptions = '<option value="">Select Section</option>';
        sectionOptions += '<option value="__new_section__">-- Create new section --</option>';
        sections.forEach(section => {
            sectionOptions += `<option value="${section.id}">${section.name}</option>`;
        });
        
        let subsectionOptions = '<option value="">Select Subsection</option>';
        subsectionOptions += '<option value="__new_subsection__">-- Create new subsection --</option>';
        
        const html = `
            <div class="form-group">
                <label>Name:</label>
                <input type="text" id="new-product-name" class="form-control">
            </div>
            <div class="form-group">
                <label>Price (€):</label>
                <input type="number" id="new-product-price" step="0.01" class="form-control">
            </div>
            <div class="form-group">
                <label>Section:</label>
                <select id="new-product-section" class="form-control">${sectionOptions}</select>
            </div>
            <div id="new-section-row" class="form-group hidden">
                <label>New Section Name:</label>
                <input type="text" id="new-section-name" class="form-control">
            </div>
            <div class="form-group">
                <label>Subsection:</label>
                <select id="new-product-subsection" class="form-control">${subsectionOptions}</select>
            </div>
            <div id="new-subsection-row" class="form-group hidden">
                <label>New Subsection Name:</label>
                <input type="text" id="new-subsection-name" class="form-control">
            </div>
            <div class="form-group">
                <label>SKU:</label>
                <input type="text" id="new-product-sku" class="form-control">
            </div>
            <div class="form-group">
                <label>Stock (leave empty for unlimited):</label>
                <input type="number" id="new-product-stock" class="form-control">
            </div>
        `;

        // Read form values in onConfirm callback (runs before overlay is removed)
        let formData = null;
        
        const onConfirm = function() {
            const sectionSelect = document.getElementById('new-product-section');
            const subsectionSelect = document.getElementById('new-product-subsection');
            
            formData = {
                sectionId: sectionSelect.value,
                subsectionId: subsectionSelect.value,
                newSectionName: document.getElementById('new-section-name').value.trim(),
                newSubsectionName: document.getElementById('new-subsection-name').value.trim(),
                name: document.getElementById('new-product-name').value.trim(),
                price: parseFloat(document.getElementById('new-product-price').value),
                sku: document.getElementById('new-product-sku').value || null,
                stock: document.getElementById('new-product-stock').value ? parseInt(document.getElementById('new-product-stock').value) : null
            };
            
            if (!formData.name || isNaN(formData.price)) {
                alert('Name and price are required');
                return false; // Don't close the dialog
            }
        };
        
        // Create dialog and get the promise
        const dialogPromise = showDialog('Add New Product', html, 'Create', onConfirm);
        
        // Attach handlers to dropdown elements (they exist in DOM now)
        const sectionSelectEl = document.getElementById('new-product-section');
        if (sectionSelectEl) {
            sectionSelectEl.onchange = async function() {
                const newSectionRow = document.getElementById('new-section-row');
                const newSectionInput = document.getElementById('new-section-name');
                if (this.value === '__new_section__') {
                    newSectionRow.classList.remove('hidden');
                    newSectionInput.required = true;
                } else {
                    newSectionRow.classList.add('hidden');
                    newSectionInput.required = false;
                    await updateSubsectionDropdown(this.value, document.getElementById('new-product-subsection').value);
                }
            };
        }
        
        const subsectionSelectEl = document.getElementById('new-product-subsection');
        if (subsectionSelectEl) {
            subsectionSelectEl.onchange = function() {
                const newSubsectionRow = document.getElementById('new-subsection-row');
                const newSubsectionInput = document.getElementById('new-subsection-name');
                if (this.value === '__new_subsection__') {
                    newSubsectionRow.classList.remove('hidden');
                    newSubsectionInput.required = true;
                } else {
                    newSubsectionRow.classList.add('hidden');
                    newSubsectionInput.required = false;
                }
            };
        }
        
        // Wait for user to confirm/cancel
        const confirmed = await dialogPromise;
        
        if (!confirmed || !formData) return;
        
        try {
            let sectionId = formData.sectionId;
            let subsectionId = formData.subsectionId;

            // Create new section if requested
            if (formData.sectionId === '__new_section__') {
                if (!formData.newSectionName) {
                    alert('New section name is required');
                    return;
                }
                await fetchJSON(`${API_BASE}/products/sections?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({ name: formData.newSectionName })
                });
                const updatedSections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
                const newSection = updatedSections.find(s => s.name === formData.newSectionName);
                if (!newSection) {
                    alert('Failed to create section');
                    return;
                }
                sectionId = newSection.id;
            }

            // Create new subsection if requested
            if (formData.subsectionId === '__new_subsection__') {
                if (!formData.newSubsectionName) {
                    alert('New subsection name is required');
                    return;
                }
                const sid = parseInt(sectionId);
                if (!sid) {
                    alert('Section must be selected before creating a subsection');
                    return;
                }
                await fetchJSON(`${API_BASE}/products/subsections?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({ section_id: sid, name: formData.newSubsectionName })
                });
                const updatedSections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
                const matchingSection = updatedSections.find(s => s.id == sid);
                const newSub = matchingSection ? matchingSection.subsections.find(s => s.name === formData.newSubsectionName) : null;
                if (!newSub) {
                    alert('Failed to create subsection');
                    return;
                }
                subsectionId = newSub.id;
            }

            if (!sectionId || !subsectionId || formData.sectionId === '' || formData.subsectionId === '') {
                alert('Section and subsection are required');
                return;
            }

            await fetchJSON(`${API_BASE}/products/products?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    name: formData.name,
                    price: formData.price,
                    section_id: parseInt(sectionId),
                    subsection_id: parseInt(subsectionId),
                    sku: formData.sku,
                    stock: formData.stock
                })
            });
            loadProducts();
        } catch(e) {
            alert('Failed to create product: ' + (e.message || e));
        }
    }


    // Helper: update subsection dropdown based on selected section
    async function updateSubsectionDropdown(sectionId, currentSubId) {
        const subSelect = document.getElementById('new-product-subsection');
        if (!subSelect) return;

        if (!sectionId) {
            subSelect.innerHTML = '<option value="">Select Subsection</option>';
            return;
        }

        const sections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
        const section = sections.find(s => s.id == sectionId);
        let options = '<option value="">Select Subsection</option>';
        options += '<option value="__new_subsection__">-- Create new subsection --</option>';
        if (section && section.subsections) {
            section.subsections.forEach(sub => {
                const selected = sub.id == currentSubId ? ' selected' : '';
                options += `<option value="${sub.id}"${selected}>${sub.name}</option>`;
            });
        }
        subSelect.innerHTML = options;
    }

    document.getElementById('create-party-btn').addEventListener('click', async function() {
        const templates = await fetchJSON(`${API_BASE}/parties/templates?db=${db}`);
        
        // Build template options — always include the "no template" option
        let templateOptions = '<option value="__empty__">(No template — start empty)</option>';
        if (templates && templates.length > 0) {
            templates.forEach(t => {
                templateOptions += `<option value="${t.id}">${t.name}</option>`;
            });
        }
        
        const html = `
            <div class="form-group">
                <label>Party Name:</label>
                <input type="text" id="new-party-name" class="form-control">
            </div>
            <div class="form-group">
                <label>Template (optional):</label>
                <select id="new-party-template" class="form-control">${templateOptions}</select>
            </div>
            <div class="form-group">
                <label>Start Date:</label>
                <input type="date" id="new-party-start-date" class="form-control">
            </div>
            <div class="form-group">
                <label>End Date (optional):</label>
                <input type="date" id="new-party-end-date" class="form-control">
            </div>
        `;

        // Read form values in onConfirm callback (runs before overlay is removed)
        let formData = null;

        const onConfirm = function() {
            formData = {
                name: document.getElementById('new-party-name').value.trim(),
                templateValue: document.getElementById('new-party-template').value,
                startDate: document.getElementById('new-party-start-date').value,
                endDate: document.getElementById('new-party-end-date').value
            };

            if (!formData.name) {
                alert('Party name is required');
                return false; // Don't close the dialog
            }
        };

        const confirmed = await showDialog('Create New Party', html, 'Create', onConfirm);
        if (!confirmed || !formData) return;

        try {
            if (formData.templateValue === '__empty__') {
                await fetchJSON(`${API_BASE}/parties/create-empty?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({
                        name: formData.name,
                        start_date: formData.startDate,
                        end_date: formData.endDate || null
                    })
                });
            } else {
                await fetchJSON(`${API_BASE}/parties/?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({
                        name: formData.name,
                        template_id: parseInt(formData.templateValue),
                        start_date: formData.startDate,
                        end_date: formData.endDate || null
                    })
                });
            }
            loadParties();
        } catch(e) {
            alert('Failed to create party: ' + (e.message || e));
        }
    });

    // Wire up CSV import/export buttons
    document.getElementById('import-csv-btn').addEventListener('click', importCsv);
    document.getElementById('export-csv-btn').addEventListener('click', exportCsv);

    // Wire up CSV template download link
    const templateLink = document.getElementById('download-csv-template-btn');
    if (templateLink) {
        const templateCsv = 'section,subsection,name,price,sku,stock_count,tags\n"Drinks","Soft Drinks","Coca Cola",1.50,CC123,100,"Popular,Beverage"\n"Food","Snacks","Potato Chips",2.00,PC456,50,"Popular"\n';
        templateLink.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(templateCsv);
    }
    
    document.getElementById('add-operator-btn').addEventListener('click', () => {
        const name = prompt('Operator name:');
        const pin = prompt('4-digit PIN:');
        if (name && /^\d{4}$/.test(pin)) {
            fetchJSON(`${API_BASE}/auth/operators?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ name, pin, role: 'operator' })
            }).then(() => loadOperators());
        } else {
            alert('Invalid name or PIN');
        }
    });
    
    document.getElementById('settings-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(this);
        const settings = {};
        
        // Handle regular inputs and selects
        for (const [key, value] of formData.entries()) {
            settings[key] = value;
        }
        
        // Handle checkboxes — set to '0' if unchecked
        const checkboxes = this.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(cb => {
            if (!cb.checked) {
                settings[cb.name] = '0';
            } else if (cb.value !== 'on') {
                settings[cb.name] = cb.value;
            }
        });
        
        fetchJSON(`${API_BASE}/settings/?db=${db}`, {
            method: 'POST',
            body: JSON.stringify(settings)
        }).then(() => {
            alert('Settings saved');
            // Go back to dashboard after saving
            sections.forEach(s => s.classList.remove('active'));
            document.getElementById('admin-dashboard').classList.add('active');
            navLinks.forEach(l => l.classList.remove('active'));
        }).catch(err => {
            alert('Failed to save settings: ' + err);
        });
    });

    // === Tag Button Handlers ===
    document.getElementById('create-tag-btn').addEventListener('click', async function() {
        const name = document.getElementById('new-tag-name').value.trim();
        const color = document.getElementById('new-tag-color').value;
        const bgColor = document.getElementById('new-tag-bg-color').value;
        const textColor = document.getElementById('new-tag-text-color').value;

        if (!name) {
            alert('Tag name is required');
            return;
        }

        try {
            await fetchJSON(`${API_BASE}/products/tags?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    name: name,
                    color: color,
                    bg_color: bgColor === '#ffffff' ? null : bgColor,
                    text_color: textColor === '#333333' ? null : textColor
                })
            });
            // Clear inputs
            document.getElementById('new-tag-name').value = '';
            document.getElementById('new-tag-color').value = '#3498db';
            document.getElementById('new-tag-bg-color').value = '#ffffff';
            document.getElementById('new-tag-text-color').value = '#333333';
            // Refresh tag list
            loadTags();
        } catch(e) {
            alert('Failed to create tag: ' + (e.message || e));
        }
    });

    document.getElementById('assign-tag-btn').addEventListener('click', async function() {
        const productId = document.getElementById('product-select').value;
        const tagId = document.getElementById('tag-select').value;

        if (!productId || !tagId) {
            alert('Select a product and a tag');
            return;
        }

        try {
            await fetchJSON(`${API_BASE}/products/${productId}/tags?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ tag_id: parseInt(tagId) })
            });
            loadProductTags(productId);
        } catch(e) {
            alert('Failed to assign tag: ' + e);
        }
    });

    // === Filter Event Listeners ===
    // Populate section filter dropdown
    async function populateFilterDropdowns() {
        try {
            allSections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
            const sectionFilter = document.getElementById('filter-section');
            sectionFilter.innerHTML = '<option value="">All Sections</option>';
            allSections.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = s.name;
                sectionFilter.appendChild(opt);
            });

            // Populate tag filter dropdown
            allTags = await fetchJSON(`${API_BASE}/products/tags?db=${db}`);
            const tagFilter = document.getElementById('filter-tag');
            tagFilter.innerHTML = '<option value="">All Tags</option>';
            allTags.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.name;
                tagFilter.appendChild(opt);
            });
        } catch (e) {
            console.error('Failed to populate filter dropdowns:', e);
        }
    }

    // Section filter change → populate subsections
    document.getElementById('filter-section').addEventListener('change', function() {
        const subsectionFilter = document.getElementById('filter-subsection');
        const sectionId = this.value;
        subsectionFilter.innerHTML = '<option value="">All Subsections</option>';
        if (sectionId) {
            const section = allSections.find(s => s.id == sectionId);
            if (section && section.subsections) {
                section.subsections.forEach(sub => {
                    const opt = document.createElement('option');
                    opt.value = sub.id;
                    opt.textContent = sub.name;
                    subsectionFilter.appendChild(opt);
                });
            }
        }
        loadProducts();
    });

    // Subsection filter change → reload
    document.getElementById('filter-subsection').addEventListener('change', loadProducts);

    // Tag filter change → reload
    document.getElementById('filter-tag').addEventListener('change', loadProducts);

    // Active filter change → reload
    document.getElementById('filter-active').addEventListener('change', loadProducts);

    // Search input with debounce
    let searchDebounceTimer;
    document.getElementById('product-search').addEventListener('input', function() {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => loadProducts(), 300);
    });

    // Clear filters button
    document.getElementById('clear-filters-btn').addEventListener('click', function() {
        document.getElementById('product-search').value = '';
        document.getElementById('filter-section').value = '';
        document.getElementById('filter-subsection').innerHTML = '<option value="">All Subsections</option>';
        document.getElementById('filter-tag').value = '';
        document.getElementById('filter-active').value = '';
        loadProducts();
    });

    // === Select All Checkbox ===
    document.getElementById('select-all-products').addEventListener('change', function() {
        const checkboxes = document.querySelectorAll('.product-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = this.checked;
            if (this.checked) {
                if (!selectedProductIds.includes(parseInt(cb.value))) {
                    selectedProductIds.push(parseInt(cb.value));
                }
            } else {
                selectedProductIds = selectedProductIds.filter(id => id !== parseInt(cb.value));
            }
        });
        updateBulkEditBar();
    });

    // === Bulk Edit Bar ===
    function updateBulkEditBar() {
        const checkboxes = document.querySelectorAll('.product-checkbox:checked');
        selectedProductIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
        const count = selectedProductIds.length;
        document.getElementById('bulk-selected-count').textContent = `${count} selected`;
        document.getElementById('bulk-edit-bar').style.display = count > 0 ? 'block' : 'none';
    }

    // Clear selection button
    document.getElementById('bulk-clear-selection').addEventListener('click', function() {
        selectedProductIds = [];
        document.querySelectorAll('.product-checkbox').forEach(cb => cb.checked = false);
        const selectAll = document.getElementById('select-all-products');
        if (selectAll) selectAll.checked = false;
        document.getElementById('bulk-edit-bar').style.display = 'none';
    });

    // Bulk Edit Attributes button
    document.getElementById('bulk-edit-btn').addEventListener('click', async function() {
        if (selectedProductIds.length === 0) {
            alert('No products selected');
            return;
        }
        const updates = await showBulkEditDialog();
        if (!updates || Object.keys(updates).length === 0) return;

        try {
            const result = await fetchJSON(`${API_BASE}/products/products/bulk?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    product_ids: selectedProductIds,
                    updates: updates
                })
            });
            alert(result.message);
            loadProducts();
        } catch (e) {
            alert('Bulk update failed: ' + (e.message || e));
        }
    });

    // Bulk Mark Active/Inactive
    document.getElementById('bulk-active-btn').addEventListener('click', async function() {
        if (selectedProductIds.length === 0) return;
        if (!confirm(`Mark ${selectedProductIds.length} product(s) as active?`)) return;
        try {
            await fetchJSON(`${API_BASE}/products/products/bulk?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    product_ids: selectedProductIds,
                    updates: { is_active: true }
                })
            });
            loadProducts();
        } catch (e) {
            alert('Failed to update: ' + (e.message || e));
        }
    });

    document.getElementById('bulk-inactive-btn').addEventListener('click', async function() {
        if (selectedProductIds.length === 0) return;
        if (!confirm(`Mark ${selectedProductIds.length} product(s) as inactive?`)) return;
        try {
            await fetchJSON(`${API_BASE}/products/products/bulk?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    product_ids: selectedProductIds,
                    updates: { is_active: false }
                })
            });
            loadProducts();
        } catch (e) {
            alert('Failed to update: ' + (e.message || e));
        }
    });

    // Bulk Delete Products
    document.getElementById('bulk-delete-btn').addEventListener('click', async function() {
        if (selectedProductIds.length === 0) return;
        if (!confirm(`Delete ${selectedProductIds.length} product(s)? This cannot be undone.`)) return;
        try {
            // Delete each product individually (API supports single-product DELETE)
            for (const productId of selectedProductIds) {
                await fetchJSON(`${API_BASE}/products/products/${productId}?db=${db}`, {
                    method: 'DELETE'
                });
            }
            alert(`Deleted ${selectedProductIds.length} product(s)`);
            selectedProductIds = [];
            document.getElementById('bulk-edit-bar').style.display = 'none';
            loadProducts();
        } catch(e) {
            alert('Failed to delete products: ' + (e.message || e));
        }
    });

    // === Bulk Edit Dialog ===
    async function showBulkEditDialog() {
        // Fetch sections for dropdown
        await populateFilterDropdowns();

        let sectionOptions = '<option value="">-- No Change --</option>';
        allSections.forEach(section => {
            sectionOptions += `<option value="${section.id}">${section.name}</option>`;
        });

        let subsectionOptions = '<option value="">-- No Change --</option>';

        const html = `
            <div class="form-group">
                <label>Name:</label>
                <input type="text" id="bulk-name" placeholder="Leave blank to keep unchanged" class="form-control">
            </div>
            <div class="form-group">
                <label>Price (€):</label>
                <input type="number" id="bulk-price" step="0.01" placeholder="Leave blank to keep unchanged" class="form-control">
            </div>
            <div class="form-group">
                <label>SKU:</label>
                <input type="text" id="bulk-sku" placeholder="Leave blank to keep unchanged" class="form-control">
            </div>
            <div class="form-group">
                <label>Section:</label>
                <select id="bulk-section" class="form-control">${sectionOptions}</select>
            </div>
            <div class="form-group">
                <label>Subsection:</label>
                <select id="bulk-subsection" class="form-control">${subsectionOptions}</select>
            </div>
            <div class="form-group">
                <label>Stock (leave blank for unlimited):</label>
                <input type="number" id="bulk-stock" placeholder="Leave blank to keep unchanged" class="form-control">
            </div>
            <div class="form-group">
                <label>Tags:</label>
                <select id="bulk-tags" multiple class="form-control form-control-multiselect">
                    ${allTags.map(t => `<option value="${t.id}">${t.name}</option>`).join('')}
                </select>
                <p class="form-help-text">Hold Ctrl/Cmd to select multiple. Leave unselected to keep existing tags.</p>
            </div>
        `;

        // Read form values in onConfirm callback (runs before overlay is removed)
        let updates = null;

        const onConfirm = function() {
            updates = {};

            const name = document.getElementById('bulk-name').value.trim();
            if (name) updates.name = name;

            const price = document.getElementById('bulk-price').value;
            if (price) updates.price = parseFloat(price);

            const sku = document.getElementById('bulk-sku').value.trim();
            if (sku) updates.sku = sku;

            const sectionId = document.getElementById('bulk-section').value;
            if (sectionId) {
                updates.section_id = parseInt(sectionId);
                const subsectionId = document.getElementById('bulk-subsection').value;
                if (subsectionId) updates.subsection_id = parseInt(subsectionId);
            }

            const stock = document.getElementById('bulk-stock').value;
            if (stock !== '') {
                updates.stock = parseInt(stock);
            }

            const selectedTagOpts = document.getElementById('bulk-tags').selectedOptions;
            if (selectedTagOpts.length > 0) {
                updates.tags = Array.from(selectedTagOpts).map(opt => parseInt(opt.value));
            }
        };

        const confirmed = await showDialog('Bulk Edit Attributes', html, 'Apply Changes', onConfirm);
        if (!confirmed || !updates) return null;

        return updates;
    }

    // === Assign Tags to Selected Products ===
    document.getElementById('bulk-assign-tags-btn').addEventListener('click', async function() {
        if (selectedProductIds.length === 0) {
            alert('No products selected');
            return;
        }

        await populateFilterDropdowns();
        const tagOptions = allTags.map(t =>
            `<option value="${t.id}">${t.name}</option>`
        ).join('');

        const html = `
            <p>Select tags to assign to ${selectedProductIds.length} product(s):</p>
            <select id="bulk-assign-tags-select" multiple class="form-control form-control-multiselect">
                ${tagOptions}
            </select>
        `;

        let selectedTagIds = null;

        const onConfirm = function() {
            const selectedTagOpts = document.getElementById('bulk-assign-tags-select').selectedOptions;
            selectedTagIds = Array.from(selectedTagOpts).map(opt => parseInt(opt.value));
            if (selectedTagIds.length === 0) {
                alert('Please select at least one tag');
                return false; // Don't close the dialog
            }
        };

        const confirmed = await showDialog('Assign Tags', html, 'Assign', onConfirm);
        if (!confirmed || !selectedTagIds || selectedTagIds.length === 0) return;

        try {
            await fetchJSON(`${API_BASE}/products/products/bulk?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({
                    product_ids: selectedProductIds,
                    updates: { tags: selectedTagIds }
                })
            });
            alert(`Assigned ${selectedTagIds.length} tag(s) to ${selectedProductIds.length} product(s)`);
            loadProducts();
        } catch (e) {
            alert('Failed to assign tags: ' + (e.message || e));
        }
    });

    // === Sections Reorder ===
    async function loadSections() {
        try {
            const sections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
            const listEl = document.getElementById('sections-list');
            listEl.innerHTML = '';
            sections.forEach((section, idx) => {
                const div = document.createElement('div');
                div.className = 'section-item';
                div.draggable = true;
                div.dataset.sectionId = section.id;
                div.innerHTML = `<span class="drag-handle" style="margin-right:10px;cursor:move;">≡</span>${section.name} (${section.subsections ? section.subsections.length : 0} ${t('subsections')}) <span class="section-arrows" style="margin-left:auto;display:inline-flex;flex-direction:column;"><button type="button" class="section-move-up" title="Move up" style="border:none;background:none;cursor:pointer;font-size:14px;">▲</button><button type="button" class="section-move-down" title="Move down" style="border:none;background:none;cursor:pointer;font-size:14px;">▼</button></span>`;
                listEl.appendChild(div);
            });
            setupDragAndDrop();
            setupSectionArrows();
        } catch (e) {
            console.error('Sections load failed:', e);
        }
    }

    function setupDragAndDrop() {
        var listEl = document.getElementById('sections-list');
        if (!listEl) return;

        var dragSrcEl = null;

        listEl.addEventListener('dragstart', function(e) {
            dragSrcEl = e.target.closest('.section-item');
            if (dragSrcEl) {
                dragSrcEl.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            }
        });

        listEl.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            var afterElement = getDragAfterElement(listEl, e.clientY);
            var draggable = listEl.querySelector('.dragging');
            if (afterElement == null) {
                listEl.appendChild(draggable);
            } else {
                listEl.insertBefore(draggable, afterElement);
            }
        });

        listEl.addEventListener('dragend', function(e) {
            var item = e.target.closest('.section-item');
            if (item) {
                item.classList.remove('dragging');
            }
            dragSrcEl = null;
            // Save new order
            var orderedIds = Array.from(listEl.querySelectorAll('.section-item'))
                .map(el => parseInt(el.dataset.sectionId));
            fetchJSON(`${API_BASE}/products/sections/reorder?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ section_ids: orderedIds })
            }).catch(e => console.error('Failed to save section order:', e));
        });

        function getDragAfterElement(container, y) {
            var draggableElements = container.querySelectorAll('.section-item:not(.dragging)');
            var afterElement = null;
            for (var i = 0; i < draggableElements.length; i++) {
                var el = draggableElements[i];
                var rect = el.getBoundingClientRect();
                var offset = y - rect.top - rect.height / 2;
                if (offset < 0) {
                    afterElement = el;
                    break;
                }
            }
            return afterElement;
        }
    }

    function setupSectionArrows() {
        var listEl = document.getElementById('sections-list');
        if (!listEl) return;
        listEl.addEventListener('click', function(e) {
            var upBtn = e.target.closest('.section-move-up');
            var downBtn = e.target.closest('.section-move-down');
            if (!upBtn && !downBtn) return;
            var item = e.target.closest('.section-item');
            if (!item) return;
            var items = Array.from(listEl.querySelectorAll('.section-item'));
            var idx = items.indexOf(item);
            var targetIdx = upBtn ? idx - 1 : idx + 1;
            if (targetIdx < 0 || targetIdx >= items.length) return;
            var target = items[targetIdx];
            if (upBtn) {
                listEl.insertBefore(item, target);
            } else {
                listEl.insertBefore(target, item);
            }
            saveSectionOrder();
        });
    }

    async function saveSectionOrder() {
        var listEl = document.getElementById('sections-list');
        if (!listEl) return;
        var orderedIds = Array.from(listEl.querySelectorAll('.section-item'))
            .map(el => parseInt(el.dataset.sectionId));
        try {
            await fetchJSON(`${API_BASE}/products/sections/reorder?db=${db}`, {
                method: 'POST',
                body: JSON.stringify({ section_ids: orderedIds })
            });
        } catch (e) {
            console.error('Failed to save section order:', e);
        }
    }

    // === Init ===
    initSettings();
    loadDashboard();
    populateFilterDropdowns();

    // === Translate page on load ===
    function translatePage() {
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            el.textContent = t(el.dataset.i18n);
        });
    }

    async function initSettings() {
        try {
            AppState.settings = await fetchJSON(`${API_BASE}/settings/?db=${db}`);
            translatePage();
        } catch (e) {
            console.error('Settings load failed:', e);
            AppState.settings = {};
            translatePage();
        }
    }
});
