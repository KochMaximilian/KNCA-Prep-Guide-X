import re, sys, pathlib

# Move the answer line inside the collapsible block and relabel the summary, so both answer and explanation stay hidden.
pattern = re.compile(
    r"\*\*Answer:\s*([A-D])\*\*\s*\n\s*\n<details>\s*\n<summary>Explanation</summary>"
)
replacement = "<details>\n<summary>Answer & explanation</summary>\n\n**Answer: \\1**"

for path in sys.argv[1:]:
    p = pathlib.Path(path)
    text = p.read_text(encoding="utf-8")
    count = len(pattern.findall(text))
    p.write_text(pattern.sub(replacement, text), encoding="utf-8")
    print(f"{path}: rewrote {count} questions")
