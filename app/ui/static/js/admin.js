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
            }
        });
    });
    
    logoutBtn.addEventListener('click', function() {
        fetchJSON(`${API_BASE}/auth/logout?db=${db}`, { method: 'POST' })
            .then(() => { window.location.href = '/'; })
            .catch(() => { window.location.href = '/'; });
    });
    
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
                row.insertCell(0).textContent = item.product_name;
                row.insertCell(1).textContent = item.total_quantity;
                row.insertCell(2).textContent = formatCurrency(item.total_amount);
            });
        } catch (e) {
            console.error('Dashboard load failed:', e);
        }
    }
    
    // === Products ===
    async function loadProducts() {
        try {
            const products = await fetchJSON(`${API_BASE}/products/all?db=${db}`);
            const tbody = document.querySelector('#products-table tbody');
            tbody.innerHTML = '';

            products.forEach(p => {
                const row = tbody.insertRow();
                row.insertCell(0).textContent = p.name;
                row.insertCell(1).textContent = formatCurrency(p.price);
                row.insertCell(2).textContent = `${p.section_name} > ${p.subsection_name}`;
                row.insertCell(3).textContent = p.stock_count === null ? 'Unlimited' : p.stock_count;

                const actionsCell = row.insertCell(4);
                const editBtn = document.createElement('button');
                editBtn.textContent = 'Edit';
                editBtn.className = 'btn-sm';
                editBtn.onclick = () => editProduct(p);
                actionsCell.appendChild(editBtn);

                const delBtn = document.createElement('button');
                delBtn.textContent = 'Delete';
                delBtn.className = 'btn-sm btn-secondary';
                delBtn.style.marginLeft = '5px';
                delBtn.onclick = () => deleteProduct(p.id, p.name);
                actionsCell.appendChild(delBtn);
            });
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
        let selectedSubsectionId = product.subsection_id;

        sections.forEach(section => {
            sectionOptions += `<option value="${section.id}" ${section.id == product.section_id ? 'selected' : ''}>${section.name}</option>`;
        });

        // Get subsections for the product's section
        if (product.section_id) {
            const subsectionResp = await fetch(`${API_BASE}/products/subsections?db=${db}`);
            // Actually, subsections are returned within the section object
            const matchingSection = sections.find(s => s.id == product.section_id);
            if (matchingSection && matchingSection.subsections) {
                matchingSection.subsections.forEach(sub => {
                    subsectionOptions += `<option value="${sub.id}" ${sub.id == selectedSubsectionId ? 'selected' : ''}>${sub.name}</option>`;
                });
            }
        }

        const html = `
            <div style="margin-bottom:10px;">
                <label>Name:</label>
                <input type="text" id="edit-product-name" value="${product.name}" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Price (€):</label>
                <input type="number" id="edit-product-price" value="${product.price}" step="0.01" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Section:</label>
                <select id="edit-product-section" style="width:100%;">${sectionOptions}</select>
            </div>
            <div style="margin-bottom:10px;">
                <label>Subsection:</label>
                <select id="edit-product-subsection" style="width:100%;">${subsectionOptions}</select>
            </div>
            <div style="margin-bottom:10px;">
                <label>SKU:</label>
                <input type="text" id="edit-product-sku" value="${product.sku || ''}" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Stock (leave empty for unlimited):</label>
                <input type="number" id="edit-product-stock" value="${product.stock_count === null ? '' : product.stock_count}" style="width:100%;">
            </div>
        `;

        const result = await showDialog('Edit Product', html, 'Save');
        if (result) {
            const sectionId = document.getElementById('edit-product-section').value;
            const subsectionId = document.getElementById('edit-product-subsection').value;
            await fetchJSON(`${API_BASE}/products/products/${product.id}?db=${db}`, {
                method: 'PUT',
                body: JSON.stringify({
                    name: document.getElementById('edit-product-name').value,
                    price: parseFloat(document.getElementById('edit-product-price').value),
                    section_id: sectionId ? parseInt(sectionId) : null,
                    subsection_id: subsectionId ? parseInt(subsectionId) : null,
                    sku: document.getElementById('edit-product-sku').value || null,
                    stock: document.getElementById('edit-product-stock').value ? parseInt(document.getElementById('edit-product-stock').value) : null
                })
            });
            loadProducts();
        }

        // Set up section change handler for edit dialog
        const editSectionSelect = document.getElementById('edit-product-section');
        if (editSectionSelect) {
            editSectionSelect.onchange = async function() {
                await updateSubsectionDropdown('edit-' + this.value, document.getElementById('edit-product-subsection').value);
            };
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
        overlay.style.cssText = 'position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:2000; display:flex; align-items:center; justify-content:center;';

        const dialog = document.createElement('div');
        dialog.style.cssText = 'background:white; padding:20px; border-radius:8px; min-width:350px; max-width:500px;';
        dialog.innerHTML = `
            <h3>${title}</h3>
            <div id="dialog-content">${htmlContent}</div>
            <div style="margin-top:15px; text-align:right;">
                <button id="dialog-cancel" class="btn-secondary btn-sm">Cancel</button>
                <button id="dialog-confirm" class="btn-primary btn-sm" style="margin-left:5px;">${confirmBtnText}</button>
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
    async function importCsv() {
        const csvText = await showCsvImportDialog();
        if (csvText === null) return; // Cancelled

        // Parse CSV into JSON rows
        const lines = csvText.trim().split('\n');
        if (lines.length < 2) {
            alert('CSV must have a header row and at least one data row');
            return;
        }

        const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
        const rows = [];
        for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split(',').map(v => v.trim());
            if (values.length === headers.length) {
                const row = {};
                headers.forEach((h, idx) => {
                    row[h] = values[idx];
                });
                rows.push(row);
            }
        }

        if (rows.length === 0) {
            alert('No valid data rows found');
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
            <p style="font-size:14px; color:#555; margin-bottom:10px;">
                Paste CSV content below. Expected columns: section, subsection, name, price, sku (optional), stock_count (optional)
            </p>
            <textarea id="csv-input" style="width:100%; height:200px; font-family:monospace; font-size:12px; padding:5px;"></textarea>
        `;
        return new Promise((resolve) => {
            showDialog('CSV Import', html, 'Import').then(confirmed => {
                if (confirmed) {
                    const csvText = document.getElementById('csv-input').value;
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
            // Create a blob and download
            const blob = new Blob([data.csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = data.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch(e) {
            alert('Export failed: ' + (e.message || e));
        }
    }
    
    // === Parties ===
    async function loadParties() {
        try {
            const parties = await fetchJSON(`${API_BASE}/parties/?db=${db}`);
            const tbody = document.querySelector('#parties-table tbody');
            tbody.innerHTML = '';
            
            parties.forEach(p => {
                const row = tbody.insertRow();
                row.insertCell(0).textContent = p.name;
                row.insertCell(1).textContent = p.modified;
                const actionsCell = row.insertCell(2);
                const delBtn = document.createElement('button');
                delBtn.textContent = 'Delete';
                delBtn.className = 'btn-sm btn-secondary';
                delBtn.onclick = () => deleteParty(p.name);
                actionsCell.appendChild(delBtn);
            });
        } catch (e) {
            console.error('Parties load failed:', e);
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
                    if (input.type === 'select-one') {
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
                    <span class="tag-bg-info" style="font-size:11px; color:#888;">
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
                display.innerHTML += '<p style="color:#999;">No tags assigned</p>';
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
            <div style="margin-bottom:10px;">
                <label>Name:</label>
                <input type="text" id="new-product-name" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Price (€):</label>
                <input type="number" id="new-product-price" step="0.01" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Section:</label>
                <select id="new-product-section" style="width:100%;">${sectionOptions}</select>
            </div>
            <div id="new-section-row" style="margin-bottom:10px; display:none;">
                <label>New Section Name:</label>
                <input type="text" id="new-section-name" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Subsection:</label>
                <select id="new-product-subsection" style="width:100%;">${subsectionOptions}</select>
            </div>
            <div id="new-subsection-row" style="margin-bottom:10px; display:none;">
                <label>New Subsection Name:</label>
                <input type="text" id="new-subsection-name" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>SKU:</label>
                <input type="text" id="new-product-sku" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Stock (leave empty for unlimited):</label>
                <input type="number" id="new-product-stock" style="width:100%;">
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
                    newSectionRow.style.display = 'block';
                    newSectionInput.required = true;
                } else {
                    newSectionRow.style.display = 'none';
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
                    newSubsectionRow.style.display = 'block';
                    newSubsectionInput.required = true;
                } else {
                    newSubsectionRow.style.display = 'none';
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
        const subSelectId = sectionId.startsWith('edit-') ? 'edit-product-subsection' : 'new-product-subsection';
        const subSelect = document.getElementById(subSelectId);
        if (!subSelect) return;

        if (!sectionId) {
            subSelect.innerHTML = '<option value="">Select Subsection</option>';
            return;
        }

        const sections = await fetchJSON(`${API_BASE}/products/?db=${db}`);
        const section = sections.find(s => s.id == sectionId.replace('edit-', ''));
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
            <div style="margin-bottom:10px;">
                <label>Party Name:</label>
                <input type="text" id="new-party-name" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>Template (optional):</label>
                <select id="new-party-template" style="width:100%;">${templateOptions}</select>
            </div>
            <div style="margin-bottom:10px;">
                <label>Start Date:</label>
                <input type="date" id="new-party-start-date" style="width:100%;">
            </div>
            <div style="margin-bottom:10px;">
                <label>End Date (optional):</label>
                <input type="date" id="new-party-end-date" style="width:100%;">
            </div>
        `;

        const confirmed = await showDialog('Create New Party', html, 'Create');
        if (confirmed) {
            const name = document.getElementById('new-party-name').value.trim();
            const templateValue = document.getElementById('new-party-template').value;
            const startDate = document.getElementById('new-party-start-date').value;
            const endDate = document.getElementById('new-party-end-date').value;

            if (!name) {
                alert('Party name is required');
                return;
            }

            try {
                if (templateValue === '__empty__') {
                    await fetchJSON(`${API_BASE}/parties/create-empty?db=${db}`, {
                        method: 'POST',
                        body: JSON.stringify({
                            name: name,
                            start_date: startDate,
                            end_date: endDate || null
                        })
                    });
                } else {
                    await fetchJSON(`${API_BASE}/parties/?db=${db}`, {
                        method: 'POST',
                        body: JSON.stringify({
                            name: name,
                            template_id: parseInt(templateValue),
                            start_date: startDate,
                            end_date: endDate || null
                        })
                    });
                }
                loadParties();
            } catch(e) {
                alert('Failed to create party: ' + (e.message || e));
            }
        }
    });

    // Wire up CSV import/export buttons
    document.getElementById('import-csv-btn').addEventListener('click', importCsv);
    document.getElementById('export-csv-btn').addEventListener('click', exportCsv);
    
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
        for (const [key, value] of formData.entries()) {
            settings[key] = value;
        }
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
    
    // === Init ===
    loadDashboard();
});
