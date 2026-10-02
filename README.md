# Privacy-Preserving Clinical Decision Support System (CDSS)

A privacy-preserving Clinical Decision Support System that uses Zero-Knowledge Proofs (ZKP) and Retrieval-Augmented Generation (RAG) to provide clinical decisions without exposing sensitive patient data.

## Architecture

```mermaid
flowchart LR
    Doctor --> Coordinator[LangGraph Coordinator]
    Coordinator --> EMR[EMR / patient MCP]
    Coordinator --> Ruler[Ruler Agent / guideline knowledge]
    Coordinator --> Verifier[Hospital ZKP verifier]
    Sensor[Patient-room sensor] --> Prover[Edge commitment and Bulletproof prover]
    Verifier -->|public bounds and nonce| Prover
    Prover -->|commitment and proof| Verifier
    Verifier -->|verification result| Coordinator
    Coordinator -->|range assessment| Doctor
```

## Key Features

- **Privacy-Preserving**: Sensor values never leave the device; only ZKP proofs are shared
- **RAG-Based Guidelines**: Medical guidelines retrieved from PDFs using semantic search
- **LLM-Assisted Ranges**: Uses Ollama LLaMA3 to generate policy ranges from guideline context
- **Zero-Knowledge Proofs**: Rust-based Bulletproofs for range verification
- **LangGraph Workflow**: Orchestrates the entire decision pipeline

## Prerequisites

- Docker and Docker Compose
- Git
- Optional: Python 3.11+ if you want to run the console locally outside Docker
- Optional: Ollama CLI if you want to manage local models manually

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/WajdAyed/Privacy-Preserving-CDSS.git
cd Privacy-Preserving-CDSS
```

### 2. Start the full stack with Docker

From the project root:

```bash
docker compose up --build -d
```

On Windows PowerShell, this is also valid:

```powershell
docker-compose up --build -d
```

This starts all required services from [docker-compose.yml](docker-compose.yml):

- Ollama
- PostgreSQL
- EMR Layer (implemented by the compatibility-named `patient_mcp` service)
- Rule Engine
- Privacy MCP
- Ruler Agent with direct ChromaDB guideline retrieval
- LangGraph Coordinator
- Doctor Console

### 3. Check the running services

```bash
docker compose ps
```

You can verify the main API entrypoints:

```bash
curl http://localhost:8007/docs
curl http://localhost:8005/docs
curl http://localhost:8004/docs
```

### 4. Pull Ollama models (if not already available in the container)

The project expects LLM and embedding models. If needed, run:

```bash
docker exec -it cdss-ollama ollama pull llama3
docker exec -it cdss-ollama ollama pull nomic-embed-text
```

If you are running Ollama outside Docker instead of the containerized service, use:

```bash
ollama pull llama3
ollama pull nomic-embed-text
```

### 5. Build the vector database

The knowledge service uses ChromaDB and embeddings. If the vector database is not initialized yet, run:

```bash
python scripts/build_rag.py
```

This is often needed once on the host machine before using the RAG pipeline.

## Running the System

The Docker-based setup is the recommended way to run the project.

### Start everything

```bash
docker compose up --build -d
```

### Stop everything

```bash
docker compose down
```

### Restart a single service

```bash
docker compose restart langgraph-coordinator
```

### View logs

```bash
docker compose logs -f
```

### Run the doctor console locally against the Docker host

If you want to use the interactive terminal UI from your own machine while the services run in Docker on another host, set the coordinator URL:

```powershell
$env:LANGGRAPH_URL="http://<HOST_IP>:8007"
python doctor_console.py
```

For example:

```powershell
$env:LANGGRAPH_URL="http://192.168.1.50:8007"
python doctor_console.py
```

### Run a test case against the running services

```bash
python langgraph_coordinator/run_case.py
```

If the app is running remotely, set the environment variable first:

```powershell
$env:LANGGRAPH_URL="http://<HOST_IP>:8007"
python langgraph_coordinator/run_case.py
```

## Running from another machine

The Docker host is still the machine running the containers. Another machine cannot directly access the internal service names such as `patient-mcp` or `rule-engine`.

Use the host IP or public IP instead:

```text
http://<HOST_IP>:8007
```

Example:

```text
http://192.168.1.50:8007
```

You must also make sure the following ports are reachable from the network:

- 8003
- 8004
- 8005
- 8006
- 8007
- 11434
- 5432

## Alternative local startup (without Docker)

If you prefer not to use Docker, the project also supports a local setup:

```powershell
# Windows PowerShell
.\run.ps1
```

Or start services individually:

```powershell
.\start.ps1
```

Then launch the console manually:

```bash
python doctor_console.py
```

## Notes

- The Docker Compose configuration is the recommended deployment method.
- Internal container communication uses Docker service names, while external clients must use the host IP and mapped ports.
- The Ollama service is required for both the LLM and embeddings used by the RAG and policy generation components.

## How It Works

### 1. Guidelines Loading and RAG

The system loads medical guidelines from PDFs and creates a vector database for semantic search.

**File**: `knowledge_mcp/build_vector_db.py`

```python
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

