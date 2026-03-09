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
        updatePipelineBar(data.layer, data.pct || 0, false, data.detail || '');
    });

    STATE.socket.on('layer_complete', (data) => {
        console.log('Layer complete:', data);
        STATE.layersDone.add(data.layer);
        updateLayerStatus(data.layer, 'done');
        // Enable this layer's section in the sidebar
        enableLayerNav(data.layer);
        updatePipelineBar(data.layer, 100, true, '');

        // Fetch partial data so UI updates mid-pipeline
        if (STATE.currentApp && STATE.currentApp.id) {
            loadApplicationData(STATE.currentApp.id);
        }

        // Layer 6 CAM complete — auto-populate CAM view
        if (data.layer === 6 && data.audit) {
            populateCAMView({
                cam_hash: data.cam_hash || '',
                sections: data.sections || 13,
                timestamp: new Date().toISOString(),
                audit: data.audit || {},
                digital_signature: null,
            });
            // Auto-navigate to CAM tab after brief delay
            setTimeout(() => showSection('cam'), 2000);
        }

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
        // Hide progress banner
        setTimeout(() => {
            const banner = document.getElementById('pipelineProgressBanner');
            if (banner) banner.style.display = 'none';
        }, 2500);
    });

    STATE.socket.on('pipeline_error', (data) => {
        console.error('Pipeline error:', data);
        showToast('❌ Error: ' + data.error);
        const banner = document.getElementById('pipelineProgressBanner');
        const label = document.getElementById('pipelineProgressLabel');
        if (banner) banner.style.display = 'block';
        if (label) label.textContent = `❌ Error in pipeline: ${data.error?.substring(0, 60) || ''}`;
    });

    // ─── HITL: Document Review ──────────────────────────────────
    STATE.socket.on('hitl_review_needed', (data) => {
        console.log('HITL review needed:', data);
        STATE._hitlAppId = data.app_id;

        if (data.layer === "6_decision") {
            STATE._pendingHitlDecisionData = data;
            const btn = document.getElementById('btnOpenHitlModal');
            if (btn) btn.style.display = 'block';
            showToast('⚖️ Action Required: Review & Override Final AI Decision');
        } else {
            showHitlReviewModal(data);
        }
    });

    STATE.socket.on('pipeline_resumed', (data) => {
        console.log('Pipeline resumed:', data);
        closeModal('modalHitlReview');
        showToast('▶ Pipeline resumed — processing Layer 2...');
    });

    // ─── Layer 4 HITL Events ─────────────────────────────────────
    STATE.socket.on('layer4_hitl_forensics', (data) => {
        console.log('L4 HITL-1 Forensics:', data);
        STATE._l4AppId = data.app_id;
        STATE._l4Hitl1Data = data;
        renderL4Hitl1Modal(data);
        document.getElementById('modalL4Hitl1').style.display = 'flex';
        if (window.lucide) lucide.createIcons();
        showToast('⏸ Pipeline paused — please review forensic flags', 'warning');
    });

    STATE.socket.on('layer4_hitl_research', (data) => {
        console.log('L4 HITL-2 Research:', data);
        STATE._l4AppId = data.app_id;
        STATE._l4Hitl2Data = data;
        renderL4Hitl2Modal(data, 'adverse_media');
        document.getElementById('modalL4Hitl2').style.display = 'flex';
        if (window.lucide) lucide.createIcons();
        showToast('⏸ Pipeline paused — please review research findings', 'warning');
    });

    STATE.socket.on('layer4_hitl_features', (data) => {
        console.log('L4 HITL-3 Features:', data);
        STATE._l4AppId = data.app_id;
        STATE._l4Hitl3Data = data;
        renderL4Hitl3Modal(data);
        document.getElementById('modalL4Hitl3').style.display = 'flex';
        if (window.lucide) lucide.createIcons();
        showToast('⏸ Pipeline paused — review feature vector before ML scoring', 'warning');
    });

    // ─── Layer 5 HITL Event ──────────────────────────────────────
    STATE.socket.on('layer5_hitl_reject', (data) => {
        console.log('L5 HITL Reject:', data);
        STATE._l5AppId = data.app_id;
        const rules = data.hard_rules || {};

        document.getElementById('hitl5RejectRuleTitle').textContent = rules.gate === 'HARD_REJECT' ? 'Auto-Reject Triggered' : 'Hard Rule Violation';
        document.getElementById('hitl5RejectReason').textContent = rules.rejection_reason || 'Unknown policy violation';
        document.getElementById('hitl5RejectOverrideReason').value = '';

        document.getElementById('modalL5HitlReject').style.display = 'flex';
        if (window.lucide) lucide.createIcons();
        showToast('⏸ Pipeline paused — Layer 5 Hard Reject requires officer action', 'error');
    });
}

// ─── Pipeline Progress Banner ──────────────────────────────────
const PIPELINE_LAYER_NAMES = {
    2: '📑 Financial Extraction',
    3: '🧹 Data Cleaning',
    4: '🔍 Forensics & Research',
    5: '🎯 AI Risk Scoring',
    6: '⚖️ HITL Decision Review',
    7: '📄 CAM Report Generation',
};

