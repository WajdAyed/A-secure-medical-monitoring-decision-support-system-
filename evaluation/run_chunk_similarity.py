"""Optional Experiment 5: pairwise cosine similarities among retrieved chunks."""
from __future__ import annotations
import argparse, csv, os
from pathlib import Path
from evaluation_utils import RESULTS, SEED, seed_everything, write_csv
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--queries',type=Path,required=True,help='CSV with a query column'); p.add_argument('--k',type=int,default=3); args=p.parse_args(); seed_everything()
 import numpy as np
 from langchain_chroma import Chroma
 from langchain_ollama import OllamaEmbeddings
 embedding=OllamaEmbeddings(model='nomic-embed-text',base_url=os.getenv('OLLAMA_BASE_URL','http://127.0.0.1:11434')); db=Chroma(persist_directory=str(ROOT/'knowledge_mcp'/'chroma_db'),embedding_function=embedding); rows=[]
 with args.queries.open(newline='',encoding='utf-8') as h: queries=list(csv.DictReader(h))
 for qindex,item in enumerate(queries):
  docs=db.similarity_search(item['query'],k=args.k); vectors=np.array(embedding.embed_documents([d.page_content for d in docs])); vectors=vectors/np.linalg.norm(vectors,axis=1,keepdims=True)
  for i in range(len(docs)):
   for j in range(len(docs)): rows.append({'seed':SEED,'query_index':qindex,'query':item['query'],'chunk_i':i,'chunk_j':j,'cosine_similarity':float(vectors[i]@vectors[j])})
 write_csv(RESULTS/'chunk_similarity_raw.csv',rows,list(rows[0]) if rows else ['seed']); print(f'Wrote {len(rows)} similarities')
if __name__=='__main__': main()