# Load PDFs from guidelines directory
PDF_DIR = Path("RAG/guidelines")
documents = []

for pdf in PDF_DIR.glob("*.pdf"):
    loader = PyPDFLoader(str(pdf))
    docs = loader.load()
    documents.extend(docs)

# Split into chunks
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
chunks = splitter.split_documents(documents)

# Create embeddings and store in ChromaDB
embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://127.0.0.1:11434"
)

db = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="knowledge_mcp/chroma_db"
)
```

### 2. Guideline Retrieval

The Ruler Agent opens the local ChromaDB database and searches it directly using the patient's condition. It uses Ollama's `nomic-embed-text` model for the search query. The guidelines are indexed beforehand by `knowledge_mcp/build_vector_db.py`; the Knowledge MCP server is not part of the running workflow.

**File**: `rule_engine/policy_generator.py` (`search_guidelines`)

### 3. Policy Generation with LLM

The Rule Engine uses retrieved guidelines to generate personalized safe limits.

**File**: `rule_engine/policy_generator.py`

```python
import ollama
import json
import re

def generate_policy(patient):
    condition = patient["condition"]
    age = patient["age"]
    
    # Step 1: Retrieve guidelines directly from ChromaDB
    docs = search_guidelines(condition)
    
    # Step 2: Join guidelines into context
    context = "\n\n".join(docs)
    
    # Step 3: Create prompt for LLM
    prompt = f"""
Patient:
Age: {age}
Condition: {condition}

Medical Guidelines:

{context}

Based on the medical guidelines, generate personalized safe limits.
Return ONLY JSON.

Example:
{{
   "parameter":"systolic_bp",
   "min":110,
   "max":135
}}
"""
    
    # Step 4: Call Ollama LLM
    response = ollama.chat(
        model="llama3",
        format="json",
        messages=[{"role":"user", "content":prompt}]
    )
    
    # Step 5: Extract JSON from response
    text = response["message"]["content"]
    match = re.search(r"\{.*\}", text, re.S)
    policy = json.loads(match.group())
    
    return policy
```

### 4. Zero-Knowledge Proof Generation

The device generates a proof that its sensor value is within the allowed range without revealing the actual value.

The LangGraph coordinator sends public integer bounds to `privacy_mcp`. That service calls
the device agent's `prove` RPC with the bounds. `device_agent/app.py` reads a
simulated sensor locally and runs `zkp_engine` with `action: "prove"`. It returns
the Bulletproof, two commitments, a binding proof, and the public bounds. It
never returns the sensor value. The separate server-side process in
`privacy_mcp/zkp_client.py` runs `zkp_engine` with `action: "verify"`, checks that
the returned bounds match the request, and accepts `NORMAL` only after both
cryptographic checks succeed.

The binding proof establishes that the committed nonnegative offsets add up to
`max - min`. An out-of-range reading produces `ALERT` with no proof. The sensor
functions are simulations; a clinical deployment still needs authenticated
sensor input and replay protection. Docker Compose runs the device agent as a
separate service on port 8006; deploy it on the patient-room device to obtain
physical separation.

### 5. LangGraph Workflow

The coordinator orchestrates the entire decision pipeline.

**File**: `langgraph_coordinator/graph.py`

```python
from typing import TypedDict
import requests

class State(TypedDict):
    patient_id: str
    patient: dict
    policy: dict
    proof: dict
    decision: dict

def get_patient(state):
    """Get minimum EMR context from the EMR layer"""
    url = f"http://127.0.0.1:8005/patient/{state['patient_id']}"
    response = requests.get(url, timeout=10)
    patient = response.json()
    return {"patient": patient}

def get_policy(state):
    """Generate personalized policy from Rule Engine"""
    response = requests.post(
        "http://127.0.0.1:8004/policy",
        json=state["patient"],
        timeout=60
    )
    policy = response.json()
    return {"policy": policy}

def get_proof(state):
    """Request ZKP proof from Privacy MCP"""
    bounds = {
        "min": state["policy"]["min"],
        "max": state["policy"]["max"]
    }
    
    response = requests.post(
        "http://127.0.0.1:8003/request-proof",
        json={"bounds": bounds},
        timeout=30
    )
    proof = response.json()
    return {"proof": proof}

def get_decision(state):
    """Summarize the ZKP result inside the coordinator."""
    from langgraph_coordinator.graph import summarize_proof
    return {"decision": summarize_proof(state["proof"])}
```

**File**: `langgraph_coordinator/app.py`

```python
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from .graph import State, get_patient, get_policy, get_proof, get_decision

app = FastAPI(title="LangGraph Coordinator")

# Build workflow graph
builder = StateGraph(State)

builder.add_node("patient", get_patient)
builder.add_node("policy", get_policy)
builder.add_node("proof", get_proof)
builder.add_node("decision", get_decision)

# Define workflow: patient → policy → proof → decision → END
builder.set_entry_point("patient")
builder.add_edge("patient", "policy")
builder.add_edge("policy", "proof")
builder.add_edge("proof", "decision")
builder.add_edge("decision", END)

graph = builder.compile()

@app.get("/run/{patient_id}")
def run(patient_id: str):
    initial_state = {
        "patient_id": patient_id,
        "patient": {},
        "policy": {},
        "proof": {},
        "decision": {}
    }
    
    result = graph.invoke(initial_state)
    return result
```

## API Endpoints

### LangGraph Coordinator (Port 8001)

```
GET /run/{patient_id}
```
Executes the full workflow for a patient.

**Example**:
```bash
curl http://localhost:8001/run/10009628
```

### Rule Engine (Port 8004)

```
POST /policy
```
Generates personalized policy bounds.

**Example**:
```bash
curl -X POST http://localhost:8004/policy \
  -H "Content-Type: application/json" \
  -d '{"condition": "Diabetes", "age": 65}'
```

### Privacy MCP (Port 8003)

```
POST /request-proof
```
Requests ZKP proof from device.

**Example**:
```bash
curl -X POST http://localhost:8003/request-proof \
  -H "Content-Type: application/json" \
  -d '{"bounds": {"min": 110, "max": 135}}'
