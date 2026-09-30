"""Gate: every span file must rejoin its Source A text byte-for-byte."""
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
raw_a = root / "data" / "raw" / "tafsircenter"
spans_dir = root / "data" / "spans"
ok = True
for span_path in sorted(spans_dir.glob("*.json")):
    payload = json.loads(span_path.read_bytes().decode("utf-8"))
    key = span_path.stem
    src = raw_a / f"{key}.txt"
    src_bytes = src.read_bytes()
    src_text = src_bytes.decode("utf-8")
    joined = "".join(s["text"] for s in payload["spans"])
    joined_bytes = joined.encode("utf-8")
    same_text = joined == src_text
    same_bytes = joined_bytes == src_bytes
    off_ok = all(src_text[s["start"] : s["end"]] == s["text"] for s in payload["spans"])
    sha = hashlib.sha256(src_bytes).hexdigest()
    print(
        f"{key}: spans={len(payload['spans'])} "
        f"rejoin_text={same_text} rejoin_bytes={same_bytes} "
        f"offsets={off_ok} src_sha256={sha}"
    )
    if not (same_text and same_bytes and off_ok):
        ok = False
print("ALL_OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
