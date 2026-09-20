"""Create evaluation/results/summary.md solely from existing result CSVs."""
from __future__ import annotations
import csv
from evaluation_utils import RESULTS, FIGURES, seed_everything
def read(name):
 p=RESULTS/name
 return list(csv.DictReader(p.open(encoding='utf-8'))) if p.exists() else []
def main():
 seed_everything(); lines=['# Evaluation summary','','Only measured CSV values are listed; unavailable experiments remain absent.','']
 for name in ('benchmark_comparison_summary.csv','policy_gold_summary.csv'):
  data=read(name)
  if data:
   lines += [f'## {name}','', '| '+' | '.join(data[0])+' |','| '+' | '.join(['---']*len(data[0]))+' |']
   lines += ['| '+' | '.join(str(row.get(k,'')) for k in data[0])+' |' for row in data]+['']
 lines += ['## Figures','']
 for figure in sorted(FIGURES.glob('*.txt')): lines.append(f'- `{figure.with_suffix(".png").name}`: {figure.read_text(encoding="utf-8").strip()}')
 (RESULTS/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(RESULTS/'summary.md')
if __name__=='__main__': main()