function updatePipelineBar(layer, layerPct, isDone, detail) {
    const banner = document.getElementById('pipelineProgressBanner');
    const bar = document.getElementById('pipelineProgressBar');
    const label = document.getElementById('pipelineProgressLabel');
    const pctLabel = document.getElementById('pipelineProgressPct');
    if (!banner || !bar) return;
    banner.style.display = '';

    const TOTAL = 6;
    const idx = Math.max(0, layer - 2);
    const slot = 100 / TOTAL;
    const pct = Math.min(100, idx * slot + (layerPct / 100) * slot);

    bar.style.width = pct.toFixed(1) + '%';
    pctLabel.textContent = Math.round(pct) + '%';

    if (isDone && layer === 7) {
        label.textContent = '✅ Pipeline Complete!';
        bar.style.background = 'linear-gradient(90deg,#10b981,#34d399)';
    } else {
        const name = PIPELINE_LAYER_NAMES[layer] || `Layer ${layer}`;
        label.textContent = detail ? `${name} — ${detail}` : name;
    }

    for (let l = 2; l <= 7; l++) {
        const pill = document.getElementById('pp' + l);
        if (!pill) continue;
        if (l < layer || (l === layer && isDone)) {
            pill.classList.remove('active'); pill.classList.add('done');
        } else if (l === layer && !isDone) {
            pill.classList.add('active'); pill.classList.remove('done');
        } else {
            pill.classList.remove('active', 'done');
        }
    }
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

    // Close HITL modal first
    closeModal('modalHitlReview');

    // Show officer notes modal — user can submit or skip
    const officerNotes = await showOfficerNotesModal();

    document.getElementById('btnConfirmHitl').disabled = true;
    document.getElementById('btnConfirmHitl').textContent = 'Processing...';

    try {
        const res = await fetch(`/api/applications/${appId}/confirm_docs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ documents: docs, officer_notes: officerNotes })
        });
        const result = await res.json();
        if (result.error) {
            showToast('❌ ' + result.error);
            document.getElementById('btnConfirmHitl').disabled = false;
            document.getElementById('btnConfirmHitl').textContent = 'Confirm & Continue Pipeline';
            return;
        }
        showToast('✅ Documents confirmed — pipeline resuming' + (officerNotes ? ' (with officer notes)' : ''));
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
        roles: ['Role Management', 'Configure roles and permissions'],
        governance: ['Governance & Compliance', 'RBI MRM — Model Health, Drift, SMA, CRILC']
    };
    const [title, subtitle] = titles[section] || ['Dashboard', ''];
    document.getElementById('pageTitle').textContent = title;
    document.getElementById('pageSubtitle').textContent = subtitle;

    // Load section-specific data
    if (section === 'history') loadHistory();
    if (section === 'users') loadUsers();
    if (section === 'roles') loadRoles();
    if (section === 'cam') loadCAMData();
    if (section === 'governance') loadGovernance();
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

        // Populate Web Research & Anomaly Detection if layer4_output exists
        if (data.layer4_output) {
            populateResearchView(data.layer4_output);
            populateAnomalyView(data.layer4_output);
        }

        // Populate Risk Scoring (Layer 5) if available
        if (data.layer5_output) {
            populateRiskScoringView(data.layer5_output);
        }
    } catch (e) {
        console.error('Failed to load application data', e);
    }
}

function populateFinancialView(output) {
    const extracted = output.extracted || {};
    // Support both flat financial_data and old SRC_* sections
    const data = extracted.financial_data || extracted;
    const tbody = document.getElementById('financialTableBody');
    if (!tbody) return;

    // Helper: get value from either wrapped {value, confidence} or raw value
    function getVal(v) {
        if (v && typeof v === 'object' && 'value' in v) return v.value;
        return v;
    }
    function getConf(v) {
        if (v && typeof v === 'object' && 'confidence' in v) return (v.confidence * 100).toFixed(0) + '%';
        return v !== null && v !== undefined && v !== '' ? '90%' : '—';
    }
    function getMethod(v) {
        if (v && typeof v === 'object' && 'extraction_method' in v) return v.extraction_method;
        return v !== null && v !== undefined && v !== '' ? 'llm' : '—';
    }
    function fmt(val) {
        if (val === null || val === undefined || val === '') return '—';
        if (Array.isArray(val)) return val.length > 0 ? `[${val.length} items]` : '—';
        if (typeof val === 'object') return JSON.stringify(val).substring(0, 80);
        if (typeof val === 'number') return val.toLocaleString('en-IN');
        return String(val);
    }
    function fmtCurrency(val) {
        if (val === null || val === undefined) return '—';
        const n = Number(val);
        if (isNaN(n)) return '—';
        if (n >= 10000000) return '₹' + (n / 10000000).toFixed(2) + ' Cr';
        if (n >= 100000) return '₹' + (n / 100000).toFixed(2) + ' L';
        return '₹' + n.toLocaleString('en-IN');
    }

    // ─── Populate KPI Cards ─────────────────────────────────────
    const revenue = getVal(data.total_revenue) || getVal(data.revenue_from_operations) || getVal(data.gross_receipts);
    const pat = getVal(data.profit_after_tax) || getVal(data.net_profit_from_business);
    const totalDebt = getVal(data.total_debt) || 0;
    const netWorth = getVal(data.net_worth) || 0;
    const curAssets = getVal(data.current_assets) || 0;
    const curLiab = getVal(data.current_liabilities) || 0;

    const elRev = document.getElementById('kpiRevenue');
    const elPat = document.getElementById('kpiPat');
    const elDe = document.getElementById('kpiDe');
    const elCr = document.getElementById('kpiCr');

    if (elRev) elRev.textContent = fmtCurrency(revenue);
    if (elPat) elPat.textContent = fmtCurrency(pat);
    if (elDe) elDe.textContent = netWorth ? (totalDebt / netWorth).toFixed(2) : '—';
    if (elCr) elCr.textContent = curLiab ? (curAssets / curLiab).toFixed(2) : '—';

    // ─── Populate Financial Summary Table ────────────────────────
    // Skip list/array fields for the main table (show them separately if needed)
    const skipKeys = ['b2b_invoices', 'export_invoices', 'large_cash_deposits', 'large_cash_withdrawals'];
    let rows = '';
    for (const [key, raw] of Object.entries(data)) {
        if (skipKeys.includes(key)) continue;
        const val = getVal(raw);
        const conf = getConf(raw);
        const method = getMethod(raw);
        const displayVal = fmt(val);
        if (displayVal === '—') continue; // Skip empty fields
        rows += `<tr>
            <td><strong>${key.replace(/_/g, ' ')}</strong></td>
            <td>${displayVal}</td>
            <td>${conf}</td>
            <td>${method}</td>
        </tr>`;
    }

    if (rows) {
        tbody.innerHTML = rows;
    } else {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No data extracted yet</td></tr>';
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

        const newBody = apps.map(a => {
            const score = a.risk_score !== null ? a.risk_score : '—';
            const decision = a.decision || 'Pending';

            // Format for display
            let dateObj = a.completed_at ? new Date(a.completed_at) : new Date(a.created_at);
            const dateStr = dateObj.toLocaleDateString();

            // Format for DataTables sorting & filtering (YYYY-MM-DD)
            const isoDate = dateObj.toISOString().split('T')[0];

            let statusText = a.status;
            let statusClass = 'pending';

            if (a.status === 'completed') {
                statusClass = 'done';
                statusText = 'Completed';
            } else if (a.status === 'processing') {
                statusClass = 'processing';
                statusText = 'Generating CAM';
            }

            return `<tr>
                <td><strong>${a.case_id}</strong></td>
                <td>${a.company_name}</td>
                <td><span class="doc-status ${statusClass}">${statusText}</span></td>
                <td>${score}</td>
                <td>${decision}</td>
                <td data-sort="${isoDate}">${dateStr}</td>
                <td><button class="btn btn-outline btn-sm" onclick="viewApplication(${a.id})">View</button></td>
            </tr>`;
        }).join('');

        tbody.innerHTML = newBody;

        // Initialize DataTables
        if ($.fn.DataTable.isDataTable('#historyTable')) {
            $('#historyTable').DataTable().destroy();
        }

        $('#historyTable').DataTable({
            "order": [[5, "desc"]], // Sort by date descending
            "pageLength": 10,
            "language": {
                "search": "",
                "searchPlaceholder": "Search history..."
            }
        });

    } catch (e) {
        console.error('Failed to load history', e);
    }
}

// Custom Date Range Filtering for DataTables
$.fn.dataTable.ext.search.push(
    function (settings, data, dataIndex) {
        if (settings.nTable.id !== 'historyTable') return true;

        var min = $('#historyStartDate').val();
        var max = $('#historyEndDate').val();

        // Date is in column 5. data-sort attribute isn't directly exposed in data[], 
        // but we can parse the visible date or get raw data if needed. 
        // Here we'll read the data-sort attribute from the node
        var dateNode = $(settings.aoData[dataIndex].nTr).find('td:eq(5)');
        var dateStr = dateNode.attr('data-sort');

        if (!dateStr) return true;

        if (
            (min === "" && max === "") ||
            (min === "" && dateStr <= max) ||
            (min <= dateStr && max === "") ||
            (min <= dateStr && dateStr <= max)
        ) {
            return true;
        }
        return false;
    }
);

// Event listeners for date range filter
$(document).ready(function () {
    $('#historyStartDate, #historyEndDate').on('change', function () {
        if ($.fn.DataTable.isDataTable('#historyTable')) {
            $('#historyTable').DataTable().draw();
        }
    });
});

function clearHistoryFilters() {
    $('#historyStartDate').val('');
    $('#historyEndDate').val('');
    if ($.fn.DataTable.isDataTable('#historyTable')) {
        $('#historyTable').DataTable().search('').columns().search('');
        $('#historyTable').DataTable().draw();
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


// ─── LAYER 4: Web Research Rendering ─────────────────────────────
function populateResearchView(l4) {
    const research = l4.research_findings || {};
    const el = document.getElementById('researchSummaryContent');
    if (!el) return;

    // Summary card
    const report = l4.forensics_report || {};
    el.innerHTML = `
        <div style="display:flex;gap:1.5rem;flex-wrap:wrap;align-items:center;">
            <div style="text-align:center;padding:0.5rem 1.5rem;background:rgba(239,68,68,0.15);border-radius:8px;">
                <div style="font-size:1.8rem;font-weight:700;color:#ef4444;">${report.red_flag_count || 0}</div>
                <div style="font-size:0.75rem;color:#ef4444;">RED Alerts</div>
            </div>
            <div style="text-align:center;padding:0.5rem 1.5rem;background:rgba(245,158,11,0.15);border-radius:8px;">
                <div style="font-size:1.8rem;font-weight:700;color:#f59e0b;">${report.amber_flag_count || 0}</div>
                <div style="font-size:0.75rem;color:#f59e0b;">AMBER Alerts</div>
            </div>
            <div style="text-align:center;padding:0.5rem 1.5rem;background:rgba(16,185,129,0.15);border-radius:8px;">
                <div style="font-size:1.8rem;font-weight:700;color:#10b981;">${report.green_flag_count || 0}</div>
                <div style="font-size:0.75rem;color:#10b981;">GREEN Signals</div>
            </div>
            <div style="flex:1;text-align:right;font-size:0.85rem;color:var(--text-secondary);">
                Overall fraud risk: <strong style="color:${report.overall_fraud_risk === 'RED' ? '#ef4444' : report.overall_fraud_risk === 'AMBER' ? '#f59e0b' : '#10b981'}">${report.overall_fraud_risk || '—'}</strong>
                 | Score penalty: <strong>${report.total_score_penalty || 0}</strong>
            </div>
        </div>`;

    // C1: Adverse Media
    _renderResearchCard('researchAdverseCard', 'adverseMediaSummary', 'adverseMediaSnippets', research.adverse_media);

    // C2: Litigation
    _renderLitigationCard(research.litigation);

    // C3: Sector Risk
    _renderSectorCard(research.sector_risk);

    // D1-D2: MCA
    _renderMcaCard(research.mca_checks);

    // E1: CIBIL
    _renderCibilCard(research.cibil);

    // Raw snippets
    _renderRawSnippets(research);
}

function _severityBadge(severity) {
    const colors = { RED: '#ef4444', AMBER: '#f59e0b', GREEN: '#10b981', INFO: '#64748b' };
    const color = colors[severity] || '#64748b';
    return `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:600;background:${color}22;color:${color};border:1px solid ${color}44;">${severity}</span>`;
}

function _renderResearchCard(cardId, summaryId, snippetsId, data) {
    if (!data) return;
    document.getElementById(cardId).style.display = '';
    const summary = document.getElementById(summaryId);
    const snippets = document.getElementById(snippetsId);

    const flag = data.negative_news_flag ? '⚠️ Negative media found' : '✅ No adverse media detected';
    const sentiment = data.sentiment_score !== undefined ? `Sentiment: ${data.sentiment_score > 0 ? '🟢' : data.sentiment_score < 0 ? '🔴' : '🟡'} ${data.sentiment_score}` : '';

    summary.innerHTML = `
        <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
            <div style="font-weight:600;">${flag}</div>
            <div style="font-size:0.85rem;color:var(--text-secondary);">${sentiment}</div>
            ${data.risk_category ? `<div>Category: <strong>${data.risk_category}</strong></div>` : ''}
        </div>
        ${data.summary ? `<p style="margin-top:0.5rem;color:var(--text-secondary);font-size:0.9rem;">${data.summary}</p>` : ''}
        ${(data.alerts || []).map(a => `<div style="margin-top:0.3rem;">${_severityBadge(a.severity)} ${a.description}</div>`).join('')}`;

    const rawSnippets = data.raw_snippets || data.adverse_snippets || [];
    if (rawSnippets.length) {
        snippets.innerHTML = `<div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem;">Sources (${rawSnippets.length} results):</div>` +
            rawSnippets.map(s => `<div style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:0.6rem;margin-bottom:0.5rem;">
                <a href="${s.url}" target="_blank" style="color:var(--accent);font-size:0.85rem;text-decoration:none;">${s.title || s.url}</a>
                <p style="font-size:0.8rem;color:var(--text-secondary);margin-top:0.3rem;">${(s.content || s.concern || '').substring(0, 150)}...</p>
            </div>`).join('');
    }
}

function _renderLitigationCard(data) {
    if (!data) return;
    document.getElementById('researchLitigationCard').style.display = '';
    const summary = document.getElementById('litigationSummary');
    const cases = document.getElementById('litigationCases');

    summary.innerHTML = `
        <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
            <div>Active cases: <strong>${data.litigation_count || 0}</strong></div>
            <div>Risk: <strong style="color:${data.litigation_risk === 'High' ? '#ef4444' : data.litigation_risk === 'Moderate' ? '#f59e0b' : '#10b981'}">${data.litigation_risk || 'Low'}</strong></div>
            ${data.total_exposure_lakhs ? `<div>Exposure: <strong>₹${data.total_exposure_lakhs}L</strong></div>` : ''}
        </div>
        ${data.summary ? `<p style="margin-top:0.5rem;color:var(--text-secondary);font-size:0.9rem;">${data.summary}</p>` : ''}
        ${(data.alerts || []).map(a => `<div style="margin-top:0.3rem;">${_severityBadge(a.severity)} ${a.description}</div>`).join('')}`;

    const caseList = data.cases || [];
    if (caseList.length) {
        cases.innerHTML = `<table class="data-table"><thead><tr><th>Type</th><th>Severity</th><th>Status</th><th>Summary</th></tr></thead><tbody>` +
            caseList.map(c => `<tr><td>${c.case_type || '—'}</td><td>${_severityBadge(c.severity || 'Low')}</td><td>${c.case_status || '—'}</td><td>${c.summary || '—'}</td></tr>`).join('') +
            `</tbody></table>`;
    }
}

function _renderSectorCard(data) {
    if (!data) return;
    document.getElementById('researchSectorCard').style.display = '';
    document.getElementById('sectorRiskSummary').innerHTML = `
        <div style="display:flex;gap:1rem;align-items:center;">
            <div>Sector: <strong>${data.sector || '—'}</strong></div>
            <div>Risk Score: <strong style="color:${data.sector_risk_score > 0.7 ? '#ef4444' : data.sector_risk_score > 0.4 ? '#f59e0b' : '#10b981'}">${(data.sector_risk_score || 0).toFixed(2)}</strong></div>
            ${data.rbi_sector_flag ? '<div style="color:#ef4444;font-weight:600;">⚠ RBI Sector Caution</div>' : ''}
        </div>
        ${data.summary ? `<p style="margin-top:0.5rem;color:var(--text-secondary);font-size:0.9rem;">${data.summary}</p>` : ''}`;

    document.getElementById('sectorHeadwinds').innerHTML = `<div style="background:rgba(239,68,68,0.1);border-radius:8px;padding:1rem;"><strong style="color:#ef4444;">⬇ Headwinds</strong><ul style="margin:0.5rem 0 0 1rem;font-size:0.85rem;">${(data.headwinds || []).map(h => `<li>${h}</li>`).join('')}</ul></div>`;
    document.getElementById('sectorTailwinds').innerHTML = `<div style="background:rgba(16,185,129,0.1);border-radius:8px;padding:1rem;"><strong style="color:#10b981;">⬆ Tailwinds</strong><ul style="margin:0.5rem 0 0 1rem;font-size:0.85rem;">${(data.tailwinds || []).map(t => `<li>${t}</li>`).join('')}</ul></div>`;
}

function _renderMcaCard(data) {
    if (!data) return;
    document.getElementById('researchMcaCard').style.display = '';
    document.getElementById('mcaSummary').innerHTML = `
        <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
            <div>Status: <strong style="color:${data.company_status === 'Active' ? '#10b981' : '#ef4444'}">${data.company_status || 'Unknown'}</strong></div>
            <div>Charges: <strong>${data.mca_charge_count || 0}</strong></div>
            <div>DIN Score: <strong>${data.promoter_din_score || '—'}</strong></div>
        </div>
        ${data.summary ? `<p style="margin-top:0.5rem;color:var(--text-secondary);font-size:0.9rem;">${data.summary}</p>` : ''}
        ${(data.alerts || []).map(a => `<div style="margin-top:0.3rem;">${_severityBadge(a.severity)} ${a.description}</div>`).join('')}`;

    const dirs = data.directors || [];
    if (dirs.length) {
        document.getElementById('mcaDetails').innerHTML = `<table class="data-table"><thead><tr><th>Director</th><th>DIN</th><th>Status</th></tr></thead><tbody>` +
            dirs.map(d => `<tr><td>${d.name || '—'}</td><td>${d.din || '—'}</td><td style="color:${d.status === 'Active' ? '#10b981' : '#ef4444'}">${d.status || '—'}</td></tr>`).join('') +
            `</tbody></table>`;
    }
}

function _renderCibilCard(data) {
    if (!data) return;
    document.getElementById('researchCibilCard').style.display = '';
    document.getElementById('cibilSummary').innerHTML = `
        ${data.simulated ? '<div style="background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.3);border-radius:6px;padding:0.5rem;margin-bottom:0.5rem;font-size:0.8rem;color:#f59e0b;">⚠ SIMULATED — Real CIBIL Commercial requires TransUnion data-sharing agreement</div>' : ''}
        <div style="display:flex;gap:1.5rem;flex-wrap:wrap;">
            <div style="text-align:center;"><div style="font-size:1.5rem;font-weight:700;">${data.cibil_rank || '—'}</div><div style="font-size:0.7rem;color:var(--text-secondary);">Rank</div></div>
            <div style="text-align:center;"><div style="font-size:1.5rem;font-weight:700;">${data.cibil_score || '—'}</div><div style="font-size:0.7rem;color:var(--text-secondary);">Score</div></div>
            <div style="text-align:center;"><div style="font-size:1.5rem;font-weight:700;">${data.total_live_facilities || 0}</div><div style="font-size:0.7rem;color:var(--text-secondary);">Live Facilities</div></div>
            <div style="text-align:center;"><div style="font-size:1.5rem;font-weight:700;color:${data.npa_flag ? '#ef4444' : '#10b981'}">${data.npa_flag ? 'YES' : 'NO'}</div><div style="font-size:0.7rem;color:var(--text-secondary);">NPA</div></div>
            <div style="text-align:center;"><div style="font-size:1.5rem;font-weight:700;">${data.highest_dpd_days || 0}d</div><div style="font-size:0.7rem;color:var(--text-secondary);">Highest DPD</div></div>
            <div style="text-align:center;"><div style="font-size:1.5rem;font-weight:700;">${data.enquiry_count_6m || 0}</div><div style="font-size:0.7rem;color:var(--text-secondary);">Enquiries (6m)</div></div>
        </div>
        ${data.summary ? `<p style="margin-top:0.5rem;color:var(--text-secondary);font-size:0.9rem;">${data.summary}</p>` : ''}`;
}

function _renderRawSnippets(research) {
    let allSnippets = [];
    for (const [key, val] of Object.entries(research)) {
        if (val && val.raw_snippets) {
            allSnippets = allSnippets.concat(val.raw_snippets.map(s => ({ ...s, source: key })));
        }
    }
    if (!allSnippets.length) return;
    document.getElementById('researchRawCard').style.display = '';
    document.getElementById('rawSearchResults').innerHTML = allSnippets.map(s => `
        <div style="border-bottom:1px solid var(--border);padding:0.5rem 0;">
            <div style="font-size:0.75rem;color:var(--text-secondary);">[${s.source}] ${s.query || ''}</div>
            <a href="${s.url}" target="_blank" style="color:var(--accent);font-size:0.85rem;">${s.title}</a>
            <p style="font-size:0.8rem;color:var(--text-secondary);margin:0;">${(s.content || '').substring(0, 120)}</p>
        </div>`).join('');
}


// ─── LAYER 4: Anomaly Detection Rendering ────────────────────────
function populateAnomalyView(l4) {
    const report = l4.forensics_report || {};
    const el = document.getElementById('forensicsSummaryContent');
    if (!el) return;

    // Summary
    const overall = report.overall_fraud_risk || 'N/A';
    const overallColor = overall === 'RED' ? '#ef4444' : overall === 'AMBER' ? '#f59e0b' : '#10b981';
    el.innerHTML = `
        <div style="display:flex;gap:1.5rem;flex-wrap:wrap;align-items:center;">
            <div style="font-size:1.2rem;font-weight:700;color:${overallColor};">Overall: ${overall}</div>
            <div style="font-size:0.9rem;">${report.total_alerts || 0} total alerts | Penalty: <strong>${report.total_score_penalty || 0}</strong></div>
        </div>`;

    // Alert cards grid
    const grid = document.getElementById('alertCardsGrid');
    const allAlerts = report.alerts || [];
    grid.innerHTML = allAlerts.filter(a => a.severity !== 'INFO' && a.severity !== 'GREEN').map(a => {
        const c = a.severity === 'RED' ? '#ef4444' : '#f59e0b';
        return `<div style="background:${c}11;border:1px solid ${c}33;border-radius:10px;padding:1rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <span style="font-weight:600;font-size:0.85rem;">${a.type?.replace(/_/g, ' ') || 'Alert'}</span>
                ${_severityBadge(a.severity)}
            </div>
            <p style="font-size:0.85rem;color:var(--text-secondary);margin:0;">${a.description}</p>
            <div style="font-size:0.7rem;color:var(--text-secondary);margin-top:0.5rem;">Source: ${a.source || '—'} | Penalty: ${a.score_penalty || 0}</div>
        </div>`;
    }).join('');

    // GST Forensics
    const gst = l4.gst_forensics || {};
    if (Object.keys(gst).length) {
        document.getElementById('gstForensicsCard').style.display = '';
        let gstRows = '';
        const a1 = gst.a1_reconciliation || {};
        if (a1.revenue_gst_alignment !== null && a1.revenue_gst_alignment !== undefined) {
            gstRows += `<tr><td>Revenue-GST Alignment</td><td>${a1.revenue_gst_alignment}</td><td>Correlation: ${a1.correlation || '—'}</td></tr>`;
            gstRows += `<tr><td>GST Mismatch Ratio</td><td>${a1.gst_mismatch_ratio}%</td><td>${a1.gst_mismatch_ratio > 20 ? '⚠ High gap' : '✅ Within range'}</td></tr>`;
        }
        const a2 = gst.a2_itc_mismatch || {};
        if (a2.gst_2a_vs_3b_gap_pct !== null && a2.gst_2a_vs_3b_gap_pct !== undefined) {
            gstRows += `<tr><td>ITC 2A vs 3B Gap</td><td>${a2.gst_2a_vs_3b_gap_pct}%</td><td>${a2.itc_mismatch_flag ? '⚠ Overclaimed' : '✅ Conservative'}</td></tr>`;
            gstRows += `<tr><td>Months Overclaimed</td><td>${a2.months_overclaimed || 0}</td><td>${a2.months_overclaimed > 3 ? '⚠ Pattern detected' : '—'}</td></tr>`;
        }
        const a3 = gst.a3_circular_trading || {};
        gstRows += `<tr><td>Circular Trading Ratio</td><td>${a3.circular_trading_ratio || 0}%</td><td>${a3.circular_volume_lakhs ? `₹${a3.circular_volume_lakhs}L detected` : 'None detected'}</td></tr>`;
        const a4 = gst.a4_filing_compliance || {};
        if (a4.gst_compliance_score !== null && a4.gst_compliance_score !== undefined) {
            gstRows += `<tr><td>Filing Compliance</td><td>${(a4.gst_compliance_score * 100).toFixed(0)}%</td><td>${a4.on_time_filings || 0}/${a4.total_filings || 0} on-time</td></tr>`;
        }
        document.getElementById('gstForensicsContent').innerHTML = `<table class="data-table"><thead><tr><th>Check</th><th>Value</th><th>Assessment</th></tr></thead><tbody>${gstRows}</tbody></table>`;
    }

    // Bank Forensics
    const bankF = l4.bank_forensics || {};
    if (Object.keys(bankF).length) {
        document.getElementById('bankForensicsCard').style.display = '';
        let bankRows = '';
        const b1 = bankF.b1_cheque_bounces || {};
        bankRows += `<tr><td>Cheque Bounces</td><td>${b1.bounce_count || 0}</td><td>₹${b1.bounce_amount_total_lakhs || 0}L total</td></tr>`;
        bankRows += `<tr><td>Bounce Frequency</td><td>${b1.cheque_bounce_frequency || 0}/month</td><td>${b1.insufficient_funds_bounces ? '⚠ Insufficient funds' : '—'}</td></tr>`;
        const b2 = bankF.b2_od_utilisation || {};
        if (b2.bank_od_utilisation_pct !== null && b2.bank_od_utilisation_pct !== undefined) {
            bankRows += `<tr><td>OD Utilisation</td><td>${b2.bank_od_utilisation_pct}%</td><td>${b2.bank_od_utilisation_pct > 85 ? '🔴 Stressed' : b2.bank_od_utilisation_pct > 70 ? '🟡 High' : '🟢 OK'}</td></tr>`;
            bankRows += `<tr><td>Utilisation Volatility</td><td>${b2.cc_utilisation_volatility}%</td><td>${b2.months_near_limit || 0} months near limit</td></tr>`;
        }
        const b3 = bankF.b3_cash_flow || {};
        if (b3.cash_deposit_ratio !== null) {
            bankRows += `<tr><td>Cash Deposit Ratio</td><td>${b3.cash_deposit_ratio}%</td><td>${b3.cash_deposit_ratio > 30 ? '🔴 Cash-heavy' : '✅ Normal'}</td></tr>`;
            bankRows += `<tr><td>EMI-to-Credit Ratio</td><td>${b3.emi_to_credit_ratio || 0}%</td><td>${b3.months_negative_flow || 0} negative months</td></tr>`;
        }
        document.getElementById('bankForensicsContent').innerHTML = `<table class="data-table"><thead><tr><th>Check</th><th>Value</th><th>Assessment</th></tr></thead><tbody>${bankRows}</tbody></table>`;
    }

    // Officer Before/After
    const adjustment = l4.officer_adjustment_explanation || {};
    const changes = adjustment.changes || {};
    const preFeatures = l4.pre_officer_features || {};
    const postFeatures = l4.feature_vector || {};
    const officerAnalysis = l4.officer_analysis || {};

    // Show officer comparison if officer notes were provided
    if (officerAnalysis.summary || Object.keys(changes).length || Object.keys(preFeatures).length) {
        document.getElementById('officerCompareCard').style.display = '';
        const explanations = adjustment.explanations || {};

        let html = '';

        // Officer summary
        if (officerAnalysis.summary) {
            html += `<div style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:1rem;margin-bottom:1rem;">
                <strong>📋 Officer Assessment:</strong> ${officerAnalysis.summary}
            </div>`;
        }

        // Overall impact
        if (adjustment.overall_impact) {
            html += `<p style="margin-bottom:1rem;color:var(--text-secondary);font-style:italic;">🔄 ${adjustment.overall_impact}</p>`;
        }

        // Build comparison table — focus on officer-influenced features
        const officerFeatures = ['factory_operational_flag', 'capacity_utilisation_pct', 'succession_risk_flag',
            'management_stability_score', 'working_capital_cycle_days'];
        let compareRows = '';

        // First show features that actually changed
        for (const [key, vals] of Object.entries(changes)) {
            const explanation = explanations[key] || 'Updated based on officer site-visit assessment';
            const changed = vals.before !== vals.after;
            compareRows += `<tr style="${changed ? 'background:rgba(245,158,11,0.1);' : ''}">
                <td><strong>${key.replace(/_/g, ' ')}</strong></td>
                <td>${typeof vals.before === 'number' ? vals.before.toFixed(2) : vals.before}</td>
                <td style="${changed ? 'color:#f59e0b;font-weight:600;' : ''}">${typeof vals.after === 'number' ? vals.after.toFixed(2) : vals.after}</td>
                <td style="font-size:0.85rem;color:var(--text-secondary);">${explanation}</td>
            </tr>`;
        }

        // Then show officer features that didn't change (for completeness)
        if (Object.keys(preFeatures).length && Object.keys(changes).length === 0) {
            for (const feat of officerFeatures) {
                const pre = preFeatures[feat];
                const post = postFeatures[feat];
                if (pre !== undefined) {
                    const changed = pre !== post;
                    compareRows += `<tr style="${changed ? 'background:rgba(245,158,11,0.1);' : ''}">
                        <td><strong>${feat.replace(/_/g, ' ')}</strong></td>
                        <td>${typeof pre === 'number' ? pre.toFixed(2) : pre}</td>
                        <td style="${changed ? 'color:#f59e0b;font-weight:600;' : ''}">${typeof post === 'number' ? post.toFixed(2) : post}</td>
                        <td style="font-size:0.85rem;color:var(--text-secondary);">${changed ? 'Changed by officer assessment' : 'No change — default retained'}</td>
                    </tr>`;
                }
            }
        }

        if (compareRows) {
            html += `<table class="data-table"><thead><tr><th>Feature</th><th>Before Officer Notes</th><th>After Officer Notes</th><th>AI Explanation</th></tr></thead><tbody>${compareRows}</tbody></table>`;
        } else if (!officerAnalysis.summary) {
            html += `<div class="empty-state">No officer notes were provided — using default values for qualitative features.</div>`;
        } else {
            html += `<div style="color:var(--text-secondary);font-size:0.9rem;">✅ Officer notes were processed but no feature values changed from defaults.</div>`;
        }

        // Key observations from officer
        if (officerAnalysis.key_observations && officerAnalysis.key_observations.length) {
            html += `<div style="margin-top:1rem;"><strong>Key Observations:</strong><ul style="margin:0.5rem 0 0 1rem;font-size:0.9rem;">`;
            for (const obs of officerAnalysis.key_observations) {
                html += `<li>${obs}</li>`;
            }
            html += `</ul></div>`;
        }

        // Risk and positive factors
        if (officerAnalysis.risk_factors && officerAnalysis.risk_factors.length) {
            html += `<div style="margin-top:0.5rem;"><strong style="color:#ef4444;">Risk Factors:</strong><ul style="margin:0.3rem 0 0 1rem;font-size:0.85rem;">`;
            for (const rf of officerAnalysis.risk_factors) {
                html += `<li style="color:#ef4444;">${rf}</li>`;
            }
            html += `</ul></div>`;
        }
        if (officerAnalysis.positive_factors && officerAnalysis.positive_factors.length) {
            html += `<div style="margin-top:0.5rem;"><strong style="color:#10b981;">Positive Factors:</strong><ul style="margin:0.3rem 0 0 1rem;font-size:0.85rem;">`;
            for (const pf of officerAnalysis.positive_factors) {
                html += `<li style="color:#10b981;">${pf}</li>`;
            }
            html += `</ul></div>`;
        }

        document.getElementById('officerCompareContent').innerHTML = html;
    }

    // Feature Vector
    const features = l4.feature_vector || {};
    const sources = l4.feature_audit_snapshot?.feature_sources || {};
    if (Object.keys(features).length) {
        document.getElementById('featureVectorCard').style.display = '';
        const tbody = document.getElementById('featureVectorBody');
        tbody.innerHTML = Object.entries(features).map(([key, val]) => {
            const displayVal = typeof val === 'number' ? val.toFixed(val % 1 === 0 ? 0 : 2) : String(val);
            return `<tr><td><strong>${key.replace(/_/g, ' ')}</strong></td><td>${displayVal}</td><td style="font-size:0.8rem;color:var(--text-secondary);">${sources[key] || '—'}</td></tr>`;
        }).join('');
    }

    // HITL Audit Trail
    const auditTrail = l4.hitl_audit_trail || [];
    const hitlDismissed = l4.hitl1_dismissed_alerts || [];
    if (auditTrail.length) {
        let auditHtml = `<div class="card" style="margin-top:1.5rem;">
            <div class="card-header">
                <span class="card-icon" style="background:rgba(139,92,246,0.2);">📋</span>
                <div>
                    <h3>HITL Governance Audit Trail</h3>
                    <p style="color:var(--text-secondary);font-size:0.8rem;">${auditTrail.length} recorded decisions — shown in CAM &amp; Layer 7-8 governance</p>
                </div>
            </div>
            <table class="data-table">
                <thead><tr>
                    <th>Stage</th><th>Action</th><th>Item</th>
                    <th>Before</th><th>After</th><th>Officer Reason</th><th>When</th>
                </tr></thead>
                <tbody>`;

        auditTrail.forEach(entry => {
            const actionColor = {
                'DISMISS_ALERT': '#ef4444',
                'DISMISS_FINDING': '#f59e0b',
                'OVERRIDE_FEATURE': '#8b5cf6',
                'CONFIRM_ALERT': '#10b981',
            }[entry.action] || '#6b7280';

            const actionLabel = entry.action.replace(/_/g, ' ');
            const ts = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString('en-IN') : '—';
            const before = entry.original_value !== null && entry.original_value !== undefined ? String(entry.original_value).substring(0, 20) : '—';
            const after = entry.new_value !== null && entry.new_value !== undefined ? String(entry.new_value).substring(0, 20) : '—';

            auditHtml += `<tr style="${entry.action.startsWith('DISMISS') || entry.action === 'OVERRIDE_FEATURE' ? 'background:rgba(139,92,246,0.05);' : ''}">
                <td><span style="background:#374151;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem;">HITL-${entry.hitl_stage}</span></td>
                <td><span style="color:${actionColor};font-size:0.8rem;font-weight:600;">${actionLabel}</span></td>
                <td style="font-size:0.8rem;font-family:monospace;">${entry.item_id}</td>
                <td style="font-size:0.8rem;">${before}</td>
                <td style="font-size:0.8rem;font-weight:600;color:${entry.action.startsWith('DISMISS') ? '#ef4444' : '#8b5cf6'};">${after}</td>
                <td style="font-size:0.8rem;color:var(--text-secondary);">${entry.reason || '—'}</td>
                <td style="font-size:0.75rem;color:var(--text-secondary);">${ts}</td>
            </tr>`;
        });

        auditHtml += `</tbody></table></div>`;

        // Inject after feature vector
        const fvCard = document.getElementById('featureVectorCard');
        if (fvCard) {
            const auditDiv = document.createElement('div');
            auditDiv.id = 'hitlAuditTrailSection';
            auditDiv.innerHTML = auditHtml;
            fvCard.after(auditDiv);
        }
    }
}


// ─── Officer Notes Modal Handlers ────────────────────────────────
let _officerNotesResolve = null;

function showOfficerNotesModal() {
    document.getElementById('officerNotesText').value = '';
    document.getElementById('modalOfficerNotes').style.display = 'flex';
    lucide.createIcons();
    return new Promise(resolve => { _officerNotesResolve = resolve; });
}

function skipOfficerNotes() {
    document.getElementById('modalOfficerNotes').style.display = 'none';
    if (_officerNotesResolve) {
        _officerNotesResolve('');
        _officerNotesResolve = null;
    }
}

function submitWithOfficerNotes() {
    const notes = document.getElementById('officerNotesText').value.trim();
    document.getElementById('modalOfficerNotes').style.display = 'none';
    if (_officerNotesResolve) {
        _officerNotesResolve(notes);
        _officerNotesResolve = null;
    }
}

// ═══════════════════════════════════════════════════════════
// LAYER 4 HITL-1: Forensic Flag Review
// ═══════════════════════════════════════════════════════════

function renderL4Hitl1Modal(data) {
    const alerts = data.alerts || [];
    const container = document.getElementById('hitl1AlertsContainer');

    if (!alerts.length) {
        container.innerHTML = `<div class="empty-state" style="padding:2rem;">
            ✅ No RED or AMBER forensic flags detected — pipeline will continue automatically.
        </div>`;
        return;
    }

    let html = `<div style="margin-bottom:0.5rem;color:var(--text-secondary);font-size:0.85rem;">
        ${data.red} RED flags &nbsp;|&nbsp; ${data.amber} AMBER flags &nbsp;|&nbsp; ${data.total} total alerts
    </div>`;

    alerts.forEach(alert => {
        const sevColor = alert.severity === 'RED' ? '#ef4444' : '#f59e0b';
        const sevBg = alert.severity === 'RED' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)';
        html += `<div id="hitl1_card_${alert.alert_id}" style="border:1px solid ${sevColor};border-radius:8px;padding:1rem;margin-bottom:0.75rem;background:${sevBg};">
            <div style="display:flex;align-items:flex-start;gap:0.75rem;">
                <div style="flex:1;">
                    <div style="display:flex;gap:0.5rem;align-items:center;margin-bottom:0.25rem;">
                        <span style="background:${sevColor};color:#fff;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:700;">${alert.severity}</span>
                        <span style="font-size:0.75rem;color:var(--text-secondary);">${alert.alert_id}</span>
                        <span style="font-size:0.8rem;color:${sevColor};font-weight:600;">Penalty: ${alert.score_penalty || 0}</span>
                    </div>
                    <div style="font-weight:600;margin-bottom:0.25rem;">${alert.type?.replace(/_/g, ' ')}</div>
                    <div style="font-size:0.85rem;color:var(--text-secondary);">${alert.description}</div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.2rem;">Source: ${alert.source || '—'}</div>
                </div>
                <div style="display:flex;flex-direction:column;gap:0.4rem;min-width:90px;text-align:right;">
                    <label style="display:flex;align-items:center;gap:0.3rem;justify-content:flex-end;cursor:pointer;">
                        <input type="radio" name="hitl1_${alert.alert_id}" value="keep" checked
                               onchange="toggleHitl1Reason('${alert.alert_id}', false)"> Keep
                    </label>
                    <label style="display:flex;align-items:center;gap:0.3rem;justify-content:flex-end;cursor:pointer;">
                        <input type="radio" name="hitl1_${alert.alert_id}" value="dismiss"
                               onchange="toggleHitl1Reason('${alert.alert_id}', true)"> Dismiss
                    </label>
                </div>
            </div>
            <div id="hitl1_reason_${alert.alert_id}" style="display:none;margin-top:0.5rem;">
                <input type="text" id="hitl1_reason_input_${alert.alert_id}"
                       placeholder="Reason for dismissal (required for CAM audit trail)..."
                       style="width:100%;padding:0.5rem;background:var(--card-bg);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:0.85rem;">
            </div>
        </div>`;
    });

    container.innerHTML = html;
}

function toggleHitl1Reason(alertId, show) {
    const el = document.getElementById(`hitl1_reason_${alertId}`);
    if (el) el.style.display = show ? 'block' : 'none';
}

async function submitL4Hitl1() {
    const appId = STATE._l4AppId;
    const alerts = (STATE._l4Hitl1Data?.alerts || []);
    const dismissedIds = [];
    const dismissReasons = {};

    for (const alert of alerts) {
        const aid = alert.alert_id;
        const selected = document.querySelector(`input[name="hitl1_${aid}"]:checked`);
        if (selected?.value === 'dismiss') {
            const reason = document.getElementById(`hitl1_reason_input_${aid}`)?.value?.trim();
            if (!reason) {
                showToast(`❌ Reason required for dismissing alert ${aid}`);
                return;
            }
            dismissedIds.push(aid);
            dismissReasons[aid] = reason;
        }
    }

    document.getElementById('btnSubmitHitl1').disabled = true;
    document.getElementById('btnSubmitHitl1').textContent = 'Submitting...';

    try {
        await fetch(`/api/applications/${appId}/layer4_hitl_1`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dismissed_alert_ids: dismissedIds, dismiss_reasons: dismissReasons })
        });
        document.getElementById('modalL4Hitl1').style.display = 'none';
        showToast(`✅ HITL-1 submitted — ${dismissedIds.length} alerts dismissed`);
    } catch (e) {
        showToast('❌ Failed to submit HITL-1');
        document.getElementById('btnSubmitHitl1').disabled = false;
        document.getElementById('btnSubmitHitl1').textContent = 'Submit Review & Continue';
    }
}

