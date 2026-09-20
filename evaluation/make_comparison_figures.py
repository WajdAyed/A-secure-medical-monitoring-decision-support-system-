"""Comparison figures from saved results only; no CDSS calls are made."""
import csv,json
from pathlib import Path
import numpy as np
from .config import RESULTS,FIGURES,ROOT,SEED
from .ground_truth import ensure_reference_ranges

def rows(): return [json.loads(x) for x in (RESULTS/'rag_vs_norag.jsonl').read_text().splitlines() if '"error"' not in x]
def save(fig,name,data,caption):
 FIGURES.mkdir(exist_ok=True); p=FIGURES/name
 with (RESULTS/f'{name}.csv').open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=data[0].keys());w.writeheader();w.writerows(data)
 for ext in ('png','svg'):fig.savefig(p.with_suffix('.'+ext),dpi=300,bbox_inches='tight')
 p.with_suffix('.txt').write_text(caption,encoding='utf8')
def iou(a,b,c,d):
 union=max(b,d)-min(a,c)
 return max(0,min(b,d)-max(a,c))/union if union else 0
def main():
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 ref=ensure_reference_ranges(); data=rows(); quality=[]
 for r in data:
  x=r['result'];p=x['policy'];q=ref[x['patient']['condition']]; lo,hi=p['min'],p['max'];
  quality.append({'patient_id':r['patient_id'],'use_rag':r['use_rag'],'condition':x['patient']['condition'],'policy_min':lo,'policy_max':hi,'ref_min':q['min'],'ref_max':q['max'],'policy_in_reference':int(q['min']<=lo and hi<=q['max']),'interval_iou':iou(lo,hi,q['min'],q['max']),'within_5':int(abs(lo-q['min'])<=5 and abs(hi-q['max'])<=5)})
 with (RESULTS/'rag_policy_quality_recomputed.csv').open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=quality[0]);w.writeheader();w.writerows(quality)
 # cmp2, one median local pipeline and derived paper segments
 timed=[r for r in data if r['use_rag']]; local=sorted(timed,key=lambda r:r['result']['timings']['total_ms'])[len(timed)//2]; t=local['result']['timings']; stages=[('EMR',t['patient_ms']/1000),('Policy',t['policy_ms']/1000),('ZKP',t['proof_ms']/1000),('Decision',t['decision_ms']/1000)]
 paper=json.loads((ROOT/'evaluation'/'paper_reference.json').read_text())['zk_mcp']['sessions_seconds']; fig,ax=plt.subplots(figsize=(10,4)); out=[]; y=0
 start=0
 for n,v in stages:ax.barh(y,v,left=start,label=n);out.append({'series':'mine','segment':n,'seconds':v});start+=v
 ax.text(start+.1,y,'My median patient');y+=1
 for model,s in paper.items():
  parts=[('execution',s['execution_end']),('prove',s['prove_end']-s['execution_end']),('verify',s['total']-s['prove_end'])];start=0
  for n,v in parts:ax.barh(y,v,left=start,hatch='//',color='#d95f02');out.append({'series':model,'segment':n,'seconds':v});start+=v
  ax.text(start+.1,y,model);y+=1
 ax.set_xlabel('Elapsed time (s)');ax.set_yticks([]);ax.set_title('cmp_2 Timeline vs paper');save(fig,'cmp_2_timeline_vs_paper',out,'Comparable: Partially. One local patient with four stages vs paper sessions with eight MCP tool calls.');plt.close(fig)
 # cmp4
 mine=[]
 for mode in (False,True):
  v=[q['policy_in_reference']*100 for q in quality if q['use_rag']==mode];mine.append(np.mean(v))
 gains=[]
 t3=json.loads((ROOT/'evaluation'/'paper_reference.json').read_text())['rag_mcp'];
 for key,vals in t3['table3_scaling'].items():
  if '/' not in key: continue
  model,dataset=key.split('/');gains.append({'label':key,'gain_pp':vals['single_agent_rag'][4]-t3['table1_accuracy'][model]['baseline'][dataset]})
 mygain=mine[1]-mine[0]; chart=[{'label':'Mine: RAG - no RAG','gain_pp':mygain}]+gains;fig,ax=plt.subplots(figsize=(10,4));ax.bar([x['label'] for x in chart],[x['gain_pp'] for x in chart],color=['#1b9e77']+['#7570b3']*4,hatch=['']+['//']*4);ax.tick_params(axis='x',rotation=18);ax.set_ylabel('Gain (percentage points)');ax.set_title('cmp_4 RAG gain vs paper');save(fig,'cmp_4_rag_gain_vs_paper',chart,'Comparable: No (form only). MCQ accuracy vs safe-range policy-in-reference rate; only direction and gain magnitude are shown.')
 (RESULTS/'comparison_summary.md').write_text('# Comparison summary\n\nFixes applied: interval metrics replace exact bounds; all-condition fallback references are explicitly clinician-review pending.\n\n- cmp_2: partially comparable timelines; workload differs.\n- cmp_4: form-only RAG gain comparison; tasks and metrics differ.\n- cmp_1/cmp_3 skipped: saved 200-patient records do not contain prove/verify timings.\n- cmp_5 skipped: no k sweep.\n- cmp_6 skipped: the Rust engine does not aggregate values.\n',encoding='utf8')
if __name__=='__main__':main()
