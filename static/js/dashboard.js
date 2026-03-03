/* ═══════════════════════════════════════════════════════════════
   Intelli-Credit Dashboard — Client Logic + WebSocket
   ═══════════════════════════════════════════════════════════════ */

// ─── State ──────────────────────────────────────────────────────
const STATE = {
    user: null,
    currentSection: 'dashboard',
    currentApp: null,         // Active application object
    uploadedFiles: [],        // Files staged for upload
    layersDone: new Set(),    // Completed layer numbers
    socket: null
};

// ─── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await loadSession();
    initSocket();
    loadHistory();
});

async function loadSession() {
    try {
        const res = await fetch('/api/session');
        STATE.user = await res.json();
        document.getElementById('userName').textContent = STATE.user.full_name;
        document.getElementById('userRole').textContent = STATE.user.role;
        document.getElementById('userAvatar').textContent = STATE.user.full_name.charAt(0).toUpperCase();

        // Show admin nav items based on permissions
        const perms = STATE.user.permissions || [];
        if (perms.includes('*') || perms.includes('MANAGE_USERS')) {
            document.getElementById('navUsers').style.display = '';
        }
        if (perms.includes('*') || perms.includes('MANAGE_ROLES')) {
            document.getElementById('navRoles').style.display = '';
        }

        // Apply permission gating to hide elements user shouldn't see
        applyPermissionGating(perms);
    } catch (e) {
        console.error('Failed to load session', e);
    }
}

// ─── Permission Gating ──────────────────────────────────────────
// Hides any element with data-perm="PERM" if user lacks that permission.
// Hides sidebar nav items with data-nav-perm="PERM" the same way.
// SA users (permission '*') see everything.
function applyPermissionGating(perms) {
    const isSuperAdmin = perms.includes('*');

    // Gate action elements (buttons, upload zones, etc.)
    document.querySelectorAll('[data-perm]').forEach(el => {
        const required = el.getAttribute('data-perm');
        if (!isSuperAdmin && !perms.includes(required)) {
            el.style.display = 'none';
        }
    });

    // Gate sidebar nav items
    document.querySelectorAll('[data-nav-perm]').forEach(el => {
        const required = el.getAttribute('data-nav-perm');
        if (!isSuperAdmin && !perms.includes(required)) {
            el.style.display = 'none';
        }
    });
}


// ─── WebSocket ──────────────────────────────────────────────────
function initSocket() {
    STATE.socket = io();

    STATE.socket.on('layer_progress', (data) => {
        console.log('Layer progress:', data);
        updateLayerStatus(data.layer, 'processing', data.pct);
    });

    STATE.socket.on('layer_complete', (data) => {
        console.log('Layer complete:', data);
        STATE.layersDone.add(data.layer);
        updateLayerStatus(data.layer, 'done');
        // Enable this layer's section in the sidebar
        enableLayerNav(data.layer);
        // Auto-show the next layer after a brief pause
        setTimeout(() => {
            const nextLayer = data.layer + 1;
            if (nextLayer <= 7) {
                updateLayerStatus(nextLayer, 'processing', 0);
            }
        }, 1200);
    });

    STATE.socket.on('pipeline_complete', (data) => {
        console.log('Pipeline complete:', data);
        showToast('✅ Pipeline completed for ' + data.case_id);
        // Update active app info
        const statusEl = document.getElementById('activeAppStatus');
        statusEl.innerHTML = '<span class="status-dot done"></span> Processing Complete';
        statusEl.style.color = 'var(--accent-green)';
        // Enable all layer nav items
        for (let i = 1; i <= 7; i++) enableLayerNav(i);
        // Load data into views
        loadApplicationData(data.app_id || STATE.currentApp?.id);
        loadHistory();
    });

    STATE.socket.on('pipeline_error', (data) => {
        console.error('Pipeline error:', data);
        showToast('❌ Error: ' + data.error);
    });

    // ─── HITL: Document Review ──────────────────────────────────
    STATE.socket.on('hitl_review_needed', (data) => {
        console.log('HITL review needed:', data);
        STATE._hitlAppId = data.app_id;
        showHitlReviewModal(data);
    });

    STATE.socket.on('pipeline_resumed', (data) => {
        console.log('Pipeline resumed:', data);
        closeModal('modalHitlReview');
        showToast('▶ Pipeline resumed — processing Layer 2...');
    });
}

