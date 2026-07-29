#!/usr/bin/env python3
import re, sys

with open('C:/Users/Lenovo/Desktop/hermes/_full.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Read {len(lines)} lines")

# Section markers (line numbers from earlier analysis)
sections = {}
for i, line in enumerate(lines, 1):
    if 'id="cover"' in line: sections['cover'] = i
    elif 'id="bg"' in line: sections['bg'] = i
    elif 'id="questions"' in line: sections['questions'] = i
    elif 'id="roadmap"' in line: sections['roadmap'] = i
    elif 'id="ch1"' in line and 'section' in line: sections['ch1'] = i
    elif 'id="ch2"' in line and 'section' in line: sections['ch2'] = i
    elif 'id="ch3"' in line and 'section' in line: sections['ch3'] = i
    elif 'id="ch4"' in line and ('section' in line or 'container' in line):
        if 'ch4' not in sections: sections['ch4'] = i
    elif 'id="part3"' in line: sections['part3'] = i

for k, v in sorted(sections.items()):
    print(f"{k}: L{v}")

# Find section ends
section_ends = {}
for i, line in enumerate(lines, 1):
    if i in sections.values(): continue
    if '</section>' in line:
        for name, start in sorted(sections.items(), key=lambda x: -x[1]):
            if start < i:
                section_ends[name] = i
                break

for k, v in sorted(section_ends.items()):
    print(f"{k}_end: L{v}")

# Now find special cards inside CH1 and other chapters
# CH1 card titles
print("\n=== CH1 CARDS ===")
for i in range(sections.get('ch1', 0)-1, section_ends.get('ch1', 0)):
    line = lines[i]
    if 'card-title' in line:
        m = re.search(r'<span class="dot">.*?</span>\s*(.*?)</div>', line)
        title = m.group(1)[:80] if m else line.strip()[:80]
        print(f"L{i+1}: {title}")

# CH2 card titles
print("\n=== CH2 CARDS ===")
for i in range(sections.get('ch2', 0)-1, section_ends.get('ch2', 0)):
    line = lines[i]
    if 'card-title' in line:
        m = re.search(r'<span class="dot">.*?</span>\s*(.*?)</div>', line)
        title = m.group(1)[:80] if m else line.strip()[:80]
        print(f"L{i+1}: {title}")

# CH3 card titles
print("\n=== CH3 CARDS ===")
for i in range(sections.get('ch3', 0)-1, section_ends.get('ch3', 0)):
    line = lines[i]
    if 'card-title' in line:
        m = re.search(r'<span class="dot">.*?</span>\s*(.*?)</div>', line)
        title = m.group(1)[:80] if m else line.strip()[:80]
        print(f"L{i+1}: {title}")

# CH4 card titles  
print("\n=== CH4 CARDS ===")
for i in range(sections.get('ch4', 0)-1, section_ends.get('ch4', 0)):
    line = lines[i]
    if 'card-title' in line:
        m = re.search(r'<span class="dot">.*?</span>\s*(.*?)</div>', line)
        title = m.group(1)[:80] if m else line.strip()[:80]
        print(f"L{i+1}: {title}")
