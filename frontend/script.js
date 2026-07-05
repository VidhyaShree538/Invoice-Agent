/**
 * Invoice Processing Agent — Frontend Client Script
 * All API communication is done via fetch() to the FastAPI backend REST endpoints.
 */

// ============================================================
// AUTH GUARD — redirect to login if not authenticated
// ============================================================
(function authGuard() {
    const auth = sessionStorage.getItem('ia_auth') || localStorage.getItem('ia_auth');
    if (!auth) {
        window.location.replace('/login');
    }
})();

// Populate user info in sidebar
(function populateUser() {
    try {
        const raw = sessionStorage.getItem('ia_auth') || localStorage.getItem('ia_auth');
        const data = JSON.parse(raw);
        const name = data.username || 'User';
        const initial = name.charAt(0).toUpperCase();

        const nameEl = document.getElementById('user-name');
        const avatarEl = document.getElementById('user-avatar');
        if (nameEl) nameEl.textContent = name.charAt(0).toUpperCase() + name.slice(1);
        if (avatarEl) avatarEl.textContent = initial;
    } catch (e) { /* silently ignore */ }
})();

// ============================================================
// LOGOUT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            sessionStorage.removeItem('ia_auth');
            localStorage.removeItem('ia_auth');
            window.location.replace('/login');
        });
    }

    // Route to correct page init
    if (document.getElementById('drop-zone')) initUploadPage();
    if (document.getElementById('review-form')) initReviewPage();
    if (document.getElementById('history-table')) initHistoryPage();
    if (document.getElementById('detail-viewport')) initDetailPage();
    if (document.getElementById('vendorSpendChart')) initAnalyticsPage();
});

// ============================================================
// HELPERS
// ============================================================
function showToast(message, type = 'error') {
    const toast = document.getElementById('toast-container');
    const icon = document.getElementById('toast-icon');
    const msg = document.getElementById('toast-message');
    icon.textContent = type === 'success' ? '✅' : '⚠️';
    msg.textContent = message;
    toast.className = `toast show ${type}`;
    setTimeout(() => toast.classList.remove('show'), 4500);
}

function formatCurrency(amount) {
    const val = parseFloat(amount);
    if (isNaN(val)) return '$0.00';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch { return dateStr; }
}

function getFilename(filePath) {
    if (!filePath) return '';
    return filePath.split('/').pop().split('\\').pop();
}

