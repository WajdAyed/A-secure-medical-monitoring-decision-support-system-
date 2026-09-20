"""Experiment A: direct coordinator measurements; never imports doctor_console."""
import argparse, json, os, time
from pathlib import Path
import requests
from .config import RESULTS, URLS, TIMEOUT_SECONDS, RETRIES
from .patients import patient_ids

def rpc(patient_id, use_rag=True):
    payload={"jsonrpc":"2.0","id":f"eval-{patient_id}","method":"tools/call","params":{"name":"run_cdss","arguments":{"patient_id":patient_id,"use_rag":use_rag}}}
    last=None
    for _ in range(RETRIES + 1):
        started=time.perf_counter()
        try:
            r=requests.post(URLS["coordinator"]+"/rpc",json=payload,timeout=TIMEOUT_SECONDS); r.raise_for_status()
            result=r.json()["result"]["structuredContent"]
            if "error" in result: raise RuntimeError(result["error"])
            result["client_total_ms"]=(time.perf_counter()-started)*1000
            return result
        except Exception as exc: last=str(exc)
    raise RuntimeError(last)
def healthcheck():
    bad=[]
    for name,url in URLS.items():
        try: requests.get(url,timeout=3)
        except Exception: bad.append(f"{name} ({url})")
    if bad: raise RuntimeError("Required services are down: "+", ".join(bad))
def execute(path, use_rag=True, resume=False):
    if os.getenv("CDSS_EVAL") != "1": raise RuntimeError("Set CDSS_EVAL=1 in every running CDSS service before evaluation.")
    healthcheck(); path.parent.mkdir(parents=True,exist_ok=True)
    done={json.loads(x)["patient_id"] for x in path.read_text().splitlines()} if resume and path.exists() else set()
    with path.open("a",encoding="utf-8") as out:
        for i,pid in enumerate(patient_ids(),1):
            if pid in done: continue
            try: row={"patient_id":pid,"index":i,"use_rag":use_rag,"result":rpc(pid,use_rag)}
            except Exception as exc: row={"patient_id":pid,"index":i,"use_rag":use_rag,"error":str(exc)}
            out.write(json.dumps(row)+"\n"); out.flush()
    rows=[json.loads(x) for x in path.read_text().splitlines()]; failed=[r for r in rows if "error" in r]
    if len(rows)!=200 or failed: raise RuntimeError(f"Invalid run: expected 200, completed {len(rows)}, failed {[x['patient_id'] for x in failed]}")
    return rows
def main():
    p=argparse.ArgumentParser(); p.add_argument("--resume",action="store_true"); a=p.parse_args()
    execute(RESULTS/"main_eval.jsonl", True, a.resume)
if __name__=="__main__": main()