async function skipL4Hitl1() {
    const appId = STATE._l4AppId;
    document.getElementById('modalL4Hitl1').style.display = 'none';
    await fetch(`/api/applications/${appId}/layer4_hitl_1`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dismissed_alert_ids: [], dismiss_reasons: {} })
    });
    showToast('⏩ HITL-1 skipped — all forensic flags accepted');
}


// ═══════════════════════════════════════════════════════════
// LAYER 4 HITL-2: Web Research Review
// ═══════════════════════════════════════════════════════════

let _hitl2ActiveTab = 'adverse_media';

function showHitl2Tab(tab) {
    _hitl2ActiveTab = tab;
    ['adverse_media', 'litigation', 'mca_checks'].forEach(t => {
        const btn = document.getElementById(`htab_${t}`);
        if (btn) btn.style.fontWeight = t === tab ? '700' : '400';
    });
    if (STATE._l4Hitl2Data) renderL4Hitl2Modal(STATE._l4Hitl2Data, tab);
}

function renderL4Hitl2Modal(data, tab = 'adverse_media') {
    _hitl2ActiveTab = tab;
    ['adverse_media', 'litigation', 'mca_checks'].forEach(t => {
        const btn = document.getElementById(`htab_${t}`);
        if (btn) btn.style.fontWeight = t === tab ? '700' : '400';
    });

    const container = document.getElementById('hitl2FindingsContainer');
    const blockData = (data.research_findings || {})[tab] || {};
    const snippets = blockData.raw_snippets || blockData.cases || blockData.findings || [];
    const alerts = blockData.alerts || [];

    if (!snippets.length && !alerts.length) {
        container.innerHTML = `<div class="empty-state" style="padding:2rem;">No findings from this source — nothing to review.</div>`;
        return;
    }

    const sevColor = (s) => s === 'RED' ? '#ef4444' : s === 'AMBER' ? '#f59e0b' : '#10b981';

    let html = '';
    // Show alerts first
    alerts.forEach((alert, i) => {
        const fid = alert.finding_id || `${tab}_alert_${i}`;
        html += `<div style="border:1px solid ${sevColor(alert.severity)};border-radius:8px;padding:0.85rem;margin-bottom:0.6rem;background:rgba(0,0,0,0.2);">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div style="flex:1;">
                    <span style="background:${sevColor(alert.severity)};color:#fff;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;">${alert.severity}</span>
                    <span style="margin-left:0.5rem;font-weight:600;font-size:0.9rem;">${alert.type?.replace(/_/g, ' ') || 'Finding'}</span>
                    <p style="margin:0.3rem 0 0.2rem;font-size:0.85rem;color:var(--text-secondary);">${alert.description || ''}</p>
                    ${alert.source_url ? `<a href="${alert.source_url}" target="_blank" style="font-size:0.75rem;color:var(--accent-blue);">🔗 ${alert.source_url.substring(0, 60)}...</a>` : ''}
                </div>
                <div style="display:flex;gap:0.5rem;margin-left:1rem;white-space:nowrap;">
                    <label style="display:flex;align-items:center;gap:0.25rem;cursor:pointer;">
                        <input type="radio" name="hitl2_${tab}_${fid}" value="KEEP" checked> Keep
                    </label>
                    <label style="display:flex;align-items:center;gap:0.25rem;cursor:pointer;">
                        <input type="radio" name="hitl2_${tab}_${fid}" value="DISMISS"
                               onchange="toggleHitl2Reason('${tab}_${fid}', true)"
                               onfocus="toggleHitl2Reason('${tab}_${fid}', true)"> Dismiss
                    </label>
                </div>
            </div>
            <div id="hitl2_reason_${tab}_${fid}" style="display:none;margin-top:0.4rem;">
                <input type="text" id="hitl2_reason_input_${tab}_${fid}"
                       placeholder="Why is this finding incorrect or irrelevant? (required)"
                       style="width:100%;padding:0.4rem;background:var(--card-bg);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:0.8rem;">
            </div>
            <input type="hidden" name="hitl2_finding_id_${tab}_${fid}" value="${fid}">
            <input type="hidden" name="hitl2_block_${tab}_${fid}" value="${tab}">
        </div>`;
    });

    if (!html) {
        html = `<div class="empty-state" style="padding:1.5rem;">No classified alerts in this category.</div>`;
    }

    container.innerHTML = html;
}

function toggleHitl2Reason(key, show) {
    const el = document.getElementById(`hitl2_reason_${key}`);
    if (el) el.style.display = show ? 'block' : 'none';
}

async function submitL4Hitl2() {
    const appId = STATE._l4AppId;
    const allFindings = [];
    const blocks = ['adverse_media', 'litigation', 'mca_checks'];

    for (const tab of blocks) {
        const blockData = (STATE._l4Hitl2Data?.research_findings || {})[tab] || {};
        const alerts = blockData.alerts || [];

        alerts.forEach((alert, i) => {
            const fid = alert.finding_id || `${tab}_alert_${i}`;
            const selected = document.querySelector(`input[name="hitl2_${tab}_${fid}"]:checked`);
            const action = selected?.value || 'KEEP';

            if (action === 'DISMISS') {
                const reason = document.getElementById(`hitl2_reason_input_${tab}_${fid}`)?.value?.trim();
                if (!reason) {
                    showToast(`❌ Reason required to dismiss finding: ${alert.type || fid}`);
                    return;
                }
                allFindings.push({ block: tab, finding_id: fid, action: 'DISMISS', reason });
            }
        });
    }

    document.getElementById('btnSubmitHitl2').disabled = true;
    document.getElementById('btnSubmitHitl2').textContent = 'Submitting...';

    try {
        await fetch(`/api/applications/${appId}/layer4_hitl_2`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ findings: allFindings })
        });
        document.getElementById('modalL4Hitl2').style.display = 'none';
        const dismissed = allFindings.filter(f => f.action === 'DISMISS').length;
        showToast(`✅ HITL-2 submitted — ${dismissed} findings dismissed`);
    } catch (e) {
        showToast('❌ Failed to submit HITL-2');
        document.getElementById('btnSubmitHitl2').disabled = false;
        document.getElementById('btnSubmitHitl2').textContent = 'Submit Review & Continue';
    }
}

async function skipL4Hitl2() {
    const appId = STATE._l4AppId;
    document.getElementById('modalL4Hitl2').style.display = 'none';
    await fetch(`/api/applications/${appId}/layer4_hitl_2`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ findings: [] })
    });
    showToast('⏩ HITL-2 skipped — all research findings accepted');
}


// ═══════════════════════════════════════════════════════════
// LAYER 4 HITL-3: Feature Override Panel
// ═══════════════════════════════════════════════════════════

