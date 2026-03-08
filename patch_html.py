import sys

html_path = r'c:\Users\saina\Videos\AIML Hack\templates\dashboard.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Add Governance nav entry ──────────────────────────────────────────────
nav_old = '            <a class="nav-item" data-section="roles" onclick="showSection(\'roles\')" id="navRoles" style="display:none;">'
nav_new = nav_old  # keep original

gov_nav = '''
            <a class="nav-item" data-section="governance" onclick="showSection('governance')" id="navGovernance">
                <span class="nav-icon"><i data-lucide="activity"></i></span>
                <span class="nav-label">Governance L8</span>
            </a>'''

MARKER = '        </nav>'
if 'navGovernance' not in content:
    content = content.replace(MARKER, gov_nav + '\n' + MARKER, 1)
    print('Nav added')
else:
    print('Nav already present')

# ── 2. Add explanation modal + governance section before </main> ──────────────
gov_html = '''
        <!-- ═══════════════ SECTION: GOVERNANCE L8 ═══════════════ -->
        <section class="content-section" id="section-governance">
            <!-- Model Health + Inventory -->
            <div style="display:grid;grid-template-columns:1fr 320px;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <div class="card-header">
                        <span class="card-icon" style="background:rgba(99,102,241,0.2);">&#9881;</span>
                        <div><h3>Model Health &mdash; AUC / KS / Gini / Brier</h3>
                        <p style="color:var(--text-secondary);font-size:0.8rem;">RBI MRM metrics</p></div>
                        <button class="btn btn-outline btn-sm" style="margin-left:auto" onclick="loadGovernance()">&#x21BA; Refresh</button>
                    </div>
                    <div id="govPanel1"><div class="empty-state">Loading&hellip;</div></div>
                </div>
                <div class="card">
                    <h3 class="card-title">&#128194; Model Inventory</h3>
                    <div id="govModelInventory"><div class="empty-state">Loading&hellip;</div></div>
                    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
                        <button class="btn btn-outline btn-sm" onclick="showExplanationModal(STATE.currentApp && STATE.currentApp.case_id)">&#128221; Right to Explanation</button>
                        <button class="btn btn-outline btn-sm" onclick="fetch('/api/layer8/quarterly-report').then(function(r){return r.json();}).then(function(d){showToast('Q-Report: '+d.quarter);console.log(d);})">&#128196; Q-Report</button>
                    </div>
                </div>
            </div>
            <!-- PSI Drift + Override Patterns -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <h3 class="card-title">&#127777; PSI Feature Drift &mdash; 25 Features</h3>
                    <div id="govPanel2"><div class="empty-state">Loading&hellip;</div></div>
                </div>
                <div class="card">
                    <h3 class="card-title">&#9878; Override Patterns</h3>
                    <div id="govPanel3"><div class="empty-state">Loading&hellip;</div></div>
                </div>
            </div>
            <!-- SMA Dashboard + Retraining -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <h3 class="card-title">&#128680; SMA / NPA Early Warning Dashboard</h3>
                    <div id="govPanel4"><div class="empty-state">Loading&hellip;</div></div>
                </div>
                <div class="card">
                    <h3 class="card-title">&#128260; Retraining Pipeline Status</h3>
                    <div id="govPanel5"><div class="empty-state">Loading&hellip;</div></div>
                </div>
            </div>
            <!-- CRILC -->
            <div class="card">
                <h3 class="card-title">&#128203; CRILC Submissions (RBI &mdash; Exposures &ge; &#8377;5 Cr)</h3>
                <div id="govPanel6"><div class="empty-state">Loading&hellip;</div></div>
            </div>
        </section>

        <!-- Modal: DPDP Right-to-Explanation -->
        <div class="modal-overlay" id="modalExplanation" style="display:none;">
            <div class="modal" style="max-width:620px;">
                <div class="modal-header">
                    <h3>&#128221; AI Decision Explanation &mdash; DPDP Act 2023</h3>
                    <span class="close" onclick="document.getElementById('modalExplanation').style.display='none'">&times;</span>
                </div>
                <div class="modal-body">
                    <p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:1rem;">
                        Case: <strong id="explanationCaseId">&mdash;</strong> &mdash;
                        Right to Explanation (Sec. 14, DPDP Act 2023)
                    </p>
                    <div id="explanationBody" style="min-height:200px;"></div>
                </div>
            </div>
        </div>
'''

if 'section-governance' not in content:
    content = content.replace('    </main>', gov_html + '\n    </main>', 1)
    print('Governance section added')
else:
    print('Governance section already present')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('dashboard.html patched successfully')
