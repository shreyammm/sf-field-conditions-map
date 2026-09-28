#!/usr/bin/env python3
"""Small final correctness pass for incident UI literals."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "_site" / "index.html"
s = p.read_text(encoding="utf-8")
old = r"if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(String(d||'')))return'';"
new = r"if(!/^\d{4}-\d{2}-\d{2}$/.test(String(d||'')))return'';"
if old not in s:
    raise SystemExit("incident finalization anchor missing: ISO-date regex")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("finalized incident UI date parsing")