function renderL4Hitl3Modal(data) {
    const features = data.features || [];
    const officer = data.officer_analysis || {};

    document.getElementById('hitl3OfficerSummary').textContent =
        officer.summary || 'No officer notes provided — default values used.';

    const sourceColors = {
        'L2': '#6366f1', 'L3': '#8b5cf6',
        'A1': '#ef4444', 'A2': '#ef4444', 'A3': '#ef4444', 'A4': '#ef4444',
        'B1': '#f59e0b', 'B2': '#f59e0b', 'B3': '#f59e0b',
        'C1': '#3b82f6', 'C2': '#3b82f6', 'C3': '#3b82f6',
        'D1': '#06b6d4', 'D2': '#06b6d4',
        'E1': '#10b981', 'F1': '#84cc16',
    };

    let rows = '';
    features.forEach(feat => {
        const srcColor = sourceColors[feat.source] || '#6b7280';
        const val = typeof feat.value === 'number' ? feat.value.toFixed(3) : (feat.value ?? feat.default);
        rows += `<tr>
            <td style="font-size:0.85rem;font-weight:500;">${feat.name.replace(/_/g, ' ')}</td>
            <td style="font-weight:600;color:#e2e8f0;">${val}</td>
            <td><span style="background:${srcColor};color:#fff;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.7rem;">${feat.source}</span></td>
            <td>
                <input type="number" id="hitl3_val_${feat.name}" step="0.01"
                       placeholder="${val}"
                       onchange="document.getElementById('hitl3_reason_${feat.name}').required=true"
                       style="width:90px;padding:0.3rem;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:0.82rem;">
            </td>
            <td>
                <input type="text" id="hitl3_reason_${feat.name}"
                       placeholder="Required if overriding..."
                       style="width:100%;padding:0.3rem;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:0.8rem;">
            </td>
        </tr>`;
    });

    document.getElementById('hitl3FeaturesBody').innerHTML = rows;
}

async function submitL4Hitl3() {
    const appId = STATE._l4AppId;
    const features = STATE._l4Hitl3Data?.features || [];
    const overrides = [];

    for (const feat of features) {
        const valInput = document.getElementById(`hitl3_val_${feat.name}`);
        const reasonInput = document.getElementById(`hitl3_reason_${feat.name}`);
        const newVal = valInput?.value?.trim();
        const reason = reasonInput?.value?.trim();

        if (newVal !== '' && newVal !== null && newVal !== undefined) {
            if (!reason) {
                showToast(`❌ Reason required to override: ${feat.name.replace(/_/g, ' ')}`);
                return;
            }
            overrides.push({ feature: feat.name, new_value: parseFloat(newVal), reason });
        }
    }

    document.getElementById('btnSubmitHitl3').disabled = true;
    document.getElementById('btnSubmitHitl3').textContent = 'Submitting...';

    try {
        await fetch(`/api/applications/${appId}/layer4_hitl_3`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ overrides })
        });
        document.getElementById('modalL4Hitl3').style.display = 'none';
        showToast(`✅ HITL-3 submitted — ${overrides.length} feature override(s) applied`);
    } catch (e) {
        showToast('❌ Failed to submit HITL-3');
        document.getElementById('btnSubmitHitl3').disabled = false;
        document.getElementById('btnSubmitHitl3').textContent = 'Submit Overrides & Complete Layer 4';
    }
}

async function skipL4Hitl3() {
    const appId = STATE._l4AppId;
    document.getElementById('modalL4Hitl3').style.display = 'none';
    await fetch(`/api/applications/${appId}/layer4_hitl_3`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overrides: [] })
    });
    showToast('⏩ HITL-3 skipped — all computed features accepted');
}

// ─── Layer 5 HITL Hard Reject ──────────────────────────────────
async function acceptL5Reject() {
    const appId = STATE._l5AppId;
    document.getElementById('modalL5HitlReject').style.display = 'none';
    await fetch(`/api/applications/${appId}/layer5_hitl_reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'accept' })
    });
    showToast('❌ Auto-Reject Accepted. Generating rejection letter...', 'error');
}

async function overrideL5Reject() {
    const reason = document.getElementById('hitl5RejectOverrideReason').value.trim();
    if (!reason) {
        alert("An override justification is strictly required to bypass a Hard Reject.");
        return;
    }
    const appId = STATE._l5AppId;
    document.getElementById('modalL5HitlReject').style.display = 'none';
    await fetch(`/api/applications/${appId}/layer5_hitl_reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'override', reason: reason })
    });
    showToast('⚠ Hard Reject Overridden. Pipeline resuming ML scoring...', 'warning');
}

// ═══════════════════════════════════════════════════════════
// LAYER 5: Risk Scoring View Population
// ═══════════════════════════════════════════════════════════

function populateRiskScoringView(l5) {
    if (!l5) return;

    const ds = l5.decision_summary || {};
    const conf = l5.confidence || {};
    const breakdown = l5.score_breakdown || {};
    const expl = l5.explanation || {};
    const loan = l5.loan_structure || {};
    const hr = l5.hard_rules || {};
    const snap = l5.audit_snapshot || {};
    const pricing = l5.pricing || {};

    // ─── Decision Card ─────────────────────────────────────────
    const decCard = document.getElementById('l5DecisionCard');
    if (decCard) {
        decCard.style.display = '';

        // Decision badge
        const badge = document.getElementById('l5DecisionBadge');
        if (badge) {
            const decision = ds.decision || '—';
            const colors = { APPROVE: '#10b981', CONDITIONAL: '#f59e0b', REJECT: '#ef4444' };
            badge.textContent = decision;
            badge.style.background = (colors[decision] || '#6b7280') + '22';
            badge.style.color = colors[decision] || '#6b7280';
            badge.style.border = `2px solid ${colors[decision] || '#6b7280'}`;
        }

        // KPI tiles
        const score = ds.final_credit_score || 0;

        // ─── Legacy Decision Summary (Updated for LLM Bullets) ──────
        const dSumArea = document.getElementById('decisionSummary');
        if (dSumArea) {
            let summaryHtml = '';
            if (ds.llm_decision_summary) {
                // Parse simple markdown: **bold**, __bold__, *italic*, _italic_
                let parsedMd = ds.llm_decision_summary
                    .replace(/(\*\*|__)(.*?)\1/g, '<strong>$2</strong>')
                    .replace(/(\*|_)(.*?)\1/g, '<em>$2</em>');

                // Fix LLM markdown sometimes appearing purely on one line (e.g. "Text * bullet * bullet")
                parsedMd = parsedMd.replace(/(^|\s)([\*|\-])\s/g, '\n- ');

                const lines = parsedMd.split('\n').map(l => l.trim()).filter(l => l);
                let inList = false;
                let finalHtml = '';

                for (let line of lines) {
                    if (line.startsWith('-')) {
                        if (!inList) {
                            finalHtml += '<ul style="list-style-type:disc; padding-left:1.5rem; margin-top:0.5rem; margin-bottom:0.5rem; line-height:1.6; font-size:0.9rem; color:var(--text-secondary);">';
                            inList = true;
                        }
                        finalHtml += `<li>${line.substring(1).trim()}</li>`;
                    } else {
                        if (inList) {
                            finalHtml += '</ul>';
                            inList = false;
                        }
                        finalHtml += `<p style="font-size:0.9rem; color:var(--text-secondary); line-height:1.6; margin-bottom:0.5rem;">${line}</p>`;
                    }
                }
                if (inList) finalHtml += '</ul>';

                summaryHtml = finalHtml || `<p style="font-size:0.9rem; color:var(--text-secondary); line-height:1.6;">${ds.llm_decision_summary}</p>`;
            } else {
                // Fallback to basic text if no LLM summary
                const conditionsText = (ds.conditions || []).length ? ` Conditions: ${ds.conditions.join(', ')}` : '';
                summaryHtml = `<p style="font-size:0.9rem; color:var(--text-secondary); line-height:1.6;">The AI Engine has determined a <strong>${ds.decision}</strong> decision with a score of ${score}.${conditionsText}</p>`;
            }

            dSumArea.innerHTML = summaryHtml;
            dSumArea.classList.remove('empty-state');
        }
        const bandColors = { 'Very Low Risk': '#10b981', 'Low Risk': '#6366f1', 'Moderate Risk': '#f59e0b', 'High Risk': '#ef4444', 'Very High Risk': '#ef4444' };
        const bandColor = bandColors[ds.risk_band] || '#6b7280';

        _setText('l5FinalScore', score, bandColor);
        _setText('l5RiskBand', ds.risk_band || '—', bandColor);
        _setText('l5PD', ds.probability_of_default ? `${(ds.probability_of_default * 100).toFixed(1)}%` : '—');
        _setText('l5Rate', ds.interest_rate ? `${ds.interest_rate}%` : '—');
        _setText('l5Sanction', ds.sanction_amount_lakhs ? `₹${ds.sanction_amount_lakhs}L` : '—');
        _setText('l5ModelVersion', snap.model_metadata?.model_version || 'model_xgb_credit_v4.3');

        // ── Update donut with actual credit score ──
        setTimeout(() => updateRiskDonut(score), 300);


        // Confidence range bar
        const lower = conf.score_lower || 0;
        const upper = conf.score_upper || 900;
        const pct = Math.min(100, Math.max(10, ((upper - lower) / 600) * 100));
        _setText('l5ScoreLower', `↓ Optimistic: ${lower}`);
        _setText('l5ScoreUpper', `Pessimistic: ${upper} ↑`);
        _setText('l5UncertaintyLabel', `${conf.uncertainty_level || ''} Uncertainty | ±${(conf.pricing_buffer_bps || 0)}bps buffer`);
        const bar = document.getElementById('l5ConfidenceBar');
        if (bar) setTimeout(() => { bar.style.width = `${pct}%`; }, 200);

        // Score breakdown
        const sbody = document.getElementById('l5ScoreBreakdownBody');
        if (sbody) {
            const rows = [
                ['XGBoost Raw Score', breakdown.xgboost_raw, ''],
                ['LLM Qualitative Adjustment', breakdown.llm_adjustment, breakdown.llm_adjustment > 0 ? '#10b981' : breakdown.llm_adjustment < 0 ? '#ef4444' : ''],
                ['Uncertainty Penalty', breakdown.uncertainty_penalty, '#ef4444'],
                ['AMBER Alert Penalty', breakdown.amber_alert_penalty, '#f59e0b'],
                ['HC Condition Penalty', breakdown.hc_condition_penalty, '#f59e0b'],
                ['<strong>Final Adjusted Score</strong>', `<strong>${breakdown.final_score}</strong>`, bandColor],
            ];
            sbody.innerHTML = rows.map(([label, val, color]) =>
                `<tr><td>${label}</td><td style="text-align:right;font-weight:600;color:${color};">
                    ${typeof val === 'number' ? (val >= 0 ? '+' : '') + val : val ?? '—'}
                </td></tr>`
            ).join('');

            // ── Render score composition chart ──
            setTimeout(() => renderScoreCompositionChart(breakdown), 400);
        }
    }

    const shapCard = document.getElementById('l5ShapCard');
    if (shapCard && (expl.shap_waterfall || expl.shap_top_positive?.length)) {
        shapCard.style.display = '';
        _setText('l5ShapNarrative', expl.shap_waterfall || '');

        const posEl = document.getElementById('l5ShapPositive');
        const negEl = document.getElementById('l5ShapNegative');

        if (posEl) {
            posEl.innerHTML = (expl.shap_top_positive || []).map(d => `
                <div style="padding:0.75rem;background:rgba(16,185,129,0.08);border-radius:8px;border-left:3px solid #10b981;margin-bottom:0.6rem;">
                    <div style="font-size:0.82rem;font-weight:600;margin-bottom:0.3rem;">${d.label}</div>
                    <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;">
                        <div style="background:rgba(16,185,129,0.15);border-radius:6px;padding:0.25rem 0.6rem;">
                            <span style="font-size:0.7rem;color:#64748b;">Value: </span>
                            <span style="font-size:0.9rem;font-weight:700;color:#10b981;">${typeof d.value === 'number' ? d.value.toFixed(2) : d.value}</span>
                        </div>
                        <div style="background:rgba(16,185,129,0.1);border-radius:6px;padding:0.25rem 0.6rem;">
                            <span style="font-size:0.7rem;color:#64748b;">SHAP: </span>
                            <span style="font-size:0.85rem;font-weight:600;color:#10b981;">−${(d.shap_value || 0).toFixed(4)}</span>
                            <span style="font-size:0.7rem;color:#64748b;"> (${d.magnitude})</span>
                        </div>
                    </div>
                </div>`
            ).join('');
        }
        if (negEl) {
            negEl.innerHTML = (expl.shap_top_negative || []).map(d => `
                <div style="padding:0.75rem;background:rgba(239,68,68,0.08);border-radius:8px;border-left:3px solid #ef4444;margin-bottom:0.6rem;">
                    <div style="font-size:0.82rem;font-weight:600;margin-bottom:0.3rem;">${d.label}</div>
                    <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;">
                        <div style="background:rgba(239,68,68,0.15);border-radius:6px;padding:0.25rem 0.6rem;">
                            <span style="font-size:0.7rem;color:#64748b;">Value: </span>
                            <span style="font-size:0.9rem;font-weight:700;color:#ef4444;">${typeof d.value === 'number' ? d.value.toFixed(2) : d.value}</span>
                        </div>
                        <div style="background:rgba(239,68,68,0.1);border-radius:6px;padding:0.25rem 0.6rem;">
                            <span style="font-size:0.7rem;color:#64748b;">SHAP: </span>
                            <span style="font-size:0.85rem;font-weight:600;color:#ef4444;">+${(d.shap_value || 0).toFixed(4)}</span>
                            <span style="font-size:0.7rem;color:#64748b;"> (${d.magnitude})</span>
                        </div>
                    </div>
                </div>`
            ).join('');
        }

        // ── Render SHAP waterfall chart ──
        setTimeout(() => renderShapWaterfallChart(expl.shap_top_positive || [], expl.shap_top_negative || []), 400);
    }

    // ─── Five Cs Card ───────────────────────────────────────────
    const fiveCsCard = document.getElementById('l5FiveCsCard');
    const fiveCs = expl.five_cs || {};
    if (fiveCsCard && Object.keys(fiveCs).length) {
        fiveCsCard.style.display = '';
        const grid = document.getElementById('l5FiveCsGrid');
        if (grid) {
            const cColors = { POSITIVE: '#10b981', MODERATE: '#f59e0b', 'MODERATE — POSITIVE': '#6366f1', NEGATIVE: '#ef4444' };
            const cLabels = { character: '👤 Character', capacity: '💪 Capacity', capital: '🏦 Capital', collateral: '🏠 Collateral', conditions: '🌐 Conditions' };
            grid.innerHTML = Object.entries(cLabels).map(([key, label]) => {
                const c = fiveCs[key] || {};
                const rating = c.rating || 'MODERATE';
                const color = cColors[rating] || '#6b7280';
                return `<div style="padding:0.75rem;background:var(--surface-card);border-radius:10px;border-top:3px solid ${color};text-align:center;">
                    <div style="font-size:0.75rem;color:var(--text-secondary);">${label}</div>
                    <div style="font-size:0.9rem;font-weight:700;color:${color};margin-top:0.25rem;">${rating}</div>
                </div>`;
            }).join('');
        }
        // Always show Five Cs explanations as expandable cards
        const explContainer = document.getElementById('l5FiveCsExplanations');
        if (explContainer) {
            const cColors = { POSITIVE: '#10b981', MODERATE: '#f59e0b', 'MODERATE — POSITIVE': '#6366f1', NEGATIVE: '#ef4444' };
            const cLabels = { character: '👤 Character', capacity: '💪 Capacity', capital: '🏦 Capital', collateral: '🏠 Collateral', conditions: '🌐 Conditions' };
            explContainer.innerHTML = Object.entries(cLabels).map(([key, label]) => {
                const c = fiveCs[key] || {};
                const rating = c.rating || 'MODERATE';
                const color = cColors[rating] || '#6b7280';
                const explanation = c.explanation || '';
                if (!explanation) return '';
                return `<div style="padding:0.75rem;background:var(--surface-card);border-radius:8px;border-left:3px solid ${color};">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
                        <span style="font-size:0.8rem;font-weight:600;">${label}</span>
                        <span style="font-size:0.7rem;background:${color}22;color:${color};padding:0.15rem 0.5rem;border-radius:6px;">${rating}</span>
                    </div>
                    <div style="font-size:0.82rem;color:var(--text-secondary);line-height:1.6;">${explanation}</div>
                </div>`;
            }).join('');
        }

        _setText('l5LlmOpinion', expl.llm_opinion || '');
        _setText('l5BiggestRisk', expl.biggest_risk || '—');
        _setText('l5BiggestStrength', expl.biggest_strength || '—');
    }

    // ─── Loan + MPBF Card ──────────────────────────────────────
    const loanCard = document.getElementById('l5LoanCard');
    const loanStruct = loan.loan_structure || {};
    if (loanCard && (loanStruct.term_loan || loan.limits)) {
        loanCard.style.display = '';

        const noteEl = document.getElementById('l5HitlOverrideNote');
        if (noteEl) {
            if (loan.hitl_override_note) {
                noteEl.innerHTML = `<strong>⚖️ Officer Override:</strong> ${loan.hitl_override_note}`;
                noteEl.style.display = 'block';
            } else {
                noteEl.style.display = 'none';
            }
        }

        // Loan components table
        const loanBody = document.getElementById('l5LoanBody');
        if (loanBody) {
            const rows = [];
            if (loanStruct.term_loan) {
                const tl = loanStruct.term_loan;
                rows.push(`<tr><td>${tl.product || 'Term Loan'}</td><td>₹${tl.amount_lakhs}L</td><td>${tl.rate}%</td><td>${tl.tenure_months}m</td></tr>`);
            }
            if (loanStruct.working_capital) {
                const wc = loanStruct.working_capital;
                rows.push(`<tr><td>${wc.product || 'Working Capital OD'}</td><td>₹${wc.amount_lakhs}L</td><td>${wc.rate}%</td><td>${wc.tenure_months}m</td></tr>`);
            }
            rows.push(`<tr style="font-weight:700;"><td>Total Sanctioned</td><td>₹${loanStruct.total_sanctioned_lakhs || loan.approved_amount_lakhs}L</td><td>—</td><td>—</td></tr>`);
            loanBody.innerHTML = rows.join('');
        }

        // Limits table
        const limitsBody = document.getElementById('l5LimitsBody');
        if (limitsBody && loan.limits) {
            const binding = (loan.binding_constraint || '').toUpperCase();
            const methodLabels = {
                dscr_limit: 'DSCR-Based (Repayment Capacity)',
                gst_limit: 'GST Revenue Multiplier',
                collateral_limit: 'Collateral LTV (65%)',
                mpbf_limit: 'MPBF — Nayak Committee Method II',
                manual_override_limit: 'Human Officer Override',
            };
            limitsBody.innerHTML = Object.entries(loan.limits).map(([k, v]) => {
                const isBinding = k.replace('_limit', '').toUpperCase() === binding;
                return `<tr style="${isBinding ? 'background:rgba(99,102,241,0.1);' : ''}">
                    <td>${methodLabels[k] || k}</td>
                    <td style="font-weight:${isBinding ? '700' : '400'};">₹${typeof v === 'number' ? v.toFixed(1) : v}L</td>
                    <td>${isBinding ? '<span style="color:#6366f1;font-size:0.75rem;font-weight:600;">← BINDING</span>' : ''}</td>
                </tr>`;
            }).join('');
        }

        // MPBF breakdown
        const mpbfEl = document.getElementById('l5MpbfBreakdown');
        const mpbf = loan.mpbf || {};
        if (mpbfEl && mpbf.working_capital_gap !== undefined) {
            const ca = mpbf.current_assets || {};
            const cl = mpbf.current_liabilities_excl_bank || {};
            mpbfEl.innerHTML = `
                <table style="width:100%;border-collapse:collapse;font-size:0.82rem;">
                    <tr><td colspan="2" style="color:var(--text-secondary);font-size:0.75rem;padding-bottom:0.4rem;text-transform:uppercase;letter-spacing:0.05em;">Current Assets</td></tr>
                    ${_mpbfRow('  Inventory', ca.inventory)}
                    ${_mpbfRow('  Trade Debtors', ca.debtors)}
                    ${_mpbfRow('  Advances', ca.advances)}
                    ${_mpbfRow('  Cash & Bank', ca.cash)}
                    <tr style="font-weight:600;border-top:1px solid #374151;">${_mpbfRowRaw('<strong>Total Current Assets (A)</strong>', ca.total)}</tr>
                    <tr><td colspan="2" style="padding:0.5rem 0 0.25rem;"></td></tr>
                    <tr><td colspan="2" style="color:var(--text-secondary);font-size:0.75rem;padding-bottom:0.4rem;text-transform:uppercase;letter-spacing:0.05em;">Current Liabilities (excl. bank borrowings)</td></tr>
                    ${_mpbfRow('  Creditors', cl.creditors)}
                    ${_mpbfRow('  Provisions', cl.provisions)}
                    ${_mpbfRow('  Other CL', cl.other_cl)}
                    <tr style="font-size:0.7rem;color:var(--text-secondary);">${_mpbfRowRaw('  Bank Borrowings (excluded per RBI)', `[₹${cl.bank_borrowings_excluded || 0}L excluded]`)}</tr>
                    <tr style="font-weight:600;border-top:1px solid #374151;">${_mpbfRowRaw('<strong>Total CL excl. Bank (B)</strong>', cl.total)}</tr>
                    <tr style="height:0.5rem;"><td colspan="2"></td></tr>
                    <tr style="border-top:2px solid #6366f1;">${_mpbfRowRaw('<strong>Working Capital Gap (A−B)</strong>', `<strong>₹${mpbf.working_capital_gap?.toFixed(1) || 0}L</strong>`)}</tr>
                    <tr style="color:#10b981;font-weight:700;">${_mpbfRowRaw('MPBF = 75% of WC Gap', `₹${(mpbf.mpbf_75pct || 0).toFixed(1)}L`)}</tr>
                    <tr style="color:#f59e0b;">${_mpbfRowRaw("Borrower's Own Margin = 25%", `₹${(mpbf.borrower_margin_25pct || 0).toFixed(1)}L`)}</tr>
                </table>
                <div style="margin-top:0.5rem;font-size:0.7rem;color:var(--text-secondary);">📖 ${mpbf.rbi_method || 'Nayak Committee Method II'}</div>`;
        }

        // Covenants
        const covenantsEl = document.getElementById('l5Covenants');
        if (covenantsEl) {
            const covenants = ds.covenants || [];
            covenantsEl.innerHTML = covenants.map(c => `
                <div style="padding:0.6rem 0.75rem;background:rgba(99,102,241,0.07);border-radius:8px;border-left:3px solid #6366f1;margin-bottom:0.4rem;font-size:0.83rem;">
                    <span style="font-size:0.7rem;background:#374151;padding:0.1rem 0.4rem;border-radius:4px;margin-right:0.5rem;">${c.id}</span>
                    <span style="color:#6366f1;font-size:0.75rem;margin-right:0.5rem;">[${c.type}]</span>
                    ${c.description}
                </div>`
            ).join('') || '<div style="color:var(--text-secondary);font-size:0.85rem;">No covenants attached.</div>';
        }
    }

    // ─── Hard Rules Log ─────────────────────────────────────────
    const rulesCard = document.getElementById('l5RulesCard');
    const ruleLog = hr.rule_log || [];
    if (rulesCard && ruleLog.length) {
        rulesCard.style.display = '';
        const rulesBody = document.getElementById('l5RulesBody');
        if (rulesBody) {
            rulesBody.innerHTML = ruleLog.map(r => {
                const rColor = { REJECT: '#ef4444', CONDITIONAL: '#f59e0b', PASS: '#10b981' }[r.result] || '#6b7280';
                return `<tr>
                    <td><code style="font-size:0.8rem;">${r.rule_id}</code></td>
                    <td style="font-size:0.8rem;">${r.condition}</td>
                    <td><span style="color:${rColor};font-weight:600;font-size:0.8rem;">${r.result}</span></td>
                    <td style="font-size:0.8rem;color:var(--text-secondary);">${r.reason}</td>
                </tr>`;
            }).join('');
        }
    }

    // ─── Audit Snapshot ─────────────────────────────────────────
    const auditCard = document.getElementById('l5AuditCard');
    const auditBody = document.getElementById('l5AuditBody');
    if (auditCard && auditBody) {
        auditCard.style.display = '';
        const snapMeta = snap.model_metadata || {};
        const fvSnap = snap.feature_vector_snapshot || {};
        const dr = snap.decision_record || {};
        const audit = snap.auditability || {};
        const items = [
            ['Case ID', snap.case_metadata?.case_id || '—'],
            ['Snapshot Timestamp', snap.case_metadata?.snapshot_timestamp ? new Date(snap.case_metadata.snapshot_timestamp).toLocaleString('en-IN') : '—'],
            ['Model Version', snapMeta.model_version || '—'],
            ['Model Hash (SHA-256)', (snapMeta.model_hash || '').substring(0, 16) + '…'],
            ['Model Type', snapMeta.is_mock_model ? '⚠ Surrogate Mock (real model pending)' : '✅ Trained XGBoost'],
            ['Feature Vector Hash', (fvSnap.feature_vector_hash_sha256 || '').substring(0, 16) + '…'],
            ['Features Included', fvSnap.feature_count || 25],
            ['Imputations', fvSnap.imputation_flags?.length || 0],
            ['LLM Opinion Hash', (dr.llm_opinion_hash_sha256 || '').substring(0, 16) + '…'],
            ['Decision', dr.decision || '—'],
            ['Automated vs Human', audit.automated_vs_human || 'AUTOMATED'],
            ['Data Retention', `${audit.data_retention_years || 8} years (RBI mandate)`],
        ];
        auditBody.innerHTML = items.map(([k, v]) =>
            `<div style="padding:0.4rem 0.6rem;background:var(--surface-card);border-radius:6px;">
                <div style="font-size:0.7rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em;">${k}</div>
                <div style="font-size:0.82rem;font-weight:500;word-break:break-all;">${v}</div>
            </div>`
        ).join('');
    }
}