function sanitizeDate(dateStr) {
    if (!dateStr) return '';
    const m = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[1]}-${m[2]}-${m[3]}` : '';
}

// Render file preview (image or PDF embed)
function renderPreview(filePath, containerId, filenameElId) {
    const container = document.getElementById(containerId);
    const filenameEl = document.getElementById(filenameElId);
    if (!filePath || !container) return;

    const filename = getFilename(filePath);
    if (filenameEl) filenameEl.textContent = filename;

    const ext = filePath.split('.').pop().toLowerCase();
    if (ext === 'pdf') {
        container.innerHTML = `<embed src="/${filePath}" type="application/pdf" width="100%" height="100%">`;
    } else {
        container.innerHTML = `<img src="/${filePath}" alt="Invoice document preview">`;
    }
}

// Build a validation flag card element
function buildFlagCard(flag) {
    const iconMap = { duplicate: '🚨', math_mismatch: '🧮', high_value: '💎', incomplete: '⚠️' };
    const icon = iconMap[flag.type] || '⚠️';
    const title = flag.type.replace(/_/g, ' ');
    const card = document.createElement('div');
    card.className = `flag-card ${flag.type}`;
    card.innerHTML = `
    <div class="flag-icon">${icon}</div>
    <div class="flag-details">
      <div class="flag-title">${title}</div>
      <div class="flag-desc">${flag.detail}</div>
    </div>`;
    return card;
}

// Build "all clear" card
function buildOkCard() {
    const card = document.createElement('div');
    card.className = 'flag-card ok';
    card.innerHTML = `
    <div class="flag-icon" style="color:var(--accent-success)">🛡️</div>
    <div class="flag-details">
      <div class="flag-title" style="color:var(--accent-success)">All Checks Passed</div>
      <div class="flag-desc">No validation issues detected. This invoice meets all standard criteria.</div>
    </div>`;
    return card;
}

// Render validation result into a container
function renderValidation(flags, badgeId, listId) {
    const badge = document.getElementById(badgeId);
    const container = document.getElementById(listId);
    if (!badge || !container) return;
    container.innerHTML = '';

    if (flags.length > 0) {
        badge.textContent = 'NEEDS REVIEW';
        badge.className = 'status-badge needs_review';
        flags.forEach(f => container.appendChild(buildFlagCard(f)));
    } else {
        badge.textContent = 'APPROVED';
        badge.className = 'status-badge approved';
        container.appendChild(buildOkCard());
    }
}

// ============================================================
// 1. UPLOAD PAGE
// ============================================================
function initUploadPage() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const loadingWrapper = document.getElementById('loading-container');
    const loadingStatus = document.getElementById('loading-status');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', e => { e.preventDefault();
        dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => { if (fileInput.files.length > 0) handleFile(fileInput.files[0]); });

    function handleFile(file) {
        // Show loading UI
        loadingWrapper.style.display = 'flex';
        dropZone.style.pointerEvents = 'none';
        dropZone.style.opacity = '0.4';

        const steps = [
            { text: '📤 Uploading file to server…', delay: 0 },
            { text: '🔄 Converting PDF to image (if needed)…', delay: 1200 },
            { text: '🤖 Extracting invoice data…', delay: 2800 },
            { text: '🛡️ Running validation checks…', delay: 7500 },
        ];
        steps.forEach(s => setTimeout(() => {
            if (loadingWrapper.style.display === 'flex') loadingStatus.textContent = s.text;
        }, s.delay));

        const formData = new FormData();
        formData.append('file', file);

        fetch('/api/invoices/upload', { method: 'POST', body: formData })
            .then(async res => {
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Upload failed');
                return data;
            })
            .then(data => {
                localStorage.setItem('pending_invoice', JSON.stringify(data));
                window.location.href = '/review';
            })
            .catch(err => {
                loadingWrapper.style.display = 'none';
                dropZone.style.pointerEvents = 'auto';
                dropZone.style.opacity = '1';
                showToast(err.message, 'error');
            });
    }
}

// ============================================================
// 2. REVIEW PAGE
// ============================================================
let existingInvoicesList = [];

function initReviewPage() {
    const raw = localStorage.getItem('pending_invoice');
    if (!raw) {
        showToast('No pending invoice. Redirecting to upload.', 'error');
        setTimeout(() => window.location.href = '/upload', 1500);
        return;
    }
    const inv = JSON.parse(raw);

    renderPreview(inv.file_path, 'preview-viewport', 'preview-filename');

    // --- Populate text/date fields ---
    document.getElementById('vendor-name').value    = inv.vendor_name    || '';
    document.getElementById('invoice-number').value = inv.invoice_number || '';
    document.getElementById('invoice-date').value   = sanitizeDate(inv.invoice_date);
    document.getElementById('due-date').value        = sanitizeDate(inv.due_date);

    // --- Render line items first (needed to compute defaults) ---
    const tbody = document.getElementById('line-items-body');
    tbody.innerHTML = '';
    const items = (inv.line_items && inv.line_items.length > 0) ? inv.line_items : [{}];
    items.forEach(item => addLineItemRow(item));

    // --- Compute smart defaults for financial fields ---
    // Subtotal: use Claude's value, or sum of line item amounts
    const lineItemSum = items.reduce((sum, item) => {
        const amt = parseFloat(item.amount);
        return sum + (isNaN(amt) ? 0 : amt);
    }, 0);

    const subtotal = (inv.subtotal != null) ? inv.subtotal : (lineItemSum > 0 ? lineItemSum : 0);
    const tax      = (inv.tax != null)      ? inv.tax      : 0;
    const total    = (inv.total != null)    ? inv.total    : parseFloat((subtotal + tax).toFixed(2));

    document.getElementById('subtotal').value = subtotal;
    document.getElementById('tax').value      = tax;
    document.getElementById('total').value    = total;

    // --- Wire up buttons ---
    document.getElementById('add-item-btn').addEventListener('click', () => addLineItemRow());

    document.getElementById('discard-btn').addEventListener('click', () => {
        localStorage.removeItem('pending_invoice');
        window.location.href = '/upload';
    });

    // Fetch existing invoices for real-time duplicate check
    fetch('/api/invoices')
        .then(r => r.json())
        .then(data => { existingInvoicesList = data; runValidation(); })
        .catch(() => runValidation());

    // Live re-validate on any field change
    document.getElementById('review-form').addEventListener('input', runValidation);

    document.getElementById('review-form').addEventListener('submit', e => {
        e.preventDefault();
        saveInvoice(inv.file_path);
    });
}

function addLineItemRow(item = {}) {
    const tbody = document.getElementById('line-items-body');
    const tr = document.createElement('tr');
    // Default null quantity to 1 — most invoices imply qty=1 when not stated
    const displayQty = (item.quantity != null) ? item.quantity : (item.description ? 1 : '');

    tr.innerHTML = `
    <td><input type="text" class="item-desc" value="${item.description || ''}" placeholder="Description"></td>
    <td><input type="number" class="item-qty"   value="${displayQty}" step="any" placeholder="1"    style="text-align:right"></td>
    <td><input type="number" class="item-price" value="${item.unit_price ?? ''}" step="any" placeholder="0.00" style="text-align:right"></td>
    <td><input type="number" class="item-amount" value="${item.amount   ?? ''}" step="any" placeholder="0.00" style="text-align:right"></td>
    <td style="text-align:center">
      <button type="button" style="background:none;border:none;cursor:pointer;color:var(--accent-danger);font-size:1rem;" class="del-row-btn">🗑️</button>
    </td>`;

    const qtyEl = tr.querySelector('.item-qty');
    const priceEl = tr.querySelector('.item-price');
    const amountEl = tr.querySelector('.item-amount');

    function autoCalc() {
        const q = parseFloat(qtyEl.value),
            p = parseFloat(priceEl.value);
        if (!isNaN(q) && !isNaN(p)) amountEl.value = (q * p).toFixed(2);
        runValidation();
    }

    qtyEl.addEventListener('input', autoCalc);
    priceEl.addEventListener('input', autoCalc);
    amountEl.addEventListener('input', runValidation);

    tr.querySelector('.del-row-btn').addEventListener('click', () => {
        tr.remove();
        if (tbody.children.length === 0) addLineItemRow();
        runValidation();
    });

    tbody.appendChild(tr);
}

function getFormData() {
    const lineItems = [];
    let lineTotal = 0;
    document.querySelectorAll('#line-items-body tr').forEach(tr => {
        const desc = tr.querySelector('.item-desc').value.trim();
        const qty = parseFloat(tr.querySelector('.item-qty').value);
        const price = parseFloat(tr.querySelector('.item-price').value);
        const amount = parseFloat(tr.querySelector('.item-amount').value) || 0;
        if (desc) { lineItems.push({ description: desc, quantity: isNaN(qty) ? null : qty, unit_price: isNaN(price) ? null : price, amount });
            lineTotal += amount; }
    });
    return {
        vendor_name: document.getElementById('vendor-name').value.trim(),
        invoice_number: document.getElementById('invoice-number').value.trim(),
        invoice_date: document.getElementById('invoice-date').value || null,
        due_date: document.getElementById('due-date').value || null,
        subtotal: parseFloat(document.getElementById('subtotal').value) || null,
        tax: parseFloat(document.getElementById('tax').value) || 0,
        total: parseFloat(document.getElementById('total').value),
        line_items: lineItems,
        _lineTotal: lineTotal,
    };
}

function runValidation() {
    const d = getFormData();
    const flags = [];
    const THRESHOLD = 50000;

    // 1. Duplicate
    if (d.vendor_name && d.invoice_number) {
        const dup = existingInvoicesList.find(inv =>
            (inv.vendor_name || '').toLowerCase() === d.vendor_name.toLowerCase() &&
            (inv.invoice_number || '').toLowerCase() === d.invoice_number.toLowerCase()
        );
        if (dup) flags.push({ type: 'duplicate', detail: `Matches existing invoice (${d.vendor_name} / ${d.invoice_number})` });
    }

    // 2. Math
    const expected = d._lineTotal + (d.tax || 0);
    if (!isNaN(d.total) && Math.abs(expected - d.total) > 1.0) {
        flags.push({ type: 'math_mismatch', detail: `Items (${d._lineTotal.toFixed(2)}) + tax (${(d.tax||0).toFixed(2)}) = ${expected.toFixed(2)}, total = ${d.total.toFixed(2)}` });
    }

    // 3. High value
    if (!isNaN(d.total) && d.total > THRESHOLD) {
        flags.push({ type: 'high_value', detail: `Total ${formatCurrency(d.total)} exceeds threshold ${formatCurrency(THRESHOLD)}` });
    }

    // 4. Missing fields
    const missing = [];
    if (!d.vendor_name) missing.push('vendor name');
    if (!d.invoice_number) missing.push('invoice number');
    if (isNaN(d.total)) missing.push('total');
    if (missing.length) flags.push({ type: 'incomplete', detail: `Missing required: ${missing.join(', ')}` });

    renderValidation(flags, 'validation-badge', 'flags-list');
}

function saveInvoice(filePath) {
    const d = getFormData();
    const saveBtn = document.getElementById('save-btn');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';

    const body = {...d, file_path: filePath };
    delete body._lineTotal;

    fetch('/api/invoices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Save failed');
            return data;
        })
        .then(() => {
            localStorage.removeItem('pending_invoice');
            showToast('Invoice saved successfully!', 'success');
            setTimeout(() => window.location.href = '/history', 1000);
        })
        .catch(err => {
            saveBtn.disabled = false;
            saveBtn.textContent = '✅ Approve & Save';
            showToast(err.message, 'error');
        });
}

// ============================================================
// 3. HISTORY PAGE
// ============================================================
let allInvoices = [];

function initHistoryPage() {
    fetch('/api/invoices')
        .then(r => r.json())
        .then(data => {
            allInvoices = data;
            renderHistory(data);
        })
        .catch(() => showToast('Failed to load invoice history.', 'error'));

    document.getElementById('history-search').addEventListener('input', e => {
        const q = e.target.value.toLowerCase().trim();
        renderHistory(allInvoices.filter(inv =>
            (inv.vendor_name || '').toLowerCase().includes(q) ||
            (inv.invoice_number || '').toLowerCase().includes(q)
        ));
    });
}

function renderHistory(invoices) {
    const tbody = document.getElementById('history-tbody');
    const summary = document.getElementById('invoice-count-summary');
    tbody.innerHTML = '';

    if (summary) {
        summary.textContent = invoices.length === allInvoices.length ?
            `${allInvoices.length} record${allInvoices.length !== 1 ? 's' : ''}` :
            `${invoices.length} of ${allInvoices.length} records`;
    }

    if (invoices.length === 0) {
        tbody.innerHTML = `
      <tr><td colspan="7">
        <div class="empty-state">
          <div class="empty-state-icon">🔍</div>
          <div class="empty-state-title">No invoices found</div>
          <div class="empty-state-desc">Try a different search term or upload a new invoice.</div>
          <a href="/upload" class="btn btn-primary btn-sm">Upload Invoice</a>
        </div>
      </td></tr>`;
        return;
    }

    invoices.forEach(inv => {
        const tr = document.createElement('tr');
        tr.addEventListener('click', () => window.location.href = `/detail?id=${inv.id}`);

        const isApproved = inv.status === 'approved';
        tr.innerHTML = `
      <td style="color:var(--text-secondary); font-size:0.82rem;">${formatDate(inv.created_at)}</td>
      <td style="font-weight:600;">${inv.vendor_name || '—'}</td>
      <td><code>${inv.invoice_number || '—'}</code></td>
      <td style="color:var(--text-secondary);">${formatDate(inv.invoice_date)}</td>
      <td style="text-align:right; font-weight:600; font-family:'Outfit';">${formatCurrency(inv.total)}</td>
      <td style="text-align:center;">
        <span class="status-badge ${inv.status}">${isApproved ? '✅ Approved' : '⚠️ Needs Review'}</span>
      </td>
      <td style="text-align:center;">
        <a href="/detail?id=${inv.id}" class="btn btn-secondary btn-sm" onclick="event.stopPropagation()">View →</a>
      </td>`;
        tbody.appendChild(tr);
    });
}

// ============================================================
// 4. DETAIL PAGE
// ============================================================
function initDetailPage() {
    const id = new URLSearchParams(window.location.search).get('id');
    if (!id) { window.location.href = '/history'; return; }

    fetch(`/api/invoices/${id}`)
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Not found');
            return data;
        })
        .then(inv => {
            document.getElementById('detail-subtitle').textContent = `${inv.vendor_name} — #${inv.invoice_number}`;

            renderPreview(inv.file_path, 'detail-viewport', 'detail-filename');
            renderValidation(inv.flags || [], 'detail-validation-badge', 'detail-flags-list');

            document.getElementById('detail-vendor-name').textContent = inv.vendor_name || '—';
            document.getElementById('detail-invoice-number').textContent = inv.invoice_number || '—';
            document.getElementById('detail-invoice-date').textContent = formatDate(inv.invoice_date);
            document.getElementById('detail-due-date').textContent = formatDate(inv.due_date);
            document.getElementById('detail-db-id').textContent = `#${inv.id}`;
            document.getElementById('detail-processed-at').textContent =
                formatDate(inv.created_at) + ' ' +
                new Date(inv.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            document.getElementById('detail-subtotal').textContent = formatCurrency(inv.subtotal);
            document.getElementById('detail-tax').textContent = formatCurrency(inv.tax);
            document.getElementById('detail-total').textContent = formatCurrency(inv.total);

            const tbody = document.getElementById('detail-line-items-body');
            tbody.innerHTML = '';
            if (inv.line_items && inv.line_items.length > 0) {
                inv.line_items.forEach(item => {
                    const tr = document.createElement('tr');
                    // Show quantity — default null to 1 since most invoices imply single unit
                    const qty = (item.quantity != null) ? item.quantity : 1;
                    tr.innerHTML = `
            <td>${item.description || '—'}</td>
            <td style="text-align:right">${qty}</td>
            <td style="text-align:right">${item.unit_price != null ? formatCurrency(item.unit_price) : '—'}</td>
            <td style="text-align:right; font-weight:600;">${item.amount != null ? formatCurrency(item.amount) : '—'}</td>`;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:1.5rem;">No line items recorded.</td></tr>`;
            }
        })
        .catch(err => {
            showToast(err.message, 'error');
            setTimeout(() => window.location.href = '/history', 2000);
        });
}

