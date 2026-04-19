from bs4 import BeautifulSoup
import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

dash_right = soup.find('div', class_='dash-right')

health = dash_right.find('div', class_=re.compile(r'health-card'))
threat = dash_right.find('div', class_=re.compile(r'threat-card'))
inner_left = dash_right.find('div', class_='inner-col-left')
inner_right = dash_right.find('div', class_='inner-col-right')

# Extract health and threat
health.extract()
threat.extract()

# Insert health at top of inner_left
inner_left.insert(0, health)

# Insert threat at top of inner_right
inner_right.insert(0, threat)

# Remove the old split-col-grid wrapper if you want, or just make dash_right the split-col-grid
split_grid = dash_right.find('div', class_='split-col-grid')
# We'll just move inner-col-left and inner-col-right up and delete split-col-grid
split_grid.insert_before(inner_left)
split_grid.insert_before(inner_right)
split_grid.decompose()

# Add split-col-grid class to dash_right
dash_right['class'] = dash_right.get('class', []) + ['split-col-grid']

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(str(soup))
