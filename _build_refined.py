#!/usr/bin/env python3
"""Extract refined version of the mid-term defense HTML."""
import re

with open('C:/Users/Lenovo/Desktop/hermes/_full.html', 'r', encoding='utf-8') as f:
    all_lines = f.readlines()

lines = [l.rstrip('\n') for l in all_lines]
print(f"Total: {len(lines)} lines")

# ====== KEY LINE RANGES ======
# CSS: L1-L298 | Nav: L303-L316 | Cover: L319-L337
# bg: L338-L381 | questions: L384-L420 | roadmap: L423-L625
# ch1: L629-L1375 | ch2: L1378-L1648 | ch3: L1650-L2000
# ch4: L2003-L2555 | part3: L2558-L3090 | plotly scripts: L3105-L3177

# Build new file
out = []

def add_raw(start, end):
    """Add lines start to end (1-indexed)"""
    for i in range(start-1, min(end, len(lines))):
        out.append(lines[i])

def add_raw_list(ranges):
    for s, e in ranges:
        add_raw(s, e)

# ====== HEAD + CSS ======
add_raw(1, 302)

# ====== SIMPLIFIED NAV ======
out.append("""<nav class="top-nav">
  <a href="#cover">封面</a>
  <a href="#questions">科学问题</a>
  <a href="#roadmap">路线</a>
  <a href="#ch1">CH1 光热</a>
  <a href="#ch2">CH2 低温</a>
  <a href="#ch3">CH3 循环</a>
  <a href="#ch4">CH4 水热</a>
  <a href="#part3">综合讨论</a>
  <a href="#ai">iMAR系统</a>
</nav>""")

# ====== COVER ======
add_raw(319, 337)

# ====== SCIENCE QUESTIONS ======
add_raw(384, 420)

# ====== ROADMAP (already refined) ======
add_raw(423, 625)

# ====== CH1 - 4 CHAPTERS ======
# For each chapter, keep: section header + key cards with charts + mechanism diagrams

# ---- CH1: Keep core comparison + 力学性能 charts + gradient OIT + key conclusions ----
add_raw(629, 637)    # section header
add_raw_list([       # key cards
    (638, 695),      # 2.1.1 三种PPR户外老化对比 (comparison grid + key results)
    (696, 732),      # OIT衰减趋势 chart (keep chart + data table)
    (733, 734),      # close card
    (750, 776),      # 2.1.1B section header + summary bar + stat row
    (777, 798),      # 断裂伸长率+强度 charts
    (799, 816),      # 屈服强度+伸长率 charts
    (817, 835),      # 屈服韧性+断裂韧性 charts + footnote
    (836, 848),      # 悬崖式衰退 chart + alert
    (849, 854),      # 雷达图 + footnote
    (855, 870),      # 通水vs不通水 chart + alerts
    (871, 880),      # 双层热力图 + alert
    (881, 900),      # 关联模型
    (999, 1000),     # - empty line separator
    (1000, 1057),    # 2.1.2 梯度老化 + 四级预警 + gradient chart + 大结论
    (1058, 1073),    # 风险点
    (1074, 1098),    # 2.1.3 氙灯加速
    (1099, 1375),    # 2.1.4 其他管材 + SVG机理图
])

# ---- CH2: Keep ranking + Tg mechanism + OD data + SVG ----
add_raw(1378, 1384)  # section header
add_raw_list([
    (1385, 1420),    # 2.2.1 实验设计 + 排名 + stat-row
    (1421, 1437),    # 2.2.2 Tg机理
    (1438, 1648),    # 2.2.3 OD数据 + SVG机理图
])

# ---- CH3: Keep key finding + model + validation + SVG ----
add_raw(1650, 1656)  # section header
add_raw_list([
    (1657, 1678),    # 2.3.1 工程需求 + table
    (1679, 1739),    # 2.3.2 关键发现 + correlation chart + 4 cards
    (1740, 1996),    # 2.3.3 model + 2.3.4 validation + SVG
])

# ---- CH4: Keep material selection + pre-experiment + life prediction + SVG ----
add_raw(2003, 2010)
add_raw_list([
    (2011, 2101),    # 2.4.1 PFAS + 2.4.2 material selection + comparison table + conclusion
    (2102, 2138),    # 2.4.3 pre-experiment chart + table + conclusion
    (2139, 2198),    # 2.4.4 formal experiment design
    (2199, 2253),    # 2.4.5 life prediction chart
    (2254, 2555),    # 2.4.6-2.4.7 + SVG
])

# ====== COMPREHENSIVE DISCUSSION ======
add_raw(2558, 2880)  # 四章对比 + 共性规律 + 创新展望 + 成果清单

# ====== 图文摘要 + iMAR ======
add_raw_list([
    (2880, 2897),    # 成果清单 table
    (2899, 2952),    # 图文摘要 4章发现
    (2954, 3090),    # 共性规律 + iMAR
])

# ====== PLOTLY SCRIPTS ======
add_raw(3105, 3177)

# ====== Write output ======
result = "\n".join(out)
with open('C:/Users/Lenovo/Desktop/hermes/博士后中期答辩-精炼版.html', 'w', encoding='utf-8') as f:
    f.write(result)

print(f"Output: {len(result)} chars, {len(out)} lines")
print("Done!")
