from pathlib import Path
import re
import json

js_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink_main.js")
with open(js_path, "r", encoding="utf-8") as f:
    js = f.read()

# Let's find the array of strings. It usually looks like: const _0x1234 = ['...', '...']
# or function _0x1234() { const _0x5678 = [...] }
# Let's search for arrays of strings in hglink_main.js using regex
arrays = re.findall(r"const\s+(_0x[a-f0-9]+)\s*=\s*(\[.*?\]);", js)
print(f"Found {len(arrays)} const array assignments.")

# Let's search for any assignment of an array containing at least 20 elements
large_arrays = []
for m in re.finditer(r"\[\s*(?:'[^']*'|\"[^\"]*\"|`[^`]*`)\s*(?:,\s*(?:'[^']*'|\"[^\"]*\"|`[^`]*`))*\s*\]", js):
    arr_str = m.group(0)
    # Parse as JSON if possible by replacing single quotes and backticks
    # Simple count of commas is easier
    commas = arr_str.count(",")
    if commas > 50:
        print(f"Found large array of length {commas+1} at position {m.start()}:")
        print(arr_str[:300] + " ... " + arr_str[-300:])
        large_arrays.append(arr_str)

# Save large arrays to file to inspect
if large_arrays:
    out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink_large_arrays.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        for idx, arr in enumerate(large_arrays):
            f.write(f"Array {idx+1}:\n{arr}\n\n")
    print(f"Saved large arrays to {out_file}")