// ─── Helpers ─────────────────────────────────────────────────
function _setText(id, text, color) {
    const el = document.getElementById(id);
    if (el) {
        el.innerHTML = text ?? '—';
        if (color) el.style.color = color;
    }
}
function _mpbfRow(label, val) {
    const display = (val !== undefined && val !== null) ? `₹${parseFloat(val).toFixed(1)}L` : '₹0L';
    return `<tr><td style="padding:0.15rem 0;color:var(--text-secondary);">${label}</td><td style="text-align:right;">${display}</td></tr>`;
}
function _mpbfRowRaw(label, val) {
    return `<td style="padding:0.2rem 0;">${label}</td><td style="text-align:right;">${val}</td>`;
}


// ─── Chart.js — SHAP Waterfall Horizontal Bar Chart ──────────────────────────
let _shapChartInstance = null;
function renderShapWaterfallChart(topPositive, topNegative) {
    const canvas = document.getElementById('shapWaterfallChart');
    if (!canvas) return;
    const all = [
        ...topPositive.map(d => ({ label: d.label, value: -(d.shap_value || 0), actualVal: d.value, dir: 'positive' })),
        ...topNegative.map(d => ({ label: d.label, value: +(d.shap_value || 0), actualVal: d.value, dir: 'negative' })),
    ].sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 8);

    const labels = all.map(d => {
        const actStr = typeof d.actualVal === 'number' ? d.actualVal.toFixed(2) : d.actualVal;
        const lbl = d.label.length > 20 ? d.label.substring(0, 20) + '…' : d.label;
        return `${lbl} [${actStr}]`;
    });
    const values = all.map(d => +(d.value * 100).toFixed(3));
    const colors = all.map(d => d.dir === 'positive' ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.7)');
    const borders = all.map(d => d.dir === 'positive' ? '#10b981' : '#ef4444');

    if (_shapChartInstance) { _shapChartInstance.destroy(); }
    _shapChartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{ label: 'SHAP PD Impact (%pts)', data: values, backgroundColor: colors, borderColor: borders, borderWidth: 1, borderRadius: 4 }]
        },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.raw < 0
                            ? `Reduces default prob by ${Math.abs(ctx.raw).toFixed(3)}%pts (positive)`
                            : `Increases default prob by ${Math.abs(ctx.raw).toFixed(3)}%pts (risk factor)`
                    }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { size: 10 } }, title: { display: true, text: 'PD Change (%pts) — negative = score booster', color: '#94a3b8', font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { color: '#e2e8f0', font: { size: 10 } } }
            }
        }
    });
    document.getElementById('l5ShapChartCard').style.display = '';
}


// ─── Chart.js — Score Composition Doughnut ───────────────────────────────────
let _scoreChartInstance = null;
function renderScoreCompositionChart(breakdown) {
    const canvas = document.getElementById('scoreCompositionChart');
    if (!canvas) return;
    const xgbRaw = Math.abs(breakdown.xgboost_raw || 0);
    const llmAdj = Math.abs(breakdown.llm_adjustment || 0);
    const uncPen = Math.abs(breakdown.uncertainty_penalty || 0);
    const amberPen = Math.abs(breakdown.amber_alert_penalty || 0);
    const hcPen = Math.abs(breakdown.hc_condition_penalty || 0);
    if (_scoreChartInstance) { _scoreChartInstance.destroy(); }
    _scoreChartInstance = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: ['XGBoost Base', 'LLM Adjustment', 'Uncertainty Penalty', 'Alert Penalty', 'HC Penalty'],
            datasets: [{ data: [xgbRaw, llmAdj, uncPen, amberPen, hcPen], backgroundColor: ['#6366f1', '#10b981', '#ef4444', '#f59e0b', '#f97316'], borderColor: '#0f172a', borderWidth: 2, hoverOffset: 8 }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '60%',
            plugins: {
                legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12, padding: 8 } },
                tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw > 0 ? '+' : ''}${ctx.raw} pts` } }
            }
        }
    });
    document.getElementById('l5ScoreChartCard').style.display = '';
}


// ─── Update Donut with Actual Credit Score ────────────────────────────────────
function updateRiskDonut(creditScore, scoreMin = 300, scoreMax = 900) {
    const circle = document.getElementById('donutCircle');
    const scoreNum = document.getElementById('riskScoreNum');
    const riskGrade = document.getElementById('riskGrade');
    if (!circle) return;

    const pct = Math.min(1, Math.max(0, (creditScore - scoreMin) / (scoreMax - scoreMin)));
    const circumference = 2 * Math.PI * 50; // r=50
    const dash = pct * circumference;
    circle.style.strokeDasharray = `${dash.toFixed(1)} ${circumference.toFixed(1)}`;
    circle.style.transition = 'stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)';

    // Color by score
    let color = '#ef4444';
    let grade = 'HIGH RISK';
    if (creditScore >= 750) { color = '#10b981'; grade = 'EXCELLENT'; }
    else if (creditScore >= 700) { color = '#6366f1'; grade = 'LOW RISK'; }
    else if (creditScore >= 650) { color = '#f59e0b'; grade = 'MODERATE'; }
    else if (creditScore >= 600) { color = '#f97316'; grade = 'ELEVATED'; }
    circle.style.stroke = color;
    if (scoreNum) { scoreNum.textContent = creditScore; scoreNum.style.color = color; }
    if (riskGrade) { riskGrade.textContent = grade; riskGrade.style.color = color; }
}


// ─── Generate LLM SHAP Explanation ───────────────────────────────────────────
async function generateShapExplanation() {
    const appId = STATE.currentApp?.id;
    if (!appId) { showToast('❌ No active application'); return; }

    const btn = document.getElementById('btnGenerateShapExplain');
    const loading = document.getElementById('shapExplainLoading');
    const content = document.getElementById('shapExplainContent');
    const errorEl = document.getElementById('shapExplainError');
    const text = document.getElementById('shapExplainText');
    const cacheBadge = document.getElementById('shapExplainCacheBadge');

    if (btn) btn.disabled = true;
    if (loading) loading.style.display = 'block';
    if (content) content.style.display = 'none';
    if (errorEl) errorEl.style.display = 'none';

    try {
        const res = await fetch(`/api/applications/${appId}/shap_explain`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();
        if (data.error) {
            if (errorEl) { errorEl.textContent = '❌ ' + data.error; errorEl.style.display = 'block'; }
            showToast('❌ ' + data.error);
            return;
        }
        if (text) text.textContent = data.explanation || '';
        if (cacheBadge) {
            cacheBadge.textContent = data.cached ? '♻ Cached' : '✨ Fresh from Groq';
            cacheBadge.style.background = data.cached ? 'rgba(245,158,11,0.15)' : 'rgba(99,102,241,0.15)';
            cacheBadge.style.color = data.cached ? '#f59e0b' : '#818cf8';
        }
        if (content) content.style.display = 'block';
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        if (errorEl) { errorEl.textContent = 'Network error: ' + e.message; errorEl.style.display = 'block'; }
        showToast('❌ Failed to generate explanation');
    } finally {
        if (loading) loading.style.display = 'none';
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i data-lucide="refresh-cw" style="width:14px;height:14px;"></i> Regenerate`;
            if (window.lucide) lucide.createIcons();
        }
    }
}


// ═══════════════════════════════════════════════════════════
// LAYER 6: Decision Override (HITL)
// ═══════════════════════════════════════════════════════════

function openPendingHitlModal() {
    if (STATE._pendingHitlDecisionData) {
        showHitlDecisionModal(STATE._pendingHitlDecisionData);
    } else {
        showToast("No pending decision found.");
    }
}

function showHitlDecisionModal(data) {
    const dec = data.decision || {};

    // Set current AI recommendations as default
    document.getElementById('hitlDecSelect').value = dec.decision || 'APPROVE';
    document.getElementById('hitlDecAmount').value = dec.sanction_amount_lakhs || '';
    document.getElementById('hitlDecRate').value = dec.interest_rate || '';
    document.getElementById('hitlDecReason').value = '';

    // Store original values for risk checking
    STATE._l6OriginalDecision = dec.decision || 'APPROVE';
    STATE._l6OriginalAmount = dec.sanction_amount_lakhs || 0;

    // Reset UI state
    document.getElementById('hitlDecRiskWarning').style.display = 'none';
    document.getElementById('btnAcceptAi').style.display = 'inline-block';
    document.getElementById('btnOverrideAi').style.display = 'inline-block';
    document.getElementById('btnConfirmOverride').style.display = 'none';

    document.getElementById('hitlDecisionModal').style.display = 'flex';
}

function closeHitlDecisionModal() {
    document.getElementById('hitlDecisionModal').style.display = 'none';
}

async function handleHitlOverride() {
    const reason = document.getElementById('hitlDecReason').value.trim();
    const newDec = document.getElementById('hitlDecSelect').value;
    const newAmt = parseFloat(document.getElementById('hitlDecAmount').value);

    if (newDec !== STATE._l6OriginalDecision || Math.abs(newAmt - STATE._l6OriginalAmount) > 0.1) {
        if (!reason) {
            showToast('❌ You must provide a reason when overriding the AI decision.');
            document.getElementById('hitlDecReason').focus();
            return;
        }
    } else {
        showToast('ℹ You have not made any changes. Use "Accept AI Decision".');
        return;
    }

    const appId = STATE._hitlAppId;
    const btn = document.getElementById('btnOverrideAi');
    btn.textContent = 'Checking Risks...';
    btn.disabled = true;

    try {
        const res = await fetch(`/api/applications/${appId}/layer6_risk_check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_decision: STATE._l6OriginalDecision,
                old_loan_amount: STATE._l6OriginalAmount,
                decision: newDec,
                loan_amount: newAmt,
                reason: reason
            })
        });

        const data = await res.json();

        if (data.bullet_points) {
            STATE._l6RiskBullets = data.bullet_points;
            const warningUl = document.getElementById('hitlDecRiskBullets');
            warningUl.innerHTML = data.bullet_points.map(b => `<li style="margin-bottom:0.4rem;">${b.replace(/^•\s*/, '')}</li>`).join('');

            // Show warnings and morph buttons
            document.getElementById('hitlDecRiskWarning').style.display = 'block';
            document.getElementById('btnOverrideAi').style.display = 'none';
            document.getElementById('btnAcceptAi').style.display = 'inline-block';
            document.getElementById('btnConfirmOverride').style.display = 'inline-block';

            showToast('⚠ Please review the LLM risk assessment before confirming.');
        } else {
            showToast('❌ Failed to assess risks.');
        }

    } catch (e) {
        showToast('❌ Network error checking risks.');
    } finally {
        btn.textContent = 'Override Decision';
        btn.disabled = false;
    }
}

async function submitHitlDecision(isOverride) {
    const appId = STATE._hitlAppId;
    if (!appId) return;

    let payload = {};
    if (!isOverride) {
        // Accept AI
        payload = {
            decision: STATE._l6OriginalDecision,
            loan_amount: STATE._l6OriginalAmount,
            interest_rate: document.getElementById('hitlDecRate').value,
            reason: 'Accepted AI decision without modifications.'
        };
    } else {
        // Confirm Risky Override
        const reason = document.getElementById('hitlDecReason').value.trim();
        if (!reason) { showToast('❌ Reason required'); return; }

        payload = {
            decision: document.getElementById('hitlDecSelect').value,
            loan_amount: document.getElementById('hitlDecAmount').value,
            interest_rate: document.getElementById('hitlDecRate').value,
            reason: reason,
            risk_bullets: STATE._l6RiskBullets || []
        };
    }

    try {
        const res = await fetch(`/api/applications/${appId}/layer6_hitl_decision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.status) {
            closeHitlDecisionModal();
            showToast('✅ Layer 6 decision submitted! Continuing to CAM Generation.');
        } else {
            showToast('❌ ' + data.error);
        }
    } catch (e) {
        showToast('❌ Failed to submit decision.');
    }
}

