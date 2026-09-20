"""Experiment 4: stage timing over 30+ varied local sensor readings."""
from __future__ import annotations
import argparse, json, os, subprocess, time
from pathlib import Path
from evaluation_utils import RESULTS, SEED, seed_everything, write_csv
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--runs',type=int,default=30); p.add_argument('--condition',default='hypertension'); p.add_argument('--age',type=int,default=50); p.add_argument('--rule-url',default=os.getenv('RULE_ENGINE_URL','http://127.0.0.1:8004')); p.add_argument('--knowledge-url',default=os.getenv('KNOWLEDGE_MCP_URL','http://127.0.0.1:8010')); p.add_argument('--decision-url',default=os.getenv('DECISION_AGENT_URL','http://127.0.0.1:8002')); p.add_argument('--engine',type=Path,default=ROOT/'zkp_engine'/'target'/'release'/('zkp_engine.exe' if os.name=='nt' else 'zkp_engine')); args=p.parse_args()
    if args.runs<30: p.error('--runs must be at least 30')
    if not args.engine.is_file(): raise FileNotFoundError(args.engine)
    seed_everything(); rows=[]
    for mode,use_rag in (('no_rag',False),('rag',True)):
      for run in range(args.runs):
        sensor_value=70+(run*17%131); start=time.perf_counter(); retrieval=0.
        try:
          if use_rag:
            began=time.perf_counter(); call_tool(args.knowledge_url,'search_guidelines',{'query':args.condition,'k':3},timeout=60); retrieval=(time.perf_counter()-began)*1000
          began=time.perf_counter(); policy=call_tool(args.rule_url,'generate_policy',{'patient':{'id':'latency','condition':args.condition,'age':args.age},'use_rag':use_rag},timeout=180); generation=(time.perf_counter()-began)*1000
          began=time.perf_counter(); proof=json.loads(subprocess.run([str(args.engine)],input=json.dumps({'value':sensor_value,'min':int(policy['min']),'max':int(policy['max'])}),text=True,capture_output=True,check=True).stdout); proof_ms=(time.perf_counter()-began)*1000
          began=time.perf_counter(); call_tool(args.decision_url,'evaluate_decision',{'status':proof['status']},timeout=30); decision=(time.perf_counter()-began)*1000; error=''
        except Exception as exc: generation=proof_ms=decision=0.; error=str(exc)
        rows.append({'seed':SEED,'mode':mode,'run':run+1,'sensor_value_local_only':sensor_value,'retrieval_ms':round(retrieval,4),'generation_ms':round(generation,4),'proof_ms':round(proof_ms,4),'decision_ms':round(decision,4),'end_to_end_ms':round((time.perf_counter()-start)*1000,4),'error':error})
    write_csv(RESULTS/'latency_raw.csv',rows,list(rows[0])); print(f'Wrote {len(rows)} raw timings')
if __name__=='__main__': main()
