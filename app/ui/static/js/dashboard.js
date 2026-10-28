/* Dashboard / Reports screen JavaScript */
document.addEventListener('DOMContentLoaded', function() {
    const db = getActiveDb();

    const reportType = document.getElementById('report-type');
    const reportDate = document.getElementById('report-date');
    const generateBtn = document.getElementById('generate-report');
    const backBtn = document.getElementById('back-to-pos');
    const printBtn = document.getElementById('print-receipt-btn');
    const printModal = document.getElementById('print-receipt-modal');
    const printReceiptContent = document.getElementById('print-receipt-content');
    const printNowBtn = document.getElementById('print-now-btn');
    const closePrintModalBtn = document.getElementById('close-print-modal');

    const revenueEl = document.getElementById('report-revenue');
    const ordersEl = document.getElementById('report-orders');
    const discountsEl = document.getElementById('report-discounts');
    const reportSummary = document.getElementById('report-summary');
    const reportTables = document.getElementById('report-tables');
    const cashCloseBtn = document.getElementById('cash-close-btn');
    const tillBody = document.querySelector('#till-table tbody');

    // Set default date to today — the LOCAL calendar day, like the
    // server's ?date= filter (toISOString() is UTC: right after midnight
    // it would still show yesterday).
    const today = new Date();
    const pad2 = (n) => String(n).padStart(2, '0');
    const todayStr = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
    reportDate.value = todayStr;

    let currentReportData = null;

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
        // Generic: every static [data-i18n] label (buttons, headers, options).
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            el.textContent = t(el.dataset.i18n);
        });
    }

    // === Back to POS ===
    if (backBtn) {
        backBtn.addEventListener('click', function() {
            window.location.href = '/pos';
        });
    }

    // === Generate Report ===
    if (generateBtn) {
        generateBtn.addEventListener('click', function() {
            generateReport();
        });
    }

    // === Till counts (cash close) ===
    async function loadTillHistory() {
        if (!tillBody) return;
        try {
            const rows = await fetchJSON(`${API_BASE}/orders/cash-counts?db=${db}`);
            tillBody.innerHTML = '';
            rows.forEach(function(r) {
                const tr = document.createElement('tr');
                const diff = Number(r.difference) || 0;
                tr.innerHTML = `<td></td><td></td><td></td><td></td>`;
                tr.children[0].textContent = (r.timestamp || '').slice(0, 16).replace('T', ' ');
                tr.children[1].textContent = formatCurrency(r.expected_cash);
                tr.children[2].textContent = formatCurrency(r.counted_cash);
                tr.children[3].textContent = (diff > 0 ? '+' : '') + formatCurrency(diff);
                if (diff !== 0) tr.children[3].style.color = '#c0392b';
                tillBody.appendChild(tr);
            });
        } catch (e) {
            console.error('Till history load failed:', e);
        }
    }

    if (cashCloseBtn) {
        cashCloseBtn.addEventListener('click', async function() {
            try {
                const st = await fetchJSON(`${API_BASE}/orders/cash-counts/expected?db=${db}`);
                const expected = Number(st.expected_cash) || 0;
                const raw = prompt(
                    t('counted_cash') + ' (' + t('expected_cash') + ' ' +
                    formatCurrency(expected) + '):', String(expected));
                if (raw === null) return;
                const row = await fetchJSON(`${API_BASE}/orders/cash-counts?db=${db}`, {
                    method: 'POST',
                    body: JSON.stringify({ counted: raw })
                });
                const diff = Number(row.difference) || 0;
                showSuccess(t('difference') + ': ' +
                    (diff > 0 ? '+' : '') + formatCurrency(diff));
                loadTillHistory();
            } catch (e) {
                showError(e.message || e);
            }
        });
    }

    // === Print receipt modal ===
    if (printBtn) {
        printBtn.addEventListener('click', function() {
            if (currentReportData) {
                printReceiptContent.textContent = buildReportReceipt(currentReportData);
                printModal.classList.remove('hidden');
            }
        });
    }

    if (closePrintModalBtn) {
        closePrintModalBtn.addEventListener('click', function() {
            printModal.classList.add('hidden');
        });
    }

    if (printNowBtn) {
        printNowBtn.addEventListener('click', function() {
            const content = printReceiptContent.textContent;
            const printWindow = window.open('', '_blank');
            printWindow.document.write(
                '<pre>' + content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>'
            );
            printWindow.document.title = 'Posziona - Summary Report';
            printWindow.focus();
            printWindow.print();
            printWindow.close();
        });
    }

    async function generateReport() {
        const type = reportType.value;
        const date = reportDate.value;

        try {
            // Fetch summary
            const summaryUrl = type === 'day'
                ? `${API_BASE}/orders/report/summary?db=${db}&date=${date}`
                : `${API_BASE}/orders/report/summary?db=${db}`;
            const summary = await fetchJSON(summaryUrl);

            // Fetch items sold
            const itemsUrl = type === 'day'
                ? `${API_BASE}/orders/report/items?db=${db}&date=${date}`
                : `${API_BASE}/orders/report/items?db=${db}`;
            const items = await fetchJSON(itemsUrl);

            currentReportData = {
                type: type,
                date: date,
                summary: summary,
                items: items
            };

            renderReport(currentReportData);
        } catch (e) {
            // Sales reports are admin-only; operators still use this page
            // to close the till, so explain instead of raising an error.
            if (e.status === 403) {
                currentReportData = null;
                reportSummary.textContent = t('reports_admin_only');
                reportTables.innerHTML = '';
                return;
            }
            console.error('Report generation failed:', e);
            showError(t('report_failed') + ': ' + (e.message || e));
        }
    }

    function renderReport(data) {
        // Update summary sidebar
        revenueEl.textContent = formatCurrency(data.summary.total_revenue || 0);
        ordersEl.textContent = data.summary.total_orders || 0;
        discountsEl.textContent = formatCurrency(data.summary.total_discounts || 0);

        // Render header
        const periodLabel = data.type === 'day' ? t('today') + ' (' + data.date + ')' : t('whole_party');
        reportSummary.innerHTML = `
            <h3>${t('summary')}: ${periodLabel}</h3>
            <div class="total-row"><span>${t('revenue')}:</span><span>${formatCurrency(data.summary.total_revenue || 0)}</span></div>
            <div class="total-row"><span>${t('orders')}:</span><span>${data.summary.total_orders || 0}</span></div>
            <div class="total-row"><span>${t('discounts')}:</span><span>${formatCurrency(data.summary.total_discounts || 0)}</span></div>
        `;

        // Render items table
        let html = '<h4>' + t('items_sold') + '</h4>';
        if (data.items.length > 0) {
            html += '<table class="data-table"><thead><tr><th>' + t('product_col') + '</th><th>' + t('qty_col') + '</th><th>' + t('unit_price_col') + '</th><th>' + t('amount_col') + '</th></tr></thead><tbody>';
            data.items.forEach(item => {
                html += '<tr><td>' + escapeHtml(item.product_name) + '</td><td>' + item.total_quantity + '</td><td>' + formatCurrency(item.current_price || 0) + '</td><td>' + formatCurrency(item.total_amount) + '</td></tr>';
            });
            html += '</tbody></table>';
        } else {
            html += '<p class="muted-text">' + t('no_sales_data') + '</p>';
        }

        reportTables.innerHTML = html;
    }

    function buildReportReceipt(data) {
        var lines = [];
        var separator = '=================================';
        lines.push(separator);
        lines.push('        POSZIONA - SUMMARY REPORT    ');
        lines.push(separator);

        var period = data.type === 'day' ? t('report_date_label') + ': ' + data.date : t('period_label') + ': ' + t('whole_party');
        lines.push(period);
        lines.push('');
        lines.push('--- ' + t('summary') + ' ---');
        lines.push(t('revenue') + ' ' + formatCurrency(data.summary.total_revenue || 0));
        lines.push(t('orders') + '  ' + (data.summary.total_orders || 0));
        lines.push(t('discounts') + ' ' + formatCurrency(data.summary.total_discounts || 0));
        lines.push('');
        lines.push('--- ' + t('items_sold') + ' ---');
        if (data.items.length > 0) {
            data.items.forEach(function(item) {
                var qty = item.total_quantity;
                var total = item.total_amount;
                lines.push('  ' + item.product_name +
                           ' x' + qty +
                           ' @ ' + formatCurrency(item.current_price || 0) +
                           ' = ' + formatCurrency(total));
            });
        } else {
            lines.push('  (' + t('no_sales_data') + ')');
        }
        lines.push('');
        lines.push(separator);
        lines.push('  ' + t('thank_you') + '    ');
        lines.push(separator);
        return lines.join('\n');
    }

    // --- Init ---
    loadSettings();
    generateReport();
    loadTillHistory();
});
