js_src = r'c:\Users\saina\Videos\AIML Hack\gov_layer8.js'
js_dst = r'c:\Users\saina\Videos\AIML Hack\static\js\dashboard.js'

with open(js_src, 'r', encoding='utf-8') as f:
    gov_content = f.read()

with open(js_dst, 'a', encoding='utf-8') as f:
    f.write('\n\n')
    f.write(gov_content)

print('Governance JS appended to dashboard.js')

# Verify
with open(js_dst, 'r', encoding='utf-8') as f:
    content = f.read()

for fn in ['loadGovernance', 'ragBadge', 'renderGovernancePanel1', 'triggerRetraining', 'showExplanationModal']:
    print(fn + ': ' + ('OK' if fn in content else 'MISSING'))
