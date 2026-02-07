from pathlib import Path

p = Path("src/crashkit/analyze.py")
s = p.read_text(encoding="utf-8")

candidates = [
    'path.open("r", encoding="utf-8")',
    "path.open('r', encoding='utf-8')",
    'path.open("r", encoding="utf-8",',
    "path.open('r', encoding='utf-8',",
]

replaced = False
for old in candidates:
    if old in s:
        if old.endswith(","):
            new = old.replace('encoding="utf-8"', 'encoding="utf-8-sig"').replace("encoding='utf-8'", "encoding='utf-8-sig'")
        else:
            new = old.replace('encoding="utf-8"', 'encoding="utf-8-sig"').replace("encoding='utf-8'", "encoding='utf-8-sig'")
        s = s.replace(old, new)
        replaced = True
        break

if not replaced:
    raise SystemExit("Pattern not found. Open src/crashkit/analyze.py and find the path.open(...encoding=...) line.")

p.write_text(s, encoding="utf-8")
print("patched:", p)