// ═══════════════════════════════════════════════════════════
// LAYER 7: CAM Report Rendering
// ═══════════════════════════════════════════════════════════

function populateCAMView(camData) {
    if (!camData) return;

    // CAM Hash
    const hashEl = document.getElementById('camHash');
    if (hashEl) hashEl.textContent = camData.cam_hash ? camData.cam_hash.substring(0, 24) + '…' : '—';

    // Sections
    const secEl = document.getElementById('camSections');
    if (secEl) secEl.textContent = camData.sections || '—';

    // Timestamp
    const tsEl = document.getElementById('camTimestamp');
    if (tsEl) tsEl.textContent = camData.timestamp ? new Date(camData.timestamp).toLocaleString('en-IN') : '—';

    // Digital Signature
    const sig = camData.digital_signature;
    if (sig) {
        document.getElementById('camSignatureUnsigned').style.display = 'none';
        document.getElementById('camSignatureSigned').style.display = '';
        document.getElementById('sigOfficerName').textContent = sig.officer_name || '—';
        document.getElementById('sigOfficerRole').textContent = sig.officer_role || '—';
        document.getElementById('sigTimestamp').textContent = sig.timestamp ? new Date(sig.timestamp).toLocaleString('en-IN') : '—';
        document.getElementById('sigHash').textContent = sig.signature_hash ? sig.signature_hash.substring(0, 32) + '…' : '—';
    }

    // Audit grid
    const audit = camData.audit || {};
    const auditGrid = document.getElementById('camAuditGrid');
    if (auditGrid && Object.keys(audit).length) {
        const decColors = { APPROVE: '#10b981', CONDITIONAL: '#f59e0b', REJECT: '#ef4444' };
        const items = [
            ['AI Credit Score', audit.ai_score || '—', decColors[audit.final_decision] || '#6b7280'],
            ['Risk Band', audit.risk_band || '—', decColors[audit.final_decision] || '#6b7280'],
            ['Prob. of Default', audit.probability_of_default ? `${(audit.probability_of_default * 100).toFixed(1)}%` : '—', ''],
            ['Final Decision', audit.final_decision || '—', decColors[audit.final_decision] || '#6b7280'],
            ['Interest Rate', audit.interest_rate ? `${audit.interest_rate}%` : '—', ''],
            ['Sanction Amount', audit.sanction_amount_lakhs ? `₹${audit.sanction_amount_lakhs}L` : '—', ''],
            ['RED Flags', audit.forensics_summary?.red_flags ?? 0, '#ef4444'],
            ['AMBER Flags', audit.forensics_summary?.amber_flags ?? 0, '#f59e0b'],
            ['Total Penalty', audit.forensics_summary?.total_penalty ?? 0, ''],
            ['Feature Count', audit.feature_count || 25, ''],
            ['Model Version', audit.model_version || 'v4.3', '#6366f1'],
            ['Schema', audit.schema_version || '1.0.0', ''],
        ];
        auditGrid.innerHTML = items.map(([label, val, color]) => `
            <div style="padding:0.6rem;background:var(--surface-card);border-radius:8px;text-align:center;">
                <div style="font-size:0.7rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em;">${label}</div>
                <div style="font-size:1.1rem;font-weight:700;${color ? `color:${color};` : ''}">${val}</div>
            </div>
        `).join('');
    }

    // Five Cs Rating for CAM
    const fiveCs = audit.five_cs || {};
    const camFiveCsGrid = document.getElementById('camFiveCsGrid');
    if (camFiveCsGrid && Object.keys(fiveCs).length) {
        const cColors = { POSITIVE: '#10b981', MODERATE: '#f59e0b', 'MODERATE — POSITIVE': '#6366f1', NEGATIVE: '#ef4444' };
        const cLabels = { character: '👤 Character', capacity: '💪 Capacity', capital: '🏦 Capital', collateral: '🏠 Collateral', conditions: '🌐 Conditions' };
        camFiveCsGrid.innerHTML = Object.entries(cLabels).map(([key, label]) => {
            const c = fiveCs[key] || {};
            const rating = c.rating || 'NOT ASSESSED';
            const color = cColors[rating] || '#6b7280';
            return `<div style="padding:0.75rem;background:var(--surface-card);border-radius:10px;border-top:3px solid ${color};text-align:center;">
                <div style="font-size:0.75rem;color:var(--text-secondary);">${label}</div>
                <div style="font-size:0.9rem;font-weight:700;color:${color};margin-top:0.25rem;">${rating}</div>
            </div>`;
        }).join('');
    }

    if (window.lucide) lucide.createIcons();
}


// ─── CAM Download ────────────────────────────────────────────────────────────
function downloadCAM(format) {
    const appId = STATE.currentApp?.id;
    if (!appId) { showToast('❌ No active application'); return; }

    if (format === 'json') {
        // Open in new tab as JSON
        window.open(`/api/applications/${appId}/download_cam/json`, '_blank');
    } else {
        // Direct download
        window.location.href = `/api/applications/${appId}/download_cam/${format}`;
    }
    showToast(`📥 Downloading CAM as ${format.toUpperCase()}...`);
}


// ─── Digital Signature ───────────────────────────────────────────────────────
async function applyDigitalSignature() {
    const appId = STATE.currentApp?.id;
    if (!appId) { showToast('❌ No active application'); return; }

    if (!confirm('Apply your digital signature to this CAM report?\n\nThis action is logged in the audit trail and creates a tamper-evident hash.')) return;

    const btn = document.getElementById('btnDigitalSign');
    if (btn) { btn.disabled = true; btn.textContent = 'Signing...'; }

    try {
        const res = await fetch(`/api/applications/${appId}/digital_signature`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.error) {
            showToast('❌ ' + data.error);
            return;
        }

        // Update UI
        document.getElementById('camSignatureUnsigned').style.display = 'none';
        document.getElementById('camSignatureSigned').style.display = '';
        document.getElementById('sigOfficerName').textContent = data.officer_name || '—';
        document.getElementById('sigOfficerRole').textContent = STATE.user?.role || '—';
        document.getElementById('sigTimestamp').textContent = data.timestamp ? new Date(data.timestamp).toLocaleString('en-IN') : '—';
        document.getElementById('sigHash').textContent = data.signature_hash ? data.signature_hash.substring(0, 32) + '…' : '—';

        showToast('✅ Digital signature applied successfully!');
    } catch (e) {
        showToast('❌ Failed to apply digital signature');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i data-lucide="pen-tool" style="width:16px;height:16px;"></i> Apply Digital Signature'; }
        if (window.lucide) lucide.createIcons();
    }
}


// ─── Load CAM data from API when navigating to CAM tab ──────────────────────
async function loadCAMData() {
    const appId = STATE.currentApp?.id;
    if (!appId) return;

    try {
        const res = await fetch(`/api/applications/${appId}/cam_data`);
        if (res.ok) {
            const data = await res.json();
            populateCAMView(data);
        }
    } catch (e) {
        console.log('CAM data not yet available:', e.message);
    }
}



// ═══════════════════════════════════════════════════════
//  LAYER 8 — GOVERNANCE, MONITORING & COMPLIANCE
// ═══════════════════════════════════════════════════════

async function loadGovernance() {
    try {
        const res = await fetch('/api/layer8/dashboard-data');
        if (!res.ok) throw new Error('API error ' + res.status);
        const data = await res.json();
        renderGovernancePanel1(data.panel1_model_health);
        renderGovernancePanel2(data.panel2_psi_drift);
        renderGovernancePanel3(data.panel3_override_patterns);
        renderGovernancePanel4(data.panel4_sma_dashboard);
        renderGovernancePanel5(data.panel5_retraining);
        renderGovernancePanel6(data.panel6_crilc);
        renderModelInventoryCard(data.model_inventory);
    } catch (e) {
        console.error('Governance load error:', e);
        renderGovernancePlaceholder();
    }
}

function ragBadge(status, text) {
    const map = {
        GREEN: 'gov-badge-green', AMBER: 'gov-badge-amber', RED: 'gov-badge-red',
        PASS: 'gov-badge-green', FAIL: 'gov-badge-red', GREY: 'gov-badge-grey',
        LIVE: 'gov-badge-green', SHADOW: 'gov-badge-amber', RETIRED: 'gov-badge-grey',
        HIGH: 'gov-badge-red', MEDIUM: 'gov-badge-amber', LOW: 'gov-badge-green',
        WATCH: 'gov-badge-amber', ALERT: 'gov-badge-amber', CRITICAL: 'gov-badge-red', NPA: 'gov-badge-red'
    };
    const cls = map[status] || 'gov-badge-grey';
    return '<span class="gov-badge ' + cls + '">' + (text || status) + '</span>';
}

