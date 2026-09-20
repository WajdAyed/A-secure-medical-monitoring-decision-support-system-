"""Ordered, resumable entry point. May be launched from any directory."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def main():
 for module,args in [('evaluation.run_main_eval',['--resume']),('evaluation.run_rag_vs_norag',['--resume']),('evaluation.run_zkp_scalability',[]),('evaluation.run_robustness',[]),('evaluation.make_figures',[])]:
  subprocess.run([sys.executable,'-m',module,*args],check=True,cwd=ROOT)
if __name__=='__main__':main()
