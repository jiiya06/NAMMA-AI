# Runs tests/test_set.csv against the running server and saves results in the test_results table.
import csv, sys, time, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).parent.parent
URL = "http://127.0.0.1:8000/api/chat"
rows = list(csv.DictReader(open(ROOT / "tests" / "test_set.csv", encoding="utf-8")))
conn = sqlite3.connect(ROOT / "chat.db")
passed = 0
for r in rows:
    start = time.time()
    try:
        resp = requests.post(URL, json={"session_id": "test-" + uuid.uuid4().hex, "message": r["query"]}, timeout=40)
        actual = resp.json().get("reply") or resp.json().get("detail", "")
    except Exception as e:
        actual = "ERROR: " + str(e)
    ms = int((time.time() - start) * 1000)
    ok = any(w.lower() in actual.lower() for w in r["expected_contains"].split("|"))
    passed += ok
    conn.execute("INSERT INTO test_results VALUES (?,?,?,?,?,?,?)",
                 (r["id"], datetime.now(timezone.utc).isoformat(timespec="seconds"), r["query"], r["expected_contains"], actual, int(ok), ms))
    conn.commit()
    print(f"{'PASS' if ok else 'FAIL'}  #{r['id']} {r['category']:9} {ms:5} ms  {r['query'][:45]}")
    time.sleep(2)  # stay under free-tier rate limits
print(f"\n{passed}/{len(rows)} passed")