function renderGovernancePanel1(m) {
    const el = document.getElementById('govPanel1');
    if (!el || !m) return;
    el.innerHTML = '<div class="gov-metrics-grid">' +
        '<div class="gov-metric-card"><div class="gov-metric-label">AUC-ROC</div><div class="gov-metric-value">' + (m.auc_roc != null ? m.auc_roc : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.75 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">KS Statistic</div><div class="gov-metric-value">' + (m.ks_statistic != null ? m.ks_statistic : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.40 ' + ragBadge(m.ks_status || 'GREY', m.ks_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Gini Coefficient</div><div class="gov-metric-value">' + (m.gini_coefficient != null ? m.gini_coefficient : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.50 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">F1 Score</div><div class="gov-metric-value">' + (m.f1_score != null ? m.f1_score : '&mdash;') + '</div><div class="gov-metric-sub">Prec: ' + (m.precision || '&mdash;') + ' | Rec: ' + (m.recall || '&mdash;') + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Brier Score</div><div class="gov-metric-value">' + (m.brier_score != null ? m.brier_score : '&mdash;') + '</div><div class="gov-metric-sub">&le; 0.15 ideal ' + ragBadge(m.brier_status || 'GREY', m.brier_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Sample Size</div><div class="gov-metric-value">' + (m.sample_size != null ? m.sample_size : 0) + '</div><div class="gov-metric-sub">' + (m.period || '&mdash;') + (m.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div></div>' +
        '</div>';
}

function renderGovernancePanel2(drift) {
    const el = document.getElementById('govPanel2');
    if (!el) return;
    const features = drift && drift.features ? drift.features : [];
    const ov = drift && drift.overall_status ? drift.overall_status : 'GREY';
    const rows = features.map(function (f) {
        const rc = f.status === 'RED' ? 'psi-row-red' : f.status === 'AMBER' ? 'psi-row-amber' : '';
        return '<tr class="' + rc + '"><td><code>' + f.feature + '</code></td><td><strong>' + f.psi + '</strong></td><td>' +
            ragBadge(f.status, f.status) + '</td><td>' + (f.ref_count != null ? f.ref_count : '&mdash;') +
            '</td><td>' + (f.cur_count != null ? f.cur_count : '&mdash;') + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="gov-drift-summary">Overall: ' + ragBadge(ov, ov) +
        ' &nbsp;&#128308; <strong>' + (drift && drift.red_count != null ? drift.red_count : 0) + '</strong>' +
        ' &nbsp;&#128993; <strong>' + (drift && drift.amber_count != null ? drift.amber_count : 0) + '</strong>' +
        ' &nbsp;&#128994; <strong>' + (drift && drift.green_count != null ? drift.green_count : 0) + '</strong>' +
        (drift && drift.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div>' +
        '<div class="gov-table-wrap"><table class="gov-table"><thead><tr><th>Feature</th><th>PSI</th><th>Status</th><th>Ref N</th><th>Cur N</th></tr></thead><tbody>' +
        (rows || '<tr><td colspan="5" class="empty-state">No drift data yet</td></tr>') +
        '</tbody></table></div>';
}

function renderGovernancePanel3(data) {
    const el = document.getElementById('govPanel3');
    if (!el) return;
    const decisions = data && data.decisions ? data.decisions : {};
    const total = data && data.total_decisions ? data.total_decisions : 0;
    const ovr = data && data.override_rate_pct ? data.override_rate_pct : 0;
    const bars = Object.entries(decisions).map(function (entry) {
        const lbl = entry[0], cnt = entry[1];
        const pct = total ? Math.round(cnt / total * 100) : 0;
        const col = lbl === 'REJECT' ? '#ef4444' : lbl.indexOf('CONDITIONAL') >= 0 ? '#f59e0b' : '#10b981';
        return '<div class="gov-bar-row"><span class="gov-bar-label">' + lbl + '</span>' +
            '<div class="gov-bar-track"><div class="gov-bar-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
            '<span class="gov-bar-pct">' + cnt + ' (' + pct + '%)</span></div>';
    }).join('');
    const ovrStatus = ovr > 35 ? 'RED' : ovr > 20 ? 'AMBER' : 'GREEN';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Total Decisions</span><strong>' + total + '</strong></div>' +
        '<div class="gov-stat-row"><span>Override Rate</span><strong>' + ovr + '%</strong> ' + ragBadge(ovrStatus, ovrStatus) + '</div>' +
        '<div class="gov-bars">' + (bars || '<div class="empty-state">No decisions yet</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel4(data) {
    const el = document.getElementById('govPanel4');
    if (!el) return;
    const c = data && data.sma_counts ? data.sma_counts : {};
    const cards = [
        { lbl: 'REGULAR', cnt: c.REGULAR != null ? c.REGULAR : 0, cls: 'sma-regular' },
        { lbl: 'SMA-0 (1-30 DPD)', cnt: c['SMA-0'] != null ? c['SMA-0'] : 0, cls: 'sma-0' },
        { lbl: 'SMA-1 (31-60 DPD)', cnt: c['SMA-1'] != null ? c['SMA-1'] : 0, cls: 'sma-1' },
        { lbl: 'SMA-2 (61-90 DPD)', cnt: c['SMA-2'] != null ? c['SMA-2'] : 0, cls: 'sma-2' },
        { lbl: 'NPA (>90 DPD)', cnt: c.NPA != null ? c.NPA : 0, cls: 'sma-npa' },
    ].map(function (cc) {
        return '<div class="sma-card ' + cc.cls + '"><div class="sma-card-count">' + cc.cnt +
            '</div><div class="sma-card-label">' + cc.lbl + '</div></div>';
    }).join('');
    const alerts = (data && data.early_warnings ? data.early_warnings : []).map(function (w) {
        return '<div class="gov-alert-row"><span class="gov-alert-signal">' + w.signal +
            '</span><span>' + w.description + '</span>' + ragBadge(w.severity, w.severity) + '</div>';
    }).join('');
    el.innerHTML = '<div class="sma-cards-grid">' + cards + '</div>' +
        '<div class="gov-section-label" style="margin-top:10px;">Early Warning Signals</div>' +
        '<div class="gov-alerts">' + (alerts || '<div class="empty-state">No active warnings</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel5(data) {
    const el = document.getElementById('govPanel5');
    if (!el) return;
    const history = (data && data.history ? data.history : []).slice(0, 5).map(function (h) {
        const sc = h.status === 'COMPLETED' ? 'gov-badge-green' : h.status === 'INITIATED' ? 'gov-badge-amber' : 'gov-badge-grey';
        const dt = h.created_at ? new Date(h.created_at).toLocaleDateString() : '&mdash;';
        return '<div class="gov-history-row"><span class="gov-history-trigger">' + h.trigger_type +
            '</span><span>' + dt + '</span><span class="gov-badge ' + sc + '">' + h.status + '</span></div>';
    }).join('');
    const nextDue = data && data.next_retrain_due ? new Date(data.next_retrain_due).toLocaleDateString() : '2026-09-01';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Current Model</span><strong>' + (data && data.current_model ? data.current_model : 'XGB_CREDIT_V4.3') + '</strong></div>' +
        '<div class="gov-stat-row"><span>Shadow Mode</span>' + (data && data.shadow_mode_active ? ragBadge('AMBER', 'ACTIVE') : ragBadge('GREEN', 'INACTIVE')) + '</div>' +
        '<div class="gov-stat-row"><span>Next Retrain Due</span><strong>' + nextDue + '</strong></div>' +
        '<div class="gov-stat-row"><span>IMV Due</span><strong>2026-09-01</strong></div>' +
        '<div class="gov-section-label" style="margin-top:12px;">Recent Events</div>' +
        '<div class="gov-history">' + (history || '<div class="empty-state">No retraining events yet</div>') + '</div>' +
        '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">' +
        '<button class="btn btn-outline btn-sm" onclick="triggerRetraining()">&#128260; Trigger Retraining</button>' +
        '<button class="btn btn-outline btn-sm" onclick="runIMV()">&#128203; Run IMV Check</button></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel6(data) {
    const el = document.getElementById('govPanel6');
    if (!el) return;
    const rows = (data && data.submissions ? data.submissions : []).slice(0, 8).map(function (s) {
        const sc = s.submission_status === 'SUBMITTED' ? 'gov-badge-green' : 'gov-badge-amber';
        return '<tr>' +
            '<td><strong>' + (s.case_id || '&mdash;') + '</strong></td>' +
            '<td>' + (s.borrower_name || '&mdash;') + '</td>' +
            '<td>&#8377;' + (s.outstanding_cr || 0) + ' Cr</td>' +
            '<td>' + (s.sma_status || '&mdash;') + '</td>' +
            '<td>' + (s.quarter || '&mdash;') + '</td>' +
            '<td><span class="gov-badge ' + sc + '">' + (s.submission_status || '&mdash;') + '</span></td>' +
            '</tr>';
    }).join('');
    el.innerHTML =
        '<div class="gov-stat-row"><span>Eligible (&ge;&#8377;5 Cr)</span><strong>' + (data && data.total != null ? data.total : 0) + '</strong></div>' +
        '<div class="gov-stat-row"><span>Submitted</span>' + ragBadge('GREEN', (data && data.submitted != null ? data.submitted : 0) + ' cases') + '</div>' +
        '<div class="gov-stat-row"><span>Pending</span>' + ragBadge(data && data.pending > 0 ? 'AMBER' : 'GREEN', (data && data.pending != null ? data.pending : 0) + ' cases') + '</div>' +
        '<div class="gov-table-wrap" style="margin-top:12px;">' +
        '<table class="gov-table"><thead><tr><th>Case ID</th><th>Borrower</th><th>Exposure</th><th>SMA</th><th>Quarter</th><th>Status</th></tr></thead>' +
        '<tbody>' + (rows || '<tr><td colspan="6" class="empty-state">No CRILC eligible cases</td></tr>') + '</tbody></table></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderModelInventoryCard(inv) {
    const el = document.getElementById('govModelInventory');
    if (!el || !inv) return;
    el.innerHTML =
        '<div class="gov-inv-row"><span>Model ID</span><strong>' + (inv.model_id || '&mdash;') + '</strong></div>' +
        '<div class="gov-inv-row"><span>Status</span>' + ragBadge(inv.status, inv.status) + '</div>' +
        '<div class="gov-inv-row"><span>Risk Rating</span>' + ragBadge(inv.model_risk_rating, inv.model_risk_rating) + '</div>' +
        '<div class="gov-inv-row"><span>Model Owner</span>' + (inv.model_owner || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>RMCB Resolution</span>' + (inv.rmcb_resolution_no || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>Last Validated</span>' + (inv.last_validation_date || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>Next Validation</span><strong>' + (inv.next_validation_due || '&mdash;') + '</strong></div>';
}

async function showExplanationModal(caseId) {
    if (!caseId) { showToast('No case ID available'); return; }
    const modal = document.getElementById('modalExplanation');
    if (!modal) return;
    document.getElementById('explanationCaseId').textContent = caseId;
    document.getElementById('explanationBody').innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    modal.style.display = 'flex';
    try {
        const res = await fetch('/api/applications/' + caseId + '/explanation');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const improve = (data.what_can_improve || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const supp = (data.supporting_reasons || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const dc = data.decision && data.decision.indexOf('REJECT') >= 0 ? 'RED' :
            data.decision && data.decision.indexOf('CONDITIONAL') >= 0 ? 'AMBER' : 'GREEN';
        document.getElementById('explanationBody').innerHTML =
            '<div class="exp-decision">' + ragBadge(dc, data.decision || '&mdash;') + '</div>' +
            '<div class="exp-section"><div class="exp-label">Primary Reason</div><div class="exp-text">' + (data.primary_reason || '&mdash;') + '</div></div>' +
            (supp ? '<div class="exp-section"><div class="exp-label">Supporting Factors</div><ul class="exp-list">' + supp + '</ul></div>' : '') +
            (improve ? '<div class="exp-section"><div class="exp-label">How to Improve Your Application</div><ul class="exp-list imp-list">' + improve + '</ul></div>' : '') +
            '<div class="exp-footer">' +
            '<span>Score: <strong>' + (data.credit_score != null ? data.credit_score : '&mdash;') + '</strong></span>' +
            '<span>Band: <strong>' + (data.risk_band || '&mdash;') + '</strong></span>' +
            '<span>Model: <strong>' + (data.model_version || 'v4.3') + '</strong></span>' +
            '</div>';
    } catch (e) {
        document.getElementById('explanationBody').innerHTML =
            '<div style="color:#ef4444">&#9888; ' + (e.message || 'Unable to generate explanation') + '</div>';
    }
}

// ─── Governance / Retraining Handlers ───────────────────────────
async function triggerRetraining() {
    try {
        const res = await fetch('/api/layer8/trigger-retraining', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trigger: "MANUAL_UI_TRIGGER", details: { reason: "Requested by CRO via UI" } })
        });
        const d = await res.json();
        if (d.status === 'ok') {
            showToast('✅ Retraining triggered (ID: ' + d.retrain_id + ')');
            setTimeout(() => _loadPanel('retraining-status', 'govPanelRetraining'), 1500);
        } else {
            showToast('❌ Retraining error: ' + (d.error || 'Unknown'));
        }
    } catch (e) {
        showToast('❌ Failed to trigger retraining');
    }
}

async function runIMV() {
    showToast('Running IMV check...');
    try {
        const r = await fetch('/api/layer8/run-imv', { method: 'POST' });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('IMV complete: ' + d.report.overall_status);
        loadGovernance();
    } catch (e) { showToast('IMV failed: ' + (e.message || 'error')); }
}

function renderGovernancePlaceholder() {
    ['govPanel1', 'govPanel2', 'govPanel3', 'govPanel4', 'govPanel5', 'govPanel6'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="empty-state">Loading governance data...</div>';
    });
}


// ═══════════════════════════════════════════════════════
//  LAYER 8 — GOVERNANCE, MONITORING & COMPLIANCE
// ═══════════════════════════════════════════════════════

async function loadGovernance() {
    try {
        const res = await fetch('/api/layer8/dashboard-data');
        if (!res.ok) throw new Error('API error ' + res.status);
        const data = await res.json();
        renderGovernancePanel1(data.panel1_model_health);
        renderGovernancePanel2(data.panel2_psi_drift);
        renderGovernancePanel3(data.panel3_override_patterns);
        renderGovernancePanel4(data.panel4_sma_dashboard);
        renderGovernancePanel5(data.panel5_retraining);
        renderGovernancePanel6(data.panel6_crilc);
        renderModelInventoryCard(data.model_inventory);
    } catch (e) {
        console.error('Governance load error:', e);
        renderGovernancePlaceholder();
    }
}

function ragBadge(status, text) {
    const map = {
        GREEN: 'gov-badge-green', AMBER: 'gov-badge-amber', RED: 'gov-badge-red',
        PASS: 'gov-badge-green', FAIL: 'gov-badge-red', GREY: 'gov-badge-grey',
        LIVE: 'gov-badge-green', SHADOW: 'gov-badge-amber', RETIRED: 'gov-badge-grey',
        HIGH: 'gov-badge-red', MEDIUM: 'gov-badge-amber', LOW: 'gov-badge-green',
        WATCH: 'gov-badge-amber', ALERT: 'gov-badge-amber', CRITICAL: 'gov-badge-red', NPA: 'gov-badge-red'
    };
    const cls = map[status] || 'gov-badge-grey';
    return '<span class="gov-badge ' + cls + '">' + (text || status) + '</span>';
}

function renderGovernancePanel1(m) {
    const el = document.getElementById('govPanel1');
    if (!el || !m) return;
    el.innerHTML = '<div class="gov-metrics-grid">' +
        '<div class="gov-metric-card"><div class="gov-metric-label">AUC-ROC</div><div class="gov-metric-value">' + (m.auc_roc != null ? m.auc_roc : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.75 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">KS Statistic</div><div class="gov-metric-value">' + (m.ks_statistic != null ? m.ks_statistic : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.40 ' + ragBadge(m.ks_status || 'GREY', m.ks_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Gini Coefficient</div><div class="gov-metric-value">' + (m.gini_coefficient != null ? m.gini_coefficient : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.50 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">F1 Score</div><div class="gov-metric-value">' + (m.f1_score != null ? m.f1_score : '&mdash;') + '</div><div class="gov-metric-sub">Prec: ' + (m.precision || '&mdash;') + ' | Rec: ' + (m.recall || '&mdash;') + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Brier Score</div><div class="gov-metric-value">' + (m.brier_score != null ? m.brier_score : '&mdash;') + '</div><div class="gov-metric-sub">&le; 0.15 ideal ' + ragBadge(m.brier_status || 'GREY', m.brier_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Sample Size</div><div class="gov-metric-value">' + (m.sample_size != null ? m.sample_size : 0) + '</div><div class="gov-metric-sub">' + (m.period || '&mdash;') + (m.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div></div>' +
        '</div>';
}

function renderGovernancePanel2(drift) {
    const el = document.getElementById('govPanel2');
    if (!el) return;
    const features = drift && drift.features ? drift.features : [];
    const ov = drift && drift.overall_status ? drift.overall_status : 'GREY';
    const rows = features.map(function (f) {
        const rc = f.status === 'RED' ? 'psi-row-red' : f.status === 'AMBER' ? 'psi-row-amber' : '';
        return '<tr class="' + rc + '"><td><code>' + f.feature + '</code></td><td><strong>' + f.psi + '</strong></td><td>' +
            ragBadge(f.status, f.status) + '</td><td>' + (f.ref_count != null ? f.ref_count : '&mdash;') +
            '</td><td>' + (f.cur_count != null ? f.cur_count : '&mdash;') + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="gov-drift-summary">Overall: ' + ragBadge(ov, ov) +
        ' &nbsp;&#128308; <strong>' + (drift && drift.red_count != null ? drift.red_count : 0) + '</strong>' +
        ' &nbsp;&#128993; <strong>' + (drift && drift.amber_count != null ? drift.amber_count : 0) + '</strong>' +
        ' &nbsp;&#128994; <strong>' + (drift && drift.green_count != null ? drift.green_count : 0) + '</strong>' +
        (drift && drift.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div>' +
        '<div class="gov-table-wrap"><table class="gov-table"><thead><tr><th>Feature</th><th>PSI</th><th>Status</th><th>Ref N</th><th>Cur N</th></tr></thead><tbody>' +
        (rows || '<tr><td colspan="5" class="empty-state">No drift data yet</td></tr>') +
        '</tbody></table></div>';
}

function renderGovernancePanel3(data) {
    const el = document.getElementById('govPanel3');
    if (!el) return;
    const decisions = data && data.decisions ? data.decisions : {};
    const total = data && data.total_decisions ? data.total_decisions : 0;
    const ovr = data && data.override_rate_pct ? data.override_rate_pct : 0;
    const bars = Object.entries(decisions).map(function (entry) {
        const lbl = entry[0], cnt = entry[1];
        const pct = total ? Math.round(cnt / total * 100) : 0;
        const col = lbl === 'REJECT' ? '#ef4444' : lbl.indexOf('CONDITIONAL') >= 0 ? '#f59e0b' : '#10b981';
        return '<div class="gov-bar-row"><span class="gov-bar-label">' + lbl + '</span>' +
            '<div class="gov-bar-track"><div class="gov-bar-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
            '<span class="gov-bar-pct">' + cnt + ' (' + pct + '%)</span></div>';
    }).join('');
    const ovrStatus = ovr > 35 ? 'RED' : ovr > 20 ? 'AMBER' : 'GREEN';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Total Decisions</span><strong>' + total + '</strong></div>' +
        '<div class="gov-stat-row"><span>Override Rate</span><strong>' + ovr + '%</strong> ' + ragBadge(ovrStatus, ovrStatus) + '</div>' +
        '<div class="gov-bars">' + (bars || '<div class="empty-state">No decisions yet</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel4(data) {
    const el = document.getElementById('govPanel4');
    if (!el) return;
    const c = data && data.sma_counts ? data.sma_counts : {};
    const cards = [
        { lbl: 'REGULAR', cnt: c.REGULAR != null ? c.REGULAR : 0, cls: 'sma-regular' },
        { lbl: 'SMA-0 (1-30 DPD)', cnt: c['SMA-0'] != null ? c['SMA-0'] : 0, cls: 'sma-0' },
        { lbl: 'SMA-1 (31-60 DPD)', cnt: c['SMA-1'] != null ? c['SMA-1'] : 0, cls: 'sma-1' },
        { lbl: 'SMA-2 (61-90 DPD)', cnt: c['SMA-2'] != null ? c['SMA-2'] : 0, cls: 'sma-2' },
        { lbl: 'NPA (>90 DPD)', cnt: c.NPA != null ? c.NPA : 0, cls: 'sma-npa' },
    ].map(function (cc) {
        return '<div class="sma-card ' + cc.cls + '"><div class="sma-card-count">' + cc.cnt +
            '</div><div class="sma-card-label">' + cc.lbl + '</div></div>';
    }).join('');
    const alerts = (data && data.early_warnings ? data.early_warnings : []).map(function (w) {
        return '<div class="gov-alert-row"><span class="gov-alert-signal">' + w.signal +
            '</span><span>' + w.description + '</span>' + ragBadge(w.severity, w.severity) + '</div>';
    }).join('');
    el.innerHTML = '<div class="sma-cards-grid">' + cards + '</div>' +
        '<div class="gov-section-label" style="margin-top:10px;">Early Warning Signals</div>' +
        '<div class="gov-alerts">' + (alerts || '<div class="empty-state">No active warnings</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel5(data) {
    const el = document.getElementById('govPanel5');
    if (!el) return;
    const history = (data && data.history ? data.history : []).slice(0, 5).map(function (h) {
        const sc = h.status === 'COMPLETED' ? 'gov-badge-green' : h.status === 'INITIATED' ? 'gov-badge-amber' : 'gov-badge-grey';
        const dt = h.created_at ? new Date(h.created_at).toLocaleDateString() : '&mdash;';
        return '<div class="gov-history-row"><span class="gov-history-trigger">' + h.trigger_type +
            '</span><span>' + dt + '</span><span class="gov-badge ' + sc + '">' + h.status + '</span></div>';
    }).join('');
    const nextDue = data && data.next_retrain_due ? new Date(data.next_retrain_due).toLocaleDateString() : '2026-09-01';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Current Model</span><strong>' + (data && data.current_model ? data.current_model : 'XGB_CREDIT_V4.3') + '</strong></div>' +
        '<div class="gov-stat-row"><span>Shadow Mode</span>' + (data && data.shadow_mode_active ? ragBadge('AMBER', 'ACTIVE') : ragBadge('GREEN', 'INACTIVE')) + '</div>' +
        '<div class="gov-stat-row"><span>Next Retrain Due</span><strong>' + nextDue + '</strong></div>' +
        '<div class="gov-stat-row"><span>IMV Due</span><strong>2026-09-01</strong></div>' +
        '<div class="gov-section-label" style="margin-top:12px;">Recent Events</div>' +
        '<div class="gov-history">' + (history || '<div class="empty-state">No retraining events yet</div>') + '</div>' +
        '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">' +
        '<button class="btn btn-outline btn-sm" onclick="triggerRetraining()">&#128260; Trigger Retraining</button>' +
        '<button class="btn btn-outline btn-sm" onclick="runIMV()">&#128203; Run IMV Check</button></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel6(data) {
    const el = document.getElementById('govPanel6');
    if (!el) return;
    const rows = (data && data.submissions ? data.submissions : []).slice(0, 8).map(function (s) {
        const sc = s.submission_status === 'SUBMITTED' ? 'gov-badge-green' : 'gov-badge-amber';
        return '<tr>' +
            '<td><strong>' + (s.case_id || '&mdash;') + '</strong></td>' +
            '<td>' + (s.borrower_name || '&mdash;') + '</td>' +
            '<td>&#8377;' + (s.outstanding_cr || 0) + ' Cr</td>' +
            '<td>' + (s.sma_status || '&mdash;') + '</td>' +
            '<td>' + (s.quarter || '&mdash;') + '</td>' +
            '<td><span class="gov-badge ' + sc + '">' + (s.submission_status || '&mdash;') + '</span></td>' +
            '</tr>';
    }).join('');
    el.innerHTML =
        '<div class="gov-stat-row"><span>Eligible (&ge;&#8377;5 Cr)</span><strong>' + (data && data.total != null ? data.total : 0) + '</strong></div>' +
        '<div class="gov-stat-row"><span>Submitted</span>' + ragBadge('GREEN', (data && data.submitted != null ? data.submitted : 0) + ' cases') + '</div>' +
        '<div class="gov-stat-row"><span>Pending</span>' + ragBadge(data && data.pending > 0 ? 'AMBER' : 'GREEN', (data && data.pending != null ? data.pending : 0) + ' cases') + '</div>' +
        '<div class="gov-table-wrap" style="margin-top:12px;">' +
        '<table class="gov-table"><thead><tr><th>Case ID</th><th>Borrower</th><th>Exposure</th><th>SMA</th><th>Quarter</th><th>Status</th></tr></thead>' +
        '<tbody>' + (rows || '<tr><td colspan="6" class="empty-state">No CRILC eligible cases</td></tr>') + '</tbody></table></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderModelInventoryCard(inv) {
    const el = document.getElementById('govModelInventory');
    if (!el || !inv) return;
    el.innerHTML =
        '<div class="gov-inv-row"><span>Model ID</span><strong>' + (inv.model_id || '&mdash;') + '</strong></div>' +
        '<div class="gov-inv-row"><span>Status</span>' + ragBadge(inv.status, inv.status) + '</div>' +
        '<div class="gov-inv-row"><span>Risk Rating</span>' + ragBadge(inv.model_risk_rating, inv.model_risk_rating) + '</div>' +
        '<div class="gov-inv-row"><span>Model Owner</span>' + (inv.model_owner || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>RMCB Resolution</span>' + (inv.rmcb_resolution_no || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>Last Validated</span>' + (inv.last_validation_date || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>Next Validation</span><strong>' + (inv.next_validation_due || '&mdash;') + '</strong></div>';
}

async function showExplanationModal(caseId) {
    if (!caseId) { showToast('No case ID available'); return; }
    const modal = document.getElementById('modalExplanation');
    if (!modal) return;
    document.getElementById('explanationCaseId').textContent = caseId;
    document.getElementById('explanationBody').innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    modal.style.display = 'flex';
    try {
        const res = await fetch('/api/applications/' + caseId + '/explanation');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const improve = (data.what_can_improve || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const supp = (data.supporting_reasons || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const dc = data.decision && data.decision.indexOf('REJECT') >= 0 ? 'RED' :
            data.decision && data.decision.indexOf('CONDITIONAL') >= 0 ? 'AMBER' : 'GREEN';
        document.getElementById('explanationBody').innerHTML =
            '<div class="exp-decision">' + ragBadge(dc, data.decision || '&mdash;') + '</div>' +
            '<div class="exp-section"><div class="exp-label">Primary Reason</div><div class="exp-text">' + (data.primary_reason || '&mdash;') + '</div></div>' +
            (supp ? '<div class="exp-section"><div class="exp-label">Supporting Factors</div><ul class="exp-list">' + supp + '</ul></div>' : '') +
            (improve ? '<div class="exp-section"><div class="exp-label">How to Improve Your Application</div><ul class="exp-list imp-list">' + improve + '</ul></div>' : '') +
            '<div class="exp-footer">' +
            '<span>Score: <strong>' + (data.credit_score != null ? data.credit_score : '&mdash;') + '</strong></span>' +
            '<span>Band: <strong>' + (data.risk_band || '&mdash;') + '</strong></span>' +
            '<span>Model: <strong>' + (data.model_version || 'v4.3') + '</strong></span>' +
            '</div>';
    } catch (e) {
        document.getElementById('explanationBody').innerHTML =
            '<div style="color:#ef4444">&#9888; ' + (e.message || 'Unable to generate explanation') + '</div>';
    }
}

async function triggerRetraining() {
    try {
        const r = await fetch('/api/layer8/trigger-retraining', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trigger: 'MANUAL', details: { initiated_by: 'dashboard' } })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('Retraining event logged. ID: ' + d.retrain_id);
        loadGovernance();
    } catch (e) { showToast('Failed: ' + (e.message || 'error')); }
}

async function runIMV() {
    showToast('Running IMV check...');
    try {
        const r = await fetch('/api/layer8/run-imv', { method: 'POST' });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('IMV complete: ' + d.report.overall_status);
        loadGovernance();
    } catch (e) { showToast('IMV failed: ' + (e.message || 'error')); }
}

function renderGovernancePlaceholder() {
    ['govPanel1', 'govPanel2', 'govPanel3', 'govPanel4', 'govPanel5', 'govPanel6'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="empty-state">Loading governance data...</div>';
    });
}

// ─── Generate Real Metrics Handler ─────────────────────────────
async function generateRealMetrics() {
    const btn = document.getElementById('btnGenerateMetrics');
    if (!btn) return;

    btn.disabled = true;
    const originalText = btn.innerHTML;
    btn.innerHTML = '⚙️ Generating...';

    try {
        const res = await fetch('/api/layer8/generate-metrics', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await res.json();

        if (res.ok && result.status === 'success') {
            showToast('✅ ' + result.message);
            // Refresh the entire governance section to show the new real data
            loadGovernance();
        } else {
            showToast('❌ Error: ' + (result.error || 'Failed to generate metrics'));
        }
    } catch (e) {
        showToast('❌ Network error generating metrics');
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}


// ═══════════════════════════════════════════════════════
//  LAYER 8 — GOVERNANCE, MONITORING & COMPLIANCE
// ═══════════════════════════════════════════════════════

async function loadGovernance() {
    try {
        const res = await fetch('/api/layer8/dashboard-data');
        if (!res.ok) throw new Error('API error ' + res.status);
        const data = await res.json();
        renderGovernancePanel1(data.panel1_model_health);
        renderGovernancePanel2(data.panel2_psi_drift);
        renderGovernancePanel3(data.panel3_override_patterns);
        renderGovernancePanel4(data.panel4_sma_dashboard);
        renderGovernancePanel5(data.panel5_retraining);
        renderGovernancePanel6(data.panel6_crilc);
        renderModelInventoryCard(data.model_inventory);
    } catch (e) {
        console.error('Governance load error:', e);
        renderGovernancePlaceholder();
    }
}

function ragBadge(status, text) {
    const map = {
        GREEN: 'gov-badge-green', AMBER: 'gov-badge-amber', RED: 'gov-badge-red',
        PASS: 'gov-badge-green', FAIL: 'gov-badge-red', GREY: 'gov-badge-grey',
        LIVE: 'gov-badge-green', SHADOW: 'gov-badge-amber', RETIRED: 'gov-badge-grey',
        HIGH: 'gov-badge-red', MEDIUM: 'gov-badge-amber', LOW: 'gov-badge-green',
        WATCH: 'gov-badge-amber', ALERT: 'gov-badge-amber', CRITICAL: 'gov-badge-red', NPA: 'gov-badge-red'
    };
    const cls = map[status] || 'gov-badge-grey';
    return '<span class="gov-badge ' + cls + '">' + (text || status) + '</span>';
}

function renderGovernancePanel1(m) {
    const el = document.getElementById('govPanel1');
    if (!el || !m) return;
    el.innerHTML = '<div class="gov-metrics-grid">' +
        '<div class="gov-metric-card"><div class="gov-metric-label">AUC-ROC</div><div class="gov-metric-value">' + (m.auc_roc != null ? m.auc_roc : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.75 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">KS Statistic</div><div class="gov-metric-value">' + (m.ks_statistic != null ? m.ks_statistic : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.40 ' + ragBadge(m.ks_status || 'GREY', m.ks_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Gini Coefficient</div><div class="gov-metric-value">' + (m.gini_coefficient != null ? m.gini_coefficient : '&mdash;') + '</div><div class="gov-metric-sub">Target &ge; 0.50 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">F1 Score</div><div class="gov-metric-value">' + (m.f1_score != null ? m.f1_score : '&mdash;') + '</div><div class="gov-metric-sub">Prec: ' + (m.precision || '&mdash;') + ' | Rec: ' + (m.recall || '&mdash;') + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Brier Score</div><div class="gov-metric-value">' + (m.brier_score != null ? m.brier_score : '&mdash;') + '</div><div class="gov-metric-sub">&le; 0.15 ideal ' + ragBadge(m.brier_status || 'GREY', m.brier_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Sample Size</div><div class="gov-metric-value">' + (m.sample_size != null ? m.sample_size : 0) + '</div><div class="gov-metric-sub">' + (m.period || '&mdash;') + (m.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div></div>' +
        '</div>';
}

function renderGovernancePanel2(drift) {
    const el = document.getElementById('govPanel2');
    if (!el) return;
    const features = drift && drift.features ? drift.features : [];
    const ov = drift && drift.overall_status ? drift.overall_status : 'GREY';
    const rows = features.map(function (f) {
        const rc = f.status === 'RED' ? 'psi-row-red' : f.status === 'AMBER' ? 'psi-row-amber' : '';
        return '<tr class="' + rc + '"><td><code>' + f.feature + '</code></td><td><strong>' + f.psi + '</strong></td><td>' +
            ragBadge(f.status, f.status) + '</td><td>' + (f.ref_count != null ? f.ref_count : '&mdash;') +
            '</td><td>' + (f.cur_count != null ? f.cur_count : '&mdash;') + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="gov-drift-summary">Overall: ' + ragBadge(ov, ov) +
        ' &nbsp;&#128308; <strong>' + (drift && drift.red_count != null ? drift.red_count : 0) + '</strong>' +
        ' &nbsp;&#128993; <strong>' + (drift && drift.amber_count != null ? drift.amber_count : 0) + '</strong>' +
        ' &nbsp;&#128994; <strong>' + (drift && drift.green_count != null ? drift.green_count : 0) + '</strong>' +
        (drift && drift.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div>' +
        '<div class="gov-table-wrap"><table class="gov-table"><thead><tr><th>Feature</th><th>PSI</th><th>Status</th><th>Ref N</th><th>Cur N</th></tr></thead><tbody>' +
        (rows || '<tr><td colspan="5" class="empty-state">No drift data yet</td></tr>') +
        '</tbody></table></div>';
}

function renderGovernancePanel3(data) {
    const el = document.getElementById('govPanel3');
    if (!el) return;
    const decisions = data && data.decisions ? data.decisions : {};
    const total = data && data.total_decisions ? data.total_decisions : 0;
    const ovr = data && data.override_rate_pct ? data.override_rate_pct : 0;
    const bars = Object.entries(decisions).map(function (entry) {
        const lbl = entry[0], cnt = entry[1];
        const pct = total ? Math.round(cnt / total * 100) : 0;
        const col = lbl === 'REJECT' ? '#ef4444' : lbl.indexOf('CONDITIONAL') >= 0 ? '#f59e0b' : '#10b981';
        return '<div class="gov-bar-row"><span class="gov-bar-label">' + lbl + '</span>' +
            '<div class="gov-bar-track"><div class="gov-bar-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
            '<span class="gov-bar-pct">' + cnt + ' (' + pct + '%)</span></div>';
    }).join('');
    const ovrStatus = ovr > 35 ? 'RED' : ovr > 20 ? 'AMBER' : 'GREEN';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Total Decisions</span><strong>' + total + '</strong></div>' +
        '<div class="gov-stat-row"><span>Override Rate</span><strong>' + ovr + '%</strong> ' + ragBadge(ovrStatus, ovrStatus) + '</div>' +
        '<div class="gov-bars">' + (bars || '<div class="empty-state">No decisions yet</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel4(data) {
    const el = document.getElementById('govPanel4');
    if (!el) return;
    const c = data && data.sma_counts ? data.sma_counts : {};
    const cards = [
        { lbl: 'REGULAR', cnt: c.REGULAR != null ? c.REGULAR : 0, cls: 'sma-regular' },
        { lbl: 'SMA-0 (1-30 DPD)', cnt: c['SMA-0'] != null ? c['SMA-0'] : 0, cls: 'sma-0' },
        { lbl: 'SMA-1 (31-60 DPD)', cnt: c['SMA-1'] != null ? c['SMA-1'] : 0, cls: 'sma-1' },
        { lbl: 'SMA-2 (61-90 DPD)', cnt: c['SMA-2'] != null ? c['SMA-2'] : 0, cls: 'sma-2' },
        { lbl: 'NPA (>90 DPD)', cnt: c.NPA != null ? c.NPA : 0, cls: 'sma-npa' },
    ].map(function (cc) {
        return '<div class="sma-card ' + cc.cls + '"><div class="sma-card-count">' + cc.cnt +
            '</div><div class="sma-card-label">' + cc.lbl + '</div></div>';
    }).join('');
    const alerts = (data && data.early_warnings ? data.early_warnings : []).map(function (w) {
        return '<div class="gov-alert-row"><span class="gov-alert-signal">' + w.signal +
            '</span><span>' + w.description + '</span>' + ragBadge(w.severity, w.severity) + '</div>';
    }).join('');
    el.innerHTML = '<div class="sma-cards-grid">' + cards + '</div>' +
        '<div class="gov-section-label" style="margin-top:10px;">Early Warning Signals</div>' +
        '<div class="gov-alerts">' + (alerts || '<div class="empty-state">No active warnings</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel5(data) {
    const el = document.getElementById('govPanel5');
    if (!el) return;
    const history = (data && data.history ? data.history : []).slice(0, 5).map(function (h) {
        const sc = h.status === 'COMPLETED' ? 'gov-badge-green' : h.status === 'INITIATED' ? 'gov-badge-amber' : 'gov-badge-grey';
        const dt = h.created_at ? new Date(h.created_at).toLocaleDateString() : '&mdash;';
        return '<div class="gov-history-row"><span class="gov-history-trigger">' + h.trigger_type +
            '</span><span>' + dt + '</span><span class="gov-badge ' + sc + '">' + h.status + '</span></div>';
    }).join('');
    const nextDue = data && data.next_retrain_due ? new Date(data.next_retrain_due).toLocaleDateString() : '2026-09-01';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Current Model</span><strong>' + (data && data.current_model ? data.current_model : 'XGB_CREDIT_V4.3') + '</strong></div>' +
        '<div class="gov-stat-row"><span>Shadow Mode</span>' + (data && data.shadow_mode_active ? ragBadge('AMBER', 'ACTIVE') : ragBadge('GREEN', 'INACTIVE')) + '</div>' +
        '<div class="gov-stat-row"><span>Next Retrain Due</span><strong>' + nextDue + '</strong></div>' +
        '<div class="gov-stat-row"><span>IMV Due</span><strong>2026-09-01</strong></div>' +
        '<div class="gov-section-label" style="margin-top:12px;">Recent Events</div>' +
        '<div class="gov-history">' + (history || '<div class="empty-state">No retraining events yet</div>') + '</div>' +
        '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">' +
        '<button class="btn btn-outline btn-sm" onclick="triggerRetraining()">&#128260; Trigger Retraining</button>' +
        '<button class="btn btn-outline btn-sm" onclick="runIMV()">&#128203; Run IMV Check</button></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderGovernancePanel6(data) {
    const el = document.getElementById('govPanel6');
    if (!el) return;
    const rows = (data && data.submissions ? data.submissions : []).slice(0, 8).map(function (s) {
        const sc = s.submission_status === 'SUBMITTED' ? 'gov-badge-green' : 'gov-badge-amber';
        return '<tr>' +
            '<td><strong>' + (s.case_id || '&mdash;') + '</strong></td>' +
            '<td>' + (s.borrower_name || '&mdash;') + '</td>' +
            '<td>&#8377;' + (s.outstanding_cr || 0) + ' Cr</td>' +
            '<td>' + (s.sma_status || '&mdash;') + '</td>' +
            '<td>' + (s.quarter || '&mdash;') + '</td>' +
            '<td><span class="gov-badge ' + sc + '">' + (s.submission_status || '&mdash;') + '</span></td>' +
            '</tr>';
    }).join('');
    el.innerHTML =
        '<div class="gov-stat-row"><span>Eligible (&ge;&#8377;5 Cr)</span><strong>' + (data && data.total != null ? data.total : 0) + '</strong></div>' +
        '<div class="gov-stat-row"><span>Submitted</span>' + ragBadge('GREEN', (data && data.submitted != null ? data.submitted : 0) + ' cases') + '</div>' +
        '<div class="gov-stat-row"><span>Pending</span>' + ragBadge(data && data.pending > 0 ? 'AMBER' : 'GREEN', (data && data.pending != null ? data.pending : 0) + ' cases') + '</div>' +
        '<div class="gov-table-wrap" style="margin-top:12px;">' +
        '<table class="gov-table"><thead><tr><th>Case ID</th><th>Borrower</th><th>Exposure</th><th>SMA</th><th>Quarter</th><th>Status</th></tr></thead>' +
        '<tbody>' + (rows || '<tr><td colspan="6" class="empty-state">No CRILC eligible cases</td></tr>') + '</tbody></table></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">&#9888; Demo data</div>' : '');
}

function renderModelInventoryCard(inv) {
    const el = document.getElementById('govModelInventory');
    if (!el || !inv) return;
    el.innerHTML =
        '<div class="gov-inv-row"><span>Model ID</span><strong>' + (inv.model_id || '&mdash;') + '</strong></div>' +
        '<div class="gov-inv-row"><span>Status</span>' + ragBadge(inv.status, inv.status) + '</div>' +
        '<div class="gov-inv-row"><span>Risk Rating</span>' + ragBadge(inv.model_risk_rating, inv.model_risk_rating) + '</div>' +
        '<div class="gov-inv-row"><span>Model Owner</span>' + (inv.model_owner || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>RMCB Resolution</span>' + (inv.rmcb_resolution_no || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>Last Validated</span>' + (inv.last_validation_date || '&mdash;') + '</div>' +
        '<div class="gov-inv-row"><span>Next Validation</span><strong>' + (inv.next_validation_due || '&mdash;') + '</strong></div>';
}

async function showExplanationModal(caseId) {
    if (!caseId) { showToast('No case ID available'); return; }
    const modal = document.getElementById('modalExplanation');
    if (!modal) return;
    document.getElementById('explanationCaseId').textContent = caseId;
    document.getElementById('explanationBody').innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    modal.style.display = 'flex';
    try {
        const res = await fetch('/api/applications/' + caseId + '/explanation');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const improve = (data.what_can_improve || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const supp = (data.supporting_reasons || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const dc = data.decision && data.decision.indexOf('REJECT') >= 0 ? 'RED' :
            data.decision && data.decision.indexOf('CONDITIONAL') >= 0 ? 'AMBER' : 'GREEN';
        document.getElementById('explanationBody').innerHTML =
            '<div class="exp-decision">' + ragBadge(dc, data.decision || '&mdash;') + '</div>' +
            '<div class="exp-section"><div class="exp-label">Primary Reason</div><div class="exp-text">' + (data.primary_reason || '&mdash;') + '</div></div>' +
            (supp ? '<div class="exp-section"><div class="exp-label">Supporting Factors</div><ul class="exp-list">' + supp + '</ul></div>' : '') +
            (improve ? '<div class="exp-section"><div class="exp-label">How to Improve Your Application</div><ul class="exp-list imp-list">' + improve + '</ul></div>' : '') +
            '<div class="exp-footer">' +
            '<span>Score: <strong>' + (data.credit_score != null ? data.credit_score : '&mdash;') + '</strong></span>' +
            '<span>Band: <strong>' + (data.risk_band || '&mdash;') + '</strong></span>' +
            '<span>Model: <strong>' + (data.model_version || 'v4.3') + '</strong></span>' +
            '</div>';
    } catch (e) {
        document.getElementById('explanationBody').innerHTML =
            '<div style="color:#ef4444">&#9888; ' + (e.message || 'Unable to generate explanation') + '</div>';
    }
}

async function triggerRetraining() {
    try {
        const r = await fetch('/api/layer8/trigger-retraining', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trigger: 'MANUAL', details: { initiated_by: 'dashboard' } })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('Retraining event logged. ID: ' + d.retrain_id);
        loadGovernance();
    } catch (e) { showToast('Failed: ' + (e.message || 'error')); }
}

async function runIMV() {
    showToast('Running IMV check...');
    try {
        const r = await fetch('/api/layer8/run-imv', { method: 'POST' });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('IMV complete: ' + d.report.overall_status);
        loadGovernance();
    } catch (e) { showToast('IMV failed: ' + (e.message || 'error')); }
}

function renderGovernancePlaceholder() {
    ['govPanel1', 'govPanel2', 'govPanel3', 'govPanel4', 'govPanel5', 'govPanel6'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="empty-state">Loading governance data...</div>';
    });
}
