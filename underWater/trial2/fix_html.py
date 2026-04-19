import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace the search box section to match LM design
with open('old_index.html', 'r', encoding='utf-8') as f:
    old_html = f.read()

# I will just extract old map view and weather bar if they are there, or reconstruct manually.
