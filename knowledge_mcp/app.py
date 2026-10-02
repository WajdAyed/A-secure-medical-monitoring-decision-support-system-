import os
from fastapi import FastAPI, Request
from pathlib import Path
from cdss_rpc import MCPJsonRpcServer

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

app = FastAPI(
    title="Knowledge MCP - RAG"
)
rpc = MCPJsonRpcServer("knowledge-mcp")


DB_DIR = Path(os.getenv("KNOWLEDGE_CHROMA_DIR", Path(__file__).resolve().parent / "chroma_db"))


print("\n" + "=" * 70)
print("INITIALIZING KNOWLEDGE MCP")
print("=" * 70)

print("ChromaDB directory:")
print(DB_DIR)


embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url=OLLAMA_BASE_URL
)


print("\nEmbedding model:")
print("nomic-embed-text")

print("Ollama endpoint:")
print(OLLAMA_BASE_URL)


db = Chroma(
    persist_directory=str(DB_DIR),
    embedding_function=embeddings
)


print("\n✅ ChromaDB loaded")
print("=" * 70)



@rpc.tool("search_guidelines", "Retrieve the most relevant clinical guideline passages.", {
    "type": "object", "properties": {"condition": {"type": "string"}, "query": {"type": "string"}, "k": {"type": "integer", "minimum": 1}}, "required": [],
})
def search_guidelines(condition: str = "", query: str = "", k: int = 3):

    print("\n" + "=" * 70)
    print("KNOWLEDGE MCP - RAG SEARCH")
    print("=" * 70)


    print("Search query:")
    search_text = query.strip() or condition.strip()
    if not search_text:
        return {"error": "condition or query is required"}
    if not isinstance(k, int) or k < 1:
        return {"error": "k must be a positive integer"}
    print(search_text)


    print("\nSearching ChromaDB...")


    try:

        docs = db.similarity_search(
            search_text,
            k=k
        )


    except Exception as e:

        print("\n❌ RAG ERROR")
        print(e)

        print("=" * 70)

        return {
            "error": str(e)
        }



    print("\nDocuments retrieved:")
    print(len(docs))


    for i, doc in enumerate(docs):

        print("\n-----------------------------")
        print("Document", i + 1)

        # only preview, not full medical document
        print(
            doc.page_content[:300]
        )


    print("\n✅ RAG search completed")

    print("=" * 70)



    return {

        "guidelines": [
            d.page_content
            for d in docs
        ],

        # Source metadata lets clients audit retrieval quality without having
        # to infer it from the returned text.  Existing clients can continue
        # to use the ``guidelines`` field unchanged.
        "sources": [
            Path(d.metadata.get("source", "")).name
            for d in docs
        ]

    }


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
