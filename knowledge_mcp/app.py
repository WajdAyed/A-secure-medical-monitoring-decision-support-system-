from fastapi import FastAPI
from pathlib import Path

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings


app = FastAPI(
    title="Knowledge MCP - RAG"
)


DB_DIR = Path(__file__).parent / "chroma_db"


print("\n" + "=" * 70)
print("INITIALIZING KNOWLEDGE MCP")
print("=" * 70)

print("ChromaDB directory:")
print(DB_DIR)


embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://127.0.0.1:11434"
)


print("\nEmbedding model:")
print("nomic-embed-text")

print("Ollama endpoint:")
print("http://127.0.0.1:11434")


db = Chroma(
    persist_directory=str(DB_DIR),
    embedding_function=embeddings
)


print("\n✅ ChromaDB loaded")
print("=" * 70)



@app.get("/guidelines/{condition}")
def search_guidelines(condition: str):

    print("\n" + "=" * 70)
    print("KNOWLEDGE MCP - RAG SEARCH")
    print("=" * 70)


    print("Search query:")
    print(condition)


    print("\nSearching ChromaDB...")


    try:

        docs = db.similarity_search(
            condition,
            k=3
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
        ]

    }