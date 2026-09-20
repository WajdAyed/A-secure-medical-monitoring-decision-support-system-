"""Experiment B paired and interleaved direct coordinator evaluation."""
import argparse, json, os, time
from .config import RESULTS
from .patients import patient_ids
from .run_main_eval import healthcheck, rpc
def main():
 p=argparse.ArgumentParser();p.add_argument("--resume",action="store_true");a=p.parse_args(); path=RESULTS/"rag_vs_norag.jsonl"
 if os.getenv("CDSS_EVAL")!="1": raise RuntimeError("CDSS_EVAL=1 is required.")
 healthcheck(); done={(json.loads(x)["patient_id"],json.loads(x)["use_rag"]) for x in path.read_text().splitlines()} if a.resume and path.exists() else set(); path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("a",encoding="utf-8") as f:
  for index,pid in enumerate(patient_ids(),1):
   order=[True,False] if index%2 else [False,True]
   for use_rag in order:
    if (pid,use_rag) in done: continue
    started=time.perf_counter()
    try: row={"patient_id":pid,"index":index,"use_rag":use_rag,"run_order":order.index(use_rag)+1,"result":rpc(pid,use_rag),"loop_elapsed_ms":(time.perf_counter()-started)*1000}
    except Exception as e: row={"patient_id":pid,"index":index,"use_rag":use_rag,"error":str(e)}
    f.write(json.dumps(row)+"\n");f.flush()
 rows=[json.loads(x) for x in path.read_text().splitlines()]
 if len(rows)!=400 or any("error" in x for x in rows): raise RuntimeError("Invalid paired run: both conditions require 200 successful patients.")
if __name__=="__main__":main()
