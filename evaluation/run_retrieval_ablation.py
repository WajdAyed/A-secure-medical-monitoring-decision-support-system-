"""Experiment 3: retrieval-hit ablation for k and PDF chunk size.

This evaluates Experiment 2's retrieval-hit metric; it intentionally does not
claim policy accuracy because that requires the separately run gold-policy test.
"""
from __future__ import annotations
import argparse, csv, os
from pathlib import Path
from evaluation_utils import RESULTS, SEED, seed_everything, write_csv
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--gold',type=Path,default=ROOT/'evaluation'/'gold_policies.csv'); p.add_argument('--output',type=Path,default=RESULTS/'retrieval_ablation_raw.csv'); args=p.parse_args(); seed_everything()
 from langchain_community.document_loaders import PyPDFLoader
 from langchain_text_splitters import RecursiveCharacterTextSplitter
 from langchain_ollama import OllamaEmbeddings
 docs=[]
 for pdf in (ROOT/'RAG'/'guidelines').glob('*.pdf'): docs.extend(PyPDFLoader(str(pdf)).load())
 with args.gold.open(newline='',encoding='utf-8') as h: gold=list(csv.DictReader(h))
 if not gold or any(not r.get('ref_min') or not r.get('ref_max') for r in gold): raise ValueError('Fill evaluation/gold_policies.csv before this experiment')
 embed=OllamaEmbeddings(model='nomic-embed-text',base_url=os.getenv('OLLAMA_BASE_URL','http://127.0.0.1:11434')); rows=[]
 for chunk_size in (500,1000,2000):
  chunks=RecursiveCharacterTextSplitter(chunk_size=chunk_size,chunk_overlap=200).split_documents(docs)
  for k in (1,3,5,10):
   for index, case in enumerate(gold):
    query=f"{case['condition']} age {case['age']} {case['parameter']}"; ranked=sorted(chunks,key=lambda d: -sum(a*b for a,b in zip(embed.embed_query(query),embed.embed_query(d.page_content))))[:k]; text='\n'.join(x.page_content for x in ranked); hit=(str(case['ref_min']) in text and str(case['ref_max']) in text)
    rows.append({'seed':SEED,'case_index':index,'chunk_size_characters':chunk_size,'k':k,'retrieval_hit_at_k':hit})
 write_csv(args.output,rows,list(rows[0])); print(f'Wrote {len(rows)} ablation rows')
if __name__=='__main__': main()