```

### Coordinator range assessment

LangGraph maps verified range membership to `IN_RANGE`, a device-reported out-of-range reading to `OUT_OF_RANGE`, and missing or failed verification to `UNABLE_TO_ASSESS`. These labels describe the range check, not the patient's overall clinical stability.

## Project Structure

```
Privacy-Preserving-CDSS/
├── RAG/
│   ├── rag.py                      # Legacy RAG implementation (HuggingFace)
│   ├── chroma_db/                  # Vector database (legacy)
│   └── guidelines/                 # Medical guideline PDFs
│       ├── Diabetes guideline.pdf
│       ├── Hypertension guideline.pdf
│       └── Heart Failure guideline.pdf
├── knowledge_mcp/
│   ├── app.py                      # Legacy optional Knowledge MCP API
│   ├── build_vector_db.py          # Vector database builder
│   └── chroma_db/                  # Vector database (active)
├── rule_engine/
│   ├── app.py                      # Rule Engine API
│   ├── policy_generator.py         # LLM-based policy generation
│   └── rules.py                    # Legacy rule-based policy
├── privacy_mcp/
│   ├── app.py                      # Privacy MCP API
│   └── zkp_client.py               # ZKP proof generation/verification
├── device_agent/
│   ├── app.py                      # Device agent API
│   └── sensor.py                   # Sensor reading simulation
├── langgraph_coordinator/
│   ├── app.py                      # LangGraph workflow API
│   ├── graph.py                    # Workflow nodes and edges
│   └── run_case.py                 # Test script
├── decision_engine/
│   ├── app.py                      # Legacy Decision Engine API (not started)
│   └── engine.py                   # Legacy decision logic
├── patient_mcp/
│   ├── app.py                      # EMR Layer API
│   └── database.py                 # EMR record access (FHIR representation)
├── zkp_engine/
│   ├── Cargo.toml                  # Rust dependencies
│   └── src/                        # Rust source code
│       └── main.rs                 # Bulletproof implementation
├── datasets/
│   ├── original/                   # Original patient data
│   └── processed/                  # Processed data and schemas
├── scripts/
│   ├── build_rag.py                # Build vector database
│   └── prepare_dataset.py          # Prepare EMR record dataset
├── requirements.txt                # Python dependencies
├── start.ps1                       # Windows startup script
└── README.md                       # This file
```

## Configuration

The active EMR dataset files are stored directly in `datasets/`:
`patients_100.json`, `conditions_100.json`, and `observations_100.json`.
The dataset-preparation script writes its generated files to this same directory.

### Environment Variables

Create a `.env` file in the backend directory:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/cdss_db
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

### Port Configuration

Default ports (can be modified in each service's `app.py`):

| Service | Port |
|---------|------|
| LangGraph Coordinator | 8001 |
| Privacy MCP | 8003 |
| Rule Engine | 8004 |
| EMR Layer | 8005 |
| Ollama | 11434 |

## Workflow Example

```
1. Doctor asks for Ahmed's range assessment.

2. LangGraph Coordinator receives request with patient_id

3. EMR Retrieval Node:
   - Fetches minimum EMR context from the FHIR record representation
   - Returns: {condition: "Diabetes", age: 65}

4. Policy Node:
   - Retrieves Diabetes guidelines via RAG
   - LLM generates: {parameter: "systolic_bp", min: 110, max: 135}

5. Proof Node:
   - Sends bounds (110-135) to Privacy MCP
   - Device reads BP locally: 190
   - Device generates ZKP proof (value stays hidden)
   - Device reports that the value is outside the range; no range proof is produced

6. Coordinator status node:
   - Receives proof status: `ALERT`
   - Returns: `{status: "OUT_OF_RANGE", message: "Device reported a reading outside the selected range; clinical review is needed."}`

7. Final Response to Doctor:
   - Status: Out of range; clinical review needed
   - Reason: Device reported that the reading is outside the selected range
   - Privacy: Sensor value never exposed
```

## Privacy Guarantees

1. **Sensor Data Never Leaves Device**: Raw sensor values are read locally and only used for ZKP generation
2. **Zero-Knowledge Proofs**: Mathematical proofs verify properties without revealing data
3. **Minimal Data Sharing**: Only bounds and proof status are transmitted
4. **Local Computation**: ZKP generation happens on the device itself

## Technology Stack

- **Backend**: FastAPI, Python 3.9+
- **LLM**: Ollama (LLaMA3)
- **Embeddings**: Ollama (nomic-embed-text)
- **Vector Database**: ChromaDB
- **Workflow Orchestration**: LangGraph
- **ZKP**: Rust + Bulletproofs
- **Database**: PostgreSQL
- **PDF Processing**: LangChain PyPDFLoader

## Testing

```bash
# Test ChromaDB
python test_chroma.py

# Test embeddings
python test_embed.py

# Run test case
python langgraph_coordinator/run_case.py

# Backend tests
cd backend
pytest
```

## Troubleshooting

### Ollama Connection Issues

```bash
# Check if Ollama is running
curl http://127.0.0.1:11434/api/tags

# Start Ollama service
ollama serve
```

### ZKP Engine Not Found

```bash
# Build the Rust engine
cd zkp_engine
cargo build --release
```

### ChromaDB Errors

```bash
# Rebuild vector database
python scripts/build_rag.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License

This project is part of a master's thesis on privacy-preserving clinical decision support systems.

## Contact

For questions or issues, please open an issue on GitHub.
