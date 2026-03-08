import ast

files = [
    r'layer8\__init__.py',
    r'layer8\block_a_model_registry.py',
    r'layer8\block_b_performance.py',
    r'layer8\block_c_imv.py',
    r'layer8\block_d_drift.py',
    r'layer8\block_e_fairness.py',
    r'layer8\block_f_npa.py',
    r'layer8\block_g_archive.py',
    r'layer8\block_h_retrain.py',
    r'layer8\block_i_report.py',
    r'layer8\block_j_dashboard.py',
]

print('=== Python Syntax Check ===')
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            src = fh.read()
        ast.parse(src)
        print(f'OK  {f}')
    except SyntaxError as e:
        print(f'ERR {f}: {e}')

print()
print('=== app.py Route Check ===')
with open('app.py', 'r', encoding='utf-8') as fh:
    app_src = fh.read()
routes = [
    '/api/layer8/dashboard-data',
    '/api/layer8/drift-report',
    '/api/layer8/sma-dashboard',
    '/api/applications/<case_id>/explanation',
    '/api/layer8/quarterly-report',
    '/api/layer8/run-imv',
]
for r in routes:
    status = 'OK' if r in app_src else 'MISSING'
    print(f'{status}  {r}')

print()
print('=== HTML Check ===')
with open(r'templates\dashboard.html', 'r', encoding='utf-8') as fh:
    html = fh.read()
checks = {
    'section-governance': 'Governance section',
    'navGovernance': 'Nav entry',
    'modalExplanation': 'Explanation modal',
    'govPanel1': 'Panel 1',
    'govPanel4': 'Panel 4',
}
for key, label in checks.items():
    print(f'{"OK" if key in html else "MISSING"}  {label}')

print()
print('=== JS Check ===')
with open(r'static\js\dashboard.js', 'r', encoding='utf-8') as fh:
    js = fh.read()
for fn in ['loadGovernance', 'ragBadge', 'renderGovernancePanel1', 'triggerRetraining', 'showExplanationModal']:
    print(f'{"OK" if fn in js else "MISSING"}  {fn}()')

print()
print('=== CSS Check ===')
with open(r'static\css\style.css', 'r', encoding='utf-8') as fh:
    css = fh.read()
for cls in ['.gov-badge', '.gov-metrics-grid', '.sma-cards-grid', '.exp-footer']:
    print(f'{"OK" if cls in css else "MISSING"}  {cls}')