// ─── HITL Document Review Functions ─────────────────────────────
const DOC_CATEGORIES = [
    { key: 'SRC_GST', label: 'GST Returns' },
    { key: 'SRC_ITR', label: 'Income Tax Return' },
    { key: 'SRC_BANK', label: 'Bank Statement' },
    { key: 'SRC_FS', label: 'Financial Statements' },
    { key: 'SRC_AR', label: 'Annual Report' },
    { key: 'SRC_BMM', label: 'Board Minutes' },
    { key: 'SRC_RAT', label: 'Credit Rating' },
    { key: 'SRC_SHP', label: 'Shareholding' },
    { key: 'SRC_UNKNOWN', label: 'Unknown / Skip' }
];

function showHitlReviewModal(data) {
    document.getElementById('hitlCaseId').textContent = data.case_id;
    document.getElementById('hitlCompanyName').textContent = data.company_name;

    const tbody = document.getElementById('hitlDocsBody');
    tbody.innerHTML = data.documents.map((doc, i) => {
        const options = DOC_CATEGORIES.map(cat =>
            `<option value="${cat.key}" ${cat.key === doc.detected_category ? 'selected' : ''}>${cat.label} (${cat.key})</option>`
        ).join('');

        const ocrBadge = doc.ocr_required
            ? '<span class="hitl-ocr-yes">Yes</span>'
            : '<span class="hitl-ocr-no">No</span>';

        return `<tr data-doc-id="${doc.doc_id}">
            <td>${i + 1}</td>
            <td><strong>${doc.filename}</strong></td>
            <td>${doc.file_type}</td>
            <td><select class="hitl-select" data-doc-id="${doc.doc_id}">${options}</select></td>
            <td>${doc.pages}</td>
            <td>${ocrBadge}</td>
        </tr>`;
    }).join('');

    document.getElementById('modalHitlReview').style.display = 'flex';

    // Re-init lucide icons if available
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

async function confirmHitlReview() {
    const appId = STATE._hitlAppId;
    if (!appId) { showToast('❌ No application to confirm'); return; }

    // Collect all doc categories from the selects
    const docs = [];
    document.querySelectorAll('#hitlDocsBody select.hitl-select').forEach(sel => {
        docs.push({
            doc_id: parseInt(sel.getAttribute('data-doc-id')),
            detected_category: sel.value
        });
    });

    document.getElementById('btnConfirmHitl').disabled = true;
    document.getElementById('btnConfirmHitl').textContent = 'Processing...';

    try {
        const res = await fetch(`/api/applications/${appId}/confirm_docs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ documents: docs })
        });
        const result = await res.json();
        if (result.error) {
            showToast('❌ ' + result.error);
            document.getElementById('btnConfirmHitl').disabled = false;
            document.getElementById('btnConfirmHitl').textContent = 'Confirm & Continue Pipeline';
            return;
        }
        showToast('✅ Documents confirmed — pipeline resuming');
        closeModal('modalHitlReview');
    } catch (e) {
        showToast('❌ Failed to confirm documents');
        document.getElementById('btnConfirmHitl').disabled = false;
        document.getElementById('btnConfirmHitl').textContent = 'Confirm & Continue Pipeline';
    }
}

async function cancelHitlReview() {
    const appId = STATE._hitlAppId;
    closeModal('modalHitlReview');
    if (appId) {
        // Reset application status to pending
        try {
            await fetch(`/api/applications/${appId}/cancel_review`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (e) { /* ignore */ }
    }
    showToast('⚠️ Pipeline cancelled');
}


// ─── Section Navigation ─────────────────────────────────────────
function showSection(section) {
    // Check if disabled layer
    const navItem = document.querySelector(`.nav-item[data-section="${section}"]`);
    if (navItem && navItem.classList.contains('disabled')) return;

    STATE.currentSection = section;

    // Toggle active section
    document.querySelectorAll('.content-section').forEach(el => el.classList.remove('active'));
    const target = document.getElementById('section-' + section);
    if (target) target.classList.add('active');

    // Toggle active nav
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    if (navItem) navItem.classList.add('active');

    // Update topbar title
    const titles = {
        dashboard: ['Dashboard', 'AI Corporate Credit Decisioning Engine'],
        ingestion: ['Data Ingestion', 'Upload and process financial documents'],
        financial: ['Financial Analysis', STATE.currentApp ? STATE.currentApp.company_name + ' — Multi-year trend' : 'Financial metrics and ratios'],
        anomaly: ['Anomaly Detection', 'GST-Bank mismatch, circular trading flags'],
        research: ['Web Research', 'News, MCA filings, litigation history'],
        scoring: ['Risk Scoring', 'Multi-factor risk assessment model'],
        cam: ['CAM Report', 'Structured credit assessment memorandum'],
        decision: ['Decision Engine', 'Final credit decision with conditions'],
        history: ['History', 'Past completed applications'],
        users: ['User Management', 'Manage system users and access'],
        roles: ['Role Management', 'Configure roles and permissions']
    };
    const [title, subtitle] = titles[section] || ['Dashboard', ''];
    document.getElementById('pageTitle').textContent = title;
    document.getElementById('pageSubtitle').textContent = subtitle;

    // Load section-specific data
    if (section === 'history') loadHistory();
    if (section === 'users') loadUsers();
    if (section === 'roles') loadRoles();
}

// ─── Layer Status Management ────────────────────────────────────
function updateLayerStatus(layerNum, status, pct) {
    const statusEl = document.getElementById('layerStatus' + layerNum);
    if (!statusEl) return;

    if (status === 'processing') {
        statusEl.innerHTML = '<span class="status-dot processing"></span>';
    } else if (status === 'done') {
        statusEl.innerHTML = '✅';
    }

    // Update pipeline status list in Risk Scoring view
    updatePipelineStatusList();
}

function enableLayerNav(layerNum) {
    const layerSections = { 1: 'ingestion', 2: 'financial', 3: 'anomaly', 4: 'research', 5: 'scoring', 6: 'cam', 7: 'decision' };
    const section = layerSections[layerNum];
    if (!section) return;
    const navItem = document.querySelector(`.nav-item[data-section="${section}"]`);
    if (navItem) {
        navItem.classList.remove('disabled');
        navItem.classList.add('completed');
    }
}

function updatePipelineStatusList() {
    const container = document.getElementById('pipelineStatusList');
    if (!container) return;

    const layers = [
        { num: 1, name: 'Data Ingestion', detail: 'PDFs, GST, ITR, Bank Stmts', icon: '📁' },
        { num: 2, name: 'Financial Extraction', detail: 'Metrics & Ratios', icon: '📈' },
        { num: 3, name: 'Anomaly Detection', detail: 'Cross-validation', icon: '⚠️' },
        { num: 4, name: 'Web Research', detail: 'News, MCA, Litigation', icon: '🌐' },
        { num: 5, name: 'Risk Scoring', detail: 'Multi-factor Model', icon: '🎯' },
        { num: 6, name: 'CAM Generation', detail: 'Structured Report', icon: '📄' }
    ];

    container.innerHTML = layers.map(l => {
        let badgeClass = 'pending', badgeText = 'Pending';
        if (STATE.layersDone.has(l.num)) { badgeClass = 'done'; badgeText = '✓ Done'; }
        else if (document.getElementById('layerStatus' + l.num)?.innerHTML.includes('processing')) {
            badgeClass = 'processing'; badgeText = 'Processing';
        }
        return `<div class="pipeline-status-item">
            <div class="pipeline-status-icon">${l.icon}</div>
            <div class="pipeline-status-name">${l.name}<div class="pipeline-status-detail">${l.detail}</div></div>
            <span class="pipeline-status-badge ${badgeClass}">${badgeText}</span>
        </div>`;
    }).join('');
}

// ─── New Application ────────────────────────────────────────────
function showNewAppModal() {
    document.getElementById('inputCompanyName').value = '';
    document.getElementById('modalNewApp').style.display = 'flex';
}

async function createApplication() {
    const name = document.getElementById('inputCompanyName').value.trim();
    if (!name) { showToast('⚠️ Enter a company name'); return; }

    try {
        const res = await fetch('/api/applications', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company_name: name })
        });
        const data = await res.json();
        if (data.error) { showToast('❌ ' + data.error); return; }

        STATE.currentApp = { id: data.id, case_id: data.case_id, company_name: name };

        // Show active app in sidebar
        document.getElementById('activeAppInfo').style.display = '';
        document.getElementById('activeAppName').textContent = name;
        document.getElementById('activeAppId').textContent = data.case_id;
        document.getElementById('activeAppStatus').innerHTML = '<span class="status-dot active"></span> Ready';

        closeModal('modalNewApp');
        showSection('ingestion');
        showToast('✅ Application ' + data.case_id + ' created');
    } catch (e) {
        showToast('❌ Failed to create application');
    }
}

// ─── File Upload ────────────────────────────────────────────────
function handleDrop(e) {
    e.preventDefault();
    e.target.closest('.upload-zone')?.classList.remove('dragover');
    const files = Array.from(e.dataTransfer.files);
    addFilesToQueue(files);
}

function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    addFilesToQueue(files);
    e.target.value = ''; // Reset so same files can be re-selected
}

function addFilesToQueue(files) {
    files.forEach(f => {
        if (!STATE.uploadedFiles.find(uf => uf.name === f.name)) {
            STATE.uploadedFiles.push(f);
        }
    });
    renderDocQueue();
    document.getElementById('btnRunIngestion').disabled = STATE.uploadedFiles.length === 0;
}

function removeFromQueue(index) {
    STATE.uploadedFiles.splice(index, 1);
    renderDocQueue();
    document.getElementById('btnRunIngestion').disabled = STATE.uploadedFiles.length === 0;
}

function renderDocQueue() {
    const container = document.getElementById('docQueue');
    const countEl = document.getElementById('docCount');
    countEl.textContent = STATE.uploadedFiles.length;

    const badge = document.getElementById('badgeIngestion');
    if (STATE.uploadedFiles.length > 0) {
        badge.style.display = '';
        badge.textContent = STATE.uploadedFiles.length;
    } else {
        badge.style.display = 'none';
    }

    if (STATE.uploadedFiles.length === 0) {
        container.innerHTML = '<div class="empty-state">No documents uploaded yet</div>';
        return;
    }

    container.innerHTML = STATE.uploadedFiles.map((f, i) => {
        const ext = f.name.split('.').pop().toLowerCase();
        let typeBadge = 'pdf', typeLabel = 'PDF';
        if (['xlsx', 'xls'].includes(ext)) { typeBadge = 'excel'; typeLabel = 'Excel'; }
        else if (ext === 'csv') { typeBadge = 'csv'; typeLabel = 'CSV'; }

        const size = f.size > 1048576
            ? (f.size / 1048576).toFixed(1) + ' MB'
            : (f.size / 1024).toFixed(0) + ' KB';

        return `<div class="doc-item">
            <span class="doc-type-badge ${typeBadge}">${typeLabel}</span>
            <div class="doc-info">
                <div class="doc-name">${f.name}</div>
                <div class="doc-meta">${size}</div>
            </div>
            <span class="doc-status pending">Pending</span>
            <button class="btn btn-danger btn-sm" onclick="removeFromQueue(${i})">✕</button>
        </div>`;
    }).join('');
}

// ─── Run Ingestion Pipeline ─────────────────────────────────────
async function runIngestion() {
    if (!STATE.currentApp) { showToast('⚠️ Create an application first'); return; }
    if (STATE.uploadedFiles.length === 0) { showToast('⚠️ Upload files first'); return; }

    const btn = document.getElementById('btnRunIngestion');
    btn.disabled = true;
    btn.textContent = '⏳ Uploading...';

    // Upload files first
    const formData = new FormData();
    STATE.uploadedFiles.forEach(f => formData.append('files', f));

    try {
        const uploadRes = await fetch(`/api/upload/${STATE.currentApp.id}`, {
            method: 'POST',
            body: formData
        });
        const uploadData = await uploadRes.json();
        if (uploadData.error) { showToast('❌ ' + uploadData.error); btn.disabled = false; btn.textContent = '✨ Run AI Ingestion'; return; }

        showToast(`✅ ${uploadData.count} files uploaded. Starting pipeline...`);
        btn.textContent = '⏳ Processing...';

        // Update sidebar status
        document.getElementById('activeAppStatus').innerHTML = '<span class="status-dot processing"></span> Processing';

        // Reset layer states
        STATE.layersDone.clear();
        for (let i = 2; i <= 7; i++) {
            const el = document.getElementById('layerStatus' + i);
            if (el) el.innerHTML = '';
            const nav = document.querySelector(`.nav-item[data-layer="${i}"]`);
            if (nav) { nav.classList.add('disabled'); nav.classList.remove('completed'); }
        }

        // Initialize pipeline status list
        updatePipelineStatusList();

        // Trigger pipeline via WebSocket
        STATE.socket.emit('run_pipeline', { app_id: STATE.currentApp.id });

    } catch (e) {
        showToast('❌ Upload failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = '✨ Run AI Ingestion';
    }
}

// ─── Load Application Data ──────────────────────────────────────
async function loadApplicationData(appId) {
    if (!appId) return;
    try {
        const res = await fetch(`/api/applications/${appId}`);
        const data = await res.json();
        if (data.error) return;

        STATE.currentApp = data;

        // Populate Financial Analysis if layer2_output exists
        if (data.layer2_output) {
            populateFinancialView(data.layer2_output);
        }
    } catch (e) {
        console.error('Failed to load application data', e);
    }
}

function populateFinancialView(output) {
    const extracted = output.extracted || {};
    const tbody = document.getElementById('financialTableBody');
    if (!tbody) return;

    let rows = '';
    let fieldCount = 0;
    for (const [section, fields] of Object.entries(extracted)) {
        for (const [key, data] of Object.entries(fields)) {
            if (!data || typeof data !== 'object') continue;
            const val = data.value !== null && data.value !== undefined ? data.value : '—';
            const conf = data.confidence !== undefined ? (data.confidence * 100).toFixed(0) + '%' : '—';
            const method = data.extraction_method || '—';
            rows += `<tr>
                <td><strong>${key.replace(/_/g, ' ')}</strong></td>
                <td>${typeof val === 'object' ? JSON.stringify(val).substring(0, 60) : val}</td>
                <td>${conf}</td>
                <td>${method}</td>
            </tr>`;
            fieldCount++;
        }
    }

    if (rows) {
        tbody.innerHTML = rows;
    }
}

// ─── History ────────────────────────────────────────────────────
async function loadHistory() {
    try {
        const res = await fetch('/api/applications/history');
        const apps = await res.json();
        const tbody = document.getElementById('historyTableBody');
        if (!tbody) return;

        if (apps.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No completed applications</td></tr>';
            return;
        }

        tbody.innerHTML = apps.map(a => {
            const score = a.risk_score !== null ? a.risk_score : '—';
            const decision = a.decision || 'Pending';
            const date = a.completed_at ? new Date(a.completed_at).toLocaleDateString() : '—';
            const statusClass = a.status === 'completed' ? 'done' : 'pending';
            return `<tr>
                <td><strong>${a.case_id}</strong></td>
                <td>${a.company_name}</td>
                <td><span class="doc-status ${statusClass}">${a.status}</span></td>
                <td>${score}</td>
                <td>${decision}</td>
                <td>${date}</td>
                <td><button class="btn btn-outline btn-sm" onclick="viewApplication(${a.id})">View</button></td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load history', e);
    }
}

async function viewApplication(appId) {
    await loadApplicationData(appId);
    // Enable all layers for viewing
    for (let i = 1; i <= 7; i++) enableLayerNav(i);
    STATE.layersDone = new Set([1, 2, 3, 4, 5, 6, 7]);
    updatePipelineStatusList();

    document.getElementById('activeAppInfo').style.display = '';
    document.getElementById('activeAppName').textContent = STATE.currentApp.company_name;
    document.getElementById('activeAppId').textContent = STATE.currentApp.case_id;
    document.getElementById('activeAppStatus').innerHTML = '<span class="status-dot done"></span> Processing Complete';
    document.getElementById('activeAppStatus').style.color = 'var(--accent-green)';

    showSection('financial');
}

// ─── User Management ────────────────────────────────────────────
async function loadUsers() {
    try {
        const res = await fetch('/api/users/list');
        const users = await res.json();
        const tbody = document.getElementById('usersTableBody');

        if (!Array.isArray(users) || users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No users found</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(u => {
            const date = u.created_at ? new Date(u.created_at).toLocaleDateString() : '—';
            return `<tr>
                <td><strong>${u.username}</strong></td>
                <td>${u.full_name}</td>
                <td><span class="role-perm-tag">${u.role}</span></td>
                <td>${date}</td>
                <td>
                    <button class="btn btn-outline btn-sm" onclick="showEditUserModal(${u.id}, '${u.full_name}', '${u.role}')" data-perm="EDIT_USERS">Edit</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id}, '${u.username}')" data-perm="EDIT_USERS">Delete</button>
                </td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load users', e);
    }
}

function showCreateUserModal() {
    document.getElementById('modalCreateUserHeader').textContent = 'Create New User';
    document.getElementById('inputUserId').value = '';
    document.getElementById('inputUserFullName').value = '';
    document.getElementById('inputUserUsername').value = '';
    document.getElementById('inputUserPassword').value = '';
    document.getElementById('btnSubmitUser').textContent = 'Create User';
    // Remove disabled if it was an edit
    document.getElementById('inputUserUsername').disabled = false;
    document.getElementById('inputUserPasswordGroup').style.display = 'block';

    loadAssignableRoles('inputUserRole');
    document.getElementById('modalCreateUser').style.display = 'flex';
}

function showEditUserModal(id, fullName, role) {
    document.getElementById('modalCreateUserHeader').textContent = 'Edit User';
    document.getElementById('inputUserId').value = id;
    document.getElementById('inputUserFullName').value = fullName;
    document.getElementById('inputUserUsername').value = '---'; // username disabled on edit
    document.getElementById('inputUserUsername').disabled = true;
    document.getElementById('inputUserPasswordGroup').style.display = 'none';
    document.getElementById('btnSubmitUser').textContent = 'Save Changes';

    // Load roles and pre-select
    loadAssignableRoles('inputUserRole').then(() => {
        document.getElementById('inputUserRole').value = role;
    });
    document.getElementById('modalCreateUser').style.display = 'flex';
}

async function loadAssignableRoles(selectId) {
    try {
        const res = await fetch('/api/roles/list?assignable=true');
        const roles = await res.json();
        const select = document.getElementById(selectId);
        if (roles.length > 0) {
            select.innerHTML = roles.map(r => `<option value="${r.name}">${r.name}</option>`).join('');
        } else {
            select.innerHTML = '<option value="">No roles available</option>';
        }
    } catch (e) { console.error('Failed to load roles', e); }
}

async function createUser() {
    const userId = document.getElementById('inputUserId').value;
    const isEdit = !!userId;

    const data = {
        full_name: document.getElementById('inputUserFullName').value.trim(),
        role: document.getElementById('inputUserRole').value
    };

    if (!isEdit) {
        data.username = document.getElementById('inputUserUsername').value.trim();
        data.password = document.getElementById('inputUserPassword').value;
    }

    if (!data.full_name || !data.role || (!isEdit && (!data.username || !data.password))) {
        showToast('⚠️ Required fields are missing');
        return;
    }

    try {
        if (isEdit) {
            data.id = userId;
            const res = await fetch('/api/users/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();
            if (result.error) { showToast('❌ ' + result.error); return; }
            showToast('✅ User updated');
        } else {
            const res = await fetch('/api/users/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();
            if (result.error) { showToast('❌ ' + result.error); return; }
            showToast('✅ User created');
        }

        closeModal('modalCreateUser');
        loadUsers();
    } catch (e) {
        showToast('❌ Failed to save user');
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`Delete user "${username}"?`)) return;
    try {
        const res = await fetch('/api/users/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });
        const result = await res.json();
        if (result.error) { showToast('❌ ' + result.error); return; }
        showToast('✅ User deleted');
        loadUsers();
    } catch (e) {
        showToast('❌ Error');
    }
}

// ─── Role Management ────────────────────────────────────────────
async function loadRoles() {
    try {
        const res = await fetch('/api/roles/list');
        const roles = await res.json();
        const container = document.getElementById('roleList');

        container.innerHTML = roles.map((r, i) => {
            const perms = Array.isArray(r.default_permissions) ? r.default_permissions : [];
            const permTags = perms.slice(0, 4).map(p => `<span class="role-perm-tag">${p}</span>`).join('');
            const moreTag = perms.length > 4 ? `<span class="role-perm-tag">+${perms.length - 4}</span>` : '';
            return `<div class="role-item" data-role="${r.name}" draggable="true"
                         ondragstart="dragRole(event)" ondragover="event.preventDefault()" ondrop="dropRole(event)">
                <span class="role-drag">☰</span>
                <div class="role-rank">${i + 1}</div>
                <div class="role-info">
                    <div class="role-name">${r.name}</div>
                    <div class="role-desc">${r.description || ''}</div>
                </div>
                <div class="role-perms">${permTags}${moreTag}</div>
                ${r.name !== 'SUPER_ADMIN' ? `
                    <button class="btn btn-outline btn-sm" onclick='showEditRoleModal(${JSON.stringify(r).replace(/'/g, "&#39;")})' data-perm="EDIT_ROLES">Edit</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteRole('${r.name}')" data-perm="EDIT_ROLES">Delete</button>
                ` : ''}
            </div>`;
        }).join('');
        // Apply gating within dynamic content
        applyPermissionGating(STATE.user ? STATE.user.permissions : []);
    } catch (e) {
        console.error('Failed to load roles', e);
    }
}

// Drag & drop role reordering
let draggedRole = null;
function dragRole(e) {
    draggedRole = e.target.closest('.role-item');
    draggedRole.classList.add('dragging');
}
function dropRole(e) {
    e.preventDefault();
    const target = e.target.closest('.role-item');
    if (target && draggedRole && target !== draggedRole) {
        const container = document.getElementById('roleList');
        const items = Array.from(container.children);
        const dragIdx = items.indexOf(draggedRole);
        const dropIdx = items.indexOf(target);
        if (dragIdx < dropIdx) {
            target.after(draggedRole);
        } else {
            target.before(draggedRole);
        }
        saveRoleOrder();
    }
    if (draggedRole) draggedRole.classList.remove('dragging');
    draggedRole = null;
}

async function saveRoleOrder() {
    const items = document.querySelectorAll('.role-item');
    const roles = Array.from(items).map(el => el.dataset.role);
    try {
        await fetch('/api/roles/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roles })
        });
        showToast('✅ Role hierarchy updated');
    } catch (e) {
        showToast('❌ Failed to save order');
    }
}

// Pre-load roles globally into a var to simplify edit modal logic
let ALL_PERMS = [];
async function preloadPerms() {
    try {
        const res = await fetch('/api/roles/permissions');
        ALL_PERMS = await res.json();
    } catch (e) { console.error('Failed to preload permissions'); }
}
preloadPerms();

async function showCreateRoleModal() {
    document.getElementById('modalCreateRoleHeader').textContent = 'Create New Role';
    document.getElementById('inputRoleName').value = '';
    document.getElementById('inputRoleName').disabled = false;
    document.getElementById('inputRoleDesc').value = '';
    document.getElementById('btnSubmitRole').textContent = 'Create Role';
    document.getElementById('isRoleEdit').value = 'false';

    const grid = document.getElementById('permGrid');
    grid.innerHTML = ALL_PERMS.map(p =>
        `<label class="perm-checkbox">
            <input type="checkbox" value="${p}"> ${p}
        </label>`
    ).join('');
    document.getElementById('modalCreateRole').style.display = 'flex';
}

function showEditRoleModal(roleObj) {
    document.getElementById('modalCreateRoleHeader').textContent = 'Edit Role: ' + roleObj.name;
    document.getElementById('inputRoleName').value = roleObj.name;
    document.getElementById('inputRoleName').disabled = true; // cannot edit role name!
    document.getElementById('inputRoleDesc').value = roleObj.description || '';
    document.getElementById('btnSubmitRole').textContent = 'Save Changes';
    document.getElementById('isRoleEdit').value = 'true';

    const grid = document.getElementById('permGrid');
    const existingPerms = Array.isArray(roleObj.default_permissions) ? roleObj.default_permissions : [];

    grid.innerHTML = ALL_PERMS.map(p => {
        const checked = existingPerms.includes(p) ? 'checked' : '';
        return `<label class="perm-checkbox">
            <input type="checkbox" value="${p}" ${checked}> ${p}
        </label>`;
    }).join('');

    document.getElementById('modalCreateRole').style.display = 'flex';
}

async function createRole() {
    const isEdit = document.getElementById('isRoleEdit').value === 'true';
    const name = document.getElementById('inputRoleName').value.trim();
    const desc = document.getElementById('inputRoleDesc').value.trim();
    const perms = Array.from(document.querySelectorAll('#permGrid input:checked')).map(el => el.value);

    if (!name) { showToast('⚠️ Enter a role name'); return; }

    try {
        if (isEdit) {
            const res = await fetch('/api/roles/update_details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: name, description: desc, permissions: perms })
            });
            const result = await res.json();
            if (result.error) { showToast('❌ ' + result.error); return; }
            showToast('✅ Role updated');
        } else {
            const res = await fetch('/api/roles/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description: desc, permissions: perms, allowed_child_roles: [] })
            });
            const result = await res.json();
            if (result.error) { showToast('❌ ' + result.error); return; }
            showToast('✅ Role created');
        }

        closeModal('modalCreateRole');
        loadRoles();
    } catch (e) {
        showToast('❌ Failed to save role');
    }
}

async function deleteRole(roleName) {
    if (!confirm(`Delete role "${roleName}"?`)) return;
    await _deleteRoleWithReassign(roleName, null);
}

async function _deleteRoleWithReassign(roleName, reassignTo) {
    try {
        const res = await fetch('/api/roles/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: roleName, reassign_to: reassignTo })
        });
        const result = await res.json();

        if (res.status === 409 && result.requires_reassign) {
            // Users exist on this role — ask for a reassignment target
            const rolesRes = await fetch('/api/roles/list');
            const allRoles = await rolesRes.json();
            const choices = allRoles.filter(r => r.name !== roleName && r.name !== 'SUPER_ADMIN');

            if (choices.length === 0) {
                showToast('❌ Cannot delete: no other roles to reassign users to');
                return;
            }

            const optionsList = choices.map(r => r.name).join('\n• ');
            const chosen = prompt(
                `${result.error}\n\nChoose a role to reassign them to:\n• ${optionsList}\n\nType the role name exactly:`
            );
            if (!chosen) return; // cancelled
            const valid = choices.find(r => r.name === chosen.trim().toUpperCase());
            if (!valid) {
                showToast('❌ Invalid role name entered');
                return;
            }
            await _deleteRoleWithReassign(roleName, valid.name);
            return;
        }

        if (result.error) { showToast('❌ ' + result.error); return; }
        showToast('✅ Role deleted');
        loadRoles();
    } catch (e) {
        showToast('❌ Error deleting role');
    }
}


// ─── Utility Functions ──────────────────────────────────────────
function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

function toggleUserMenu() {
    const menu = document.getElementById('userMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

// Close menus on click outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.user-avatar') && !e.target.closest('.user-menu')) {
        document.getElementById('userMenu').style.display = 'none';
    }
});

// Toast notification
function showToast(msg) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