// ============================================================
// 5. ANALYTICS PAGE
// ============================================================
function initAnalyticsPage() {
    Promise.all([
            fetch('/api/invoices/analytics').then(r => r.json()),
            fetch('/api/invoices').then(r => r.json()),
        ])
        .then(([analytics, history]) => {
            const approved = analytics.status_counts.approved;
            const review = analytics.status_counts.needs_review;
            const total = approved + review;
            const spend = history.reduce((s, i) => s + (i.total || 0), 0);

            document.getElementById('kpi-total-spend').textContent = formatCurrency(spend);
            document.getElementById('kpi-total-count').textContent = total;
            document.getElementById('kpi-approved-count').textContent = approved;
            document.getElementById('kpi-review-count').textContent = review;

            // Bar chart — vendor spend
            const vendors = (analytics.spend_by_vendor || []).slice(0, 8);
            const ctxBar = document.getElementById('vendorSpendChart').getContext('2d');
            new Chart(ctxBar, {
                type: 'bar',
                data: {
                    labels: vendors.length ? vendors.map(v => v.vendor_name) : ['No data'],
                    datasets: [{
                        label: 'Total Spend ($)',
                        data: vendors.length ? vendors.map(v => v.total_spend) : [0],
                        backgroundColor: 'rgba(99,102,241,0.7)',
                        borderColor: '#6366f1',
                        borderWidth: 1,
                        borderRadius: 6,
                        hoverBackgroundColor: '#818cf8',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#9ca3af', font: { family: 'Inter', size: 11 } } },
                        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#9ca3af', font: { family: 'Inter', size: 11 } } },
                    }
                }
            });

            // Doughnut chart — status split
            const ctxPie = document.getElementById('statusCountsChart').getContext('2d');
            new Chart(ctxPie, {
                type: 'doughnut',
                data: {
                    labels: ['Approved', 'Needs Review'],
                    datasets: [{
                        data: [approved || 0, review || 0],
                        backgroundColor: ['#10b981', '#f43f5e'],
                        borderColor: '#0d1117',
                        borderWidth: 3,
                        hoverOffset: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '65%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#f3f4f6', font: { family: 'Inter', size: 12 }, padding: 18 }
                        }
                    }
                }
            });
        })
        .catch(() => showToast('Failed to load analytics data.', 'error'));
}