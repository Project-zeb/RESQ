with open("index.html", "r") as f:
    text = f.read()

# Define boundaries
p1 = text.find("<!-- Health Panel -->")
p2 = text.find("<!-- Active Threat Matrix -->")
p3 = text.find("<!-- Two-Column Wrapper -->")
p4 = text.find('<div class="inner-col-left">')
p4 = text.find('>', p4) + 1  # inner content start
p5 = text.find('<div class="inner-col-right">')
p5 = text.find('>', p5) + 1

health_html = text[p1:p2]
threat_html = text[p2:p3]

# Reconstruct
part1 = text[:p1]
# Then skip to Two column wrapper
wrapper_start = p3
part2 = text[p3:p4]
part3 = text[p4:p5]
part4 = text[p5:]

new_text = part1 + part2 + "\n\n" + health_html + "\n\n" + part3 + "\n\n" + threat_html + "\n\n" + part4

with open("index.html", "w") as f:
    f.write(new_text)
