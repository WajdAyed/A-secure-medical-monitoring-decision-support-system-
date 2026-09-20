"""Render saved result files only; this module never calls a CDSS endpoint."""
import json
import matplotlib.pyplot as plt
from .config import RESULTS, FIGURES
def _rows(name): return [json.loads(x) for x in (RESULTS/name).read_text().splitlines() if '"error"' not in x]
def main():
 FIGURES.mkdir(parents=True,exist_ok=True)
 if not (RESULTS/'main_eval.jsonl').exists(): return
 rows=_rows('main_eval.jsonl'); values=[r['result'].get('timings',{}).get('total_ms',r['result'].get('client_total_ms',0)) for r in rows[1:]]
 plt.figure();plt.hist(values,bins=20);plt.xlabel('End-to-end latency (ms)');plt.ylabel('Patients (n=199)');plt.title('A1 End-to-end latency; patient 1 excluded as warm-up');
 for ext in ('png','svg'):plt.savefig(FIGURES/f'A1_latency_histogram.{ext}',dpi=300,bbox_inches='tight')
 plt.close()
if __name__=='__main__':main()
