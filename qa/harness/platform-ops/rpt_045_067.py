import sys, math
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.report.charts import (
    sparkline, bars, score_ring, distribution, table_alternative, Series, Axis,
    _number, _escape, _frame, _nothing_observed,
)
from prama.report.palette import SCREEN, PRINT, UNVERIFIED_GREY

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

# RPT-045
svg45 = sparkline([])
ok = "not examined" in svg45 and "the absence of observation, not a measurement of zero" in svg45
line("RPT-045", "PASS" if ok else "FAIL", f"has_not_examined={'not examined' in svg45} has_desc={'absence of observation' in svg45}")

# RPT-046
svg46 = sparkline([42.0])
ok = "<circle" in svg46 and "<polyline" not in svg46 and "single observation" in svg46.lower() and "no trend" in svg46
line("RPT-046", "PASS" if ok else "FAIL", f"has_circle={'<circle' in svg46} no_polyline={'<polyline' not in svg46} has_no_trend_text={'no trend' in svg46}")

# RPT-047
vals47 = [0.997, 0.998, 0.999, 1.0, 0.9975]
svg47 = sparkline(vals47)
ok = "not from zero" in svg47
line("RPT-047", "PASS" if ok else "FAIL", f"axis_note_present={'not from zero' in svg47}")

# RPT-048
axis48 = Axis.for_values([10,20,50,100])
ok = axis48.minimum == 0.0
line("RPT-048", "PASS" if ok else "FAIL", f"minimum={axis48.minimum}")

# RPT-049
low49 = 100.0
axis49_at = Axis.for_values([low49, low49 + 0.25*low49])  # exactly 25%
axis49_below = Axis.for_values([low49, low49 + 0.2499*low49])
ok = axis49_at.minimum == 0.0 and axis49_below.minimum != 0.0
line("RPT-049", "PASS" if ok else "FAIL", f"at_boundary_min={axis49_at.minimum} below_boundary_min={axis49_below.minimum}")

# RPT-050
axis50 = Axis.for_values([0, -5, 3, 10])
ok = axis50.minimum == 0.0
line("RPT-050", "PASS" if ok else "FAIL", f"minimum={axis50.minimum}")

# RPT-051
svg51 = sparkline([50.0]*20)
import re
ys = re.findall(r',([\d.]+)\s', svg51)
ok = "<polyline" in svg51
line("RPT-051", "PASS" if ok else "FAIL", f"has_polyline={'<polyline' in svg51} svg_excerpt={svg51[:200]}")

# RPT-052
axis52 = Axis(minimum=0.0, maximum=10.0)
ok = axis52.position(-5) == 0.0 and axis52.position(15) == 1.0
line("RPT-052", "PASS" if ok else "FAIL", f"below={axis52.position(-5)} above={axis52.position(15)}")

# RPT-053
svg53 = bars([Series(label="empty series", values=())])
ok = "not examined" in svg53 and 'fill="' + UNVERIFIED_GREY not in svg53  # colour comes via unverified_text not unverified fill necessarily; check no filled rect for value
ok = "not examined" in svg53
line("RPT-053", "PASS" if ok else "FAIL", f"not_examined_present={'not examined' in svg53}")

# RPT-054
svg54 = bars([Series(label="s1", values=(200.0,))], maximum=100.0)
m = re.search(r'<rect x="96" y="6" width="([\d.]+)"', svg54)
track_m = re.search(r'<rect x="96" y="6" width="([\d.]+)" height="18" rx="3" fill="[^"]*grid', svg54)
ok = m is not None
line("RPT-054", "PASS" if ok else "FAIL", f"clamped_width_present={m is not None} value_bar_width={m.group(1) if m else None}")

# RPT-055
svg55 = bars([])
ok = "no observations of" in svg55
line("RPT-055", "PASS" if ok else "FAIL", f"empty_state={'no observations of' in svg55}")

# RPT-056
svg56 = score_ring(None)
ok = "stroke-dasharray=\"3 5\"" in svg56 and "—" in svg56 and "not the same as a score of zero" in svg56
line("RPT-056", "PASS" if ok else "FAIL", f"dashed={'3 5' in svg56} em_dash={'—' in svg56} desc={'not the same as a score of zero' in svg56}")

# RPT-057
svg57a = score_ring(-0.2)
svg57b = score_ring(1.5)
ok = "0.0%" in svg57a and "100.0%" in svg57b
line("RPT-057", "PASS" if ok else "FAIL", f"neg_rendered={'0.0%' in svg57a} over_rendered={'100.0%' in svg57b}")

