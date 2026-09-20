"""Experiment C: invoke the Rust executable directly (no HTTP overhead)."""
import json, subprocess, time
from .config import ROOT, RESULTS
def main():
 exe=ROOT/"zkp_engine"/"target"/"release"/("zkp_engine.exe" if __import__('os').name=='nt' else 'zkp_engine'); rows=[]
 for n in [2**i for i in range(10)]:
  for repeat in range(5):
   started=time.perf_counter()
   for _ in range(n): out=subprocess.run([str(exe)],input=json.dumps({"value":120,"min":110,"max":135}),text=True,capture_output=True,check=True).stdout
   data=json.loads(out); elapsed=time.perf_counter()-started
   rows.append({"n":n,"repeat":repeat,"total_ms":elapsed*1000,"proofs_per_second":n/elapsed,**data})
 RESULTS.mkdir(parents=True,exist_ok=True); (RESULTS/'zkp_scalability.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()
