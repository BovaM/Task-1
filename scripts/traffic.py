"""Поток запросов из строк датасета для дашборда Grafana.

  uv run python scripts/traffic.py --url http://roi.localhost --rps 5 --bad 0.05
Идёт через Ingress - переживает rollout
"""
import argparse
import json
import random
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://roi.localhost")
parser.add_argument("--rps", type=float, default=5)
parser.add_argument("--bad", type=float, default=0.0)
args = parser.parse_args()


def build_request(path: str, body: bytes) -> urllib.request.Request:
    parts = urlsplit(args.url)
    host = parts.hostname or ""
    target = parts
    if host.endswith(".localhost"):
        port = f":{parts.port}" if parts.port else ""
        target = parts._replace(netloc=f"127.0.0.1{port}")
    url = urlunsplit((target.scheme, target.netloc, path, "", ""))
    return urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "Host": host},
    )


COLS = ["major", "institution_tier", "region", "institution_selectivity_pctile", "had_internship", "gpa", "net_cost_usd"]
df = pd.read_csv("data/college_major_roi.csv")[COLS]
rows = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]
for r in rows:
    r["institution_selectivity_pctile"] = int(r["institution_selectivity_pctile"])
    r["had_internship"] = int(r["had_internship"])
    if r["net_cost_usd"] is not None:
        r["net_cost_usd"] = int(r["net_cost_usd"])

codes: dict[int, int] = {}
start = time.time()
while True:
    row = dict(random.choice(rows))
    if random.random() < args.bad:
        row["gpa"] = -1
    req = build_request("/v1/predict", json.dumps(row).encode())
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, OSError):
        code = 0  # сервис недоступен: под перезапускается
    codes[code] = codes.get(code, 0) + 1
    total = sum(codes.values())
    if total % 50 == 0:
        print(f"{total} запросов за {time.time() - start:.0f} с, коды {codes}", flush=True)
    time.sleep(1 / args.rps)