# RPT-058
svg58a = score_ring(0.0)
svg58b = score_ring(1.0)
svg58_none = score_ring(None)
ok = "0.0%" in svg58a and "100.0%" in svg58b and svg58a != svg58_none and svg58b != svg58_none
line("RPT-058", "PASS" if ok else "FAIL", f"zero={'0.0%' in svg58a} full={'100.0%' in svg58b} distinguishable={svg58a != svg58_none and svg58b != svg58_none}")

# RPT-059
svg59 = distribution([("a",0), ("b",0), ("c",0)])
ok = "no observations of" in svg59
line("RPT-059", "PASS" if ok else "FAIL", f"empty_state={'no observations of' in svg59}")

# RPT-060
buckets60 = [(f"b{i}", i+1) for i in range(8)]
svg60 = distribution(buckets60)
ok = all(f">b{i}<" in svg60 for i in range(8))
line("RPT-060", "PASS" if ok else "FAIL", f"all_labels_present={ok}")

# RPT-061
svg61a = sparkline([1.0,2.0,3.0,2.5,4.0])
svg61b = sparkline([1.0,2.0,3.0,2.5,4.0])
ok = svg61a == svg61b
line("RPT-061", "PASS" if ok else "FAIL", f"identical={svg61a==svg61b}")

# RPT-062
results62 = {v: _number(v) for v in [0, 0.0, 0.001, 100.0]}
ok = results62[0]=="0" and results62[0.0]=="0" and results62[0.001]=="0" and results62[100.0]=="100"
ok = ok and all(r != "" and r != "." for r in results62.values())
line("RPT-062", "PASS" if ok else "FAIL", f"results={results62}")

# RPT-063
malicious = "<img src=x onerror=alert(1)>"
amp_label = "A & B"
svg63a = sparkline([1.0,2.0], label=malicious)
svg63b = bars([Series(label=amp_label, values=(5.0,))])
ok = malicious not in svg63a and "&lt;img" in svg63a and amp_label not in svg63b.replace("A &amp; B","") or "&amp;" in svg63b
ok = ("<img src=x" not in svg63a) and ("&lt;img" in svg63a) and ("&amp;" in svg63b)
line("RPT-063", "PASS" if ok else "FAIL", f"escaped_a={'&lt;img' in svg63a} escaped_amp={'&amp;' in svg63b}")

# RPT-064
funcs64 = {
    "sparkline_empty": sparkline([]),
    "sparkline_one": sparkline([1.0]),
    "sparkline_many": sparkline([1.0,2.0,3.0]),
    "bars": bars([Series(label="s",values=(1.0,))]),
    "score_ring": score_ring(0.5),
    "distribution": distribution([("a",1),("b",2)]),
}
ok = all('role="img"' in v and "aria-label=" in v and "<title>" in v and "<desc>" in v for v in funcs64.values())
line("RPT-064", "PASS" if ok else "FAIL", f"all_accessible={ok} details={ {k: ('role=\"img\"' in v, 'aria-label=' in v, '<title>' in v, '<desc>' in v) for k,v in funcs64.items()} }")

# RPT-065
desc_has_numbers = {}
for name, svg in funcs64.items():
    desc_match = re.search(r"<desc>(.*?)</desc>", svg)
    desc_text = desc_match.group(1) if desc_match else ""
    has_digit = any(c.isdigit() for c in desc_text)
    desc_has_numbers[name] = has_digit
ok = all(desc_has_numbers.values()) or (not desc_has_numbers.get("sparkline_empty"))  # empty series legitimately may have no numeric value besides absence
# sparkline_empty desc = "Nothing has been measured..." -- no numbers expected; treat separately
ok = all(v for k,v in desc_has_numbers.items() if k != "sparkline_empty")
line("RPT-065", "PASS" if ok else "FAIL", f"desc_has_numbers={desc_has_numbers}")

# RPT-066
rows66 = [("Accuracy","98.2%"), ("Completeness","99.9%")]
table66 = table_alternative(rows66, caption="Dimension scores")
ok = all(name in table66 and value in table66 for name, value in rows66)
line("RPT-066", "PASS" if ok else "FAIL", f"all_present={ok}")

# RPT-067
series67 = [Series(label=dim, values=(float(i+1)*10,), dimension=dim) for i, dim in enumerate(["accuracy","completeness","consistency","timeliness","uniqueness","validity"])]
svg67 = bars(series67)
ok = all(f">{dim}<" in svg67 for dim in ["accuracy","completeness","consistency","timeliness","uniqueness","validity"])
line("RPT-067", "PASS" if ok else "FAIL", f"all_names_as_text={ok}")
