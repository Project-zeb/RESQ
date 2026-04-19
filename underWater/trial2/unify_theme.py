import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Remove the entire Weather Bar (Light mode) block
html = re.sub(r'<!-- Weather Bar \(Light mode\) -->.*?</div>\s*</div>\s*</div>', '</div>\n            </div>', html, flags=re.DOTALL)

# Let's just do a simpler python script to replace 'dm-only' with '' and let the CSS hide 'lm-only' globally.
