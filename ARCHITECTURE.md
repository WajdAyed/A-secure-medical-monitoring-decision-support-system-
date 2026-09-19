# System Architecture

```mermaid
flowchart TB
    Doctor["Clinician / Doctor"]
    Console["Doctor Console<br/>(CLI)"]

    subgraph Docker["Docker Compose deployment"]
        Coordinator["LangGraph Coordinator<br/>FastAPI :8007<br/><i>patient -> policy -> proof -> decision</i>"]

        subgraph Clinical["Clinical data and policy services"]
            PatientMCP["Patient MCP<br/>FastAPI :8005"]
            PatientData[("FHIR sample data<br/>datasets/")]
            RuleEngine["Rule Engine<br/>FastAPI :8004"]
            DecisionEngine["Decision Engine<br/>FastAPI :8002"]
        end

        subgraph Knowledge["Clinical knowledge / RAG"]
            KnowledgeMCP["Knowledge MCP<br/>FastAPI :8010"]
            Chroma[("ChromaDB<br/>vector store")]
            Ollama["Ollama :11434<br/>llama3 + nomic-embed-text"]
        end

        subgraph Privacy["Privacy-preserving proof boundary"]
            PrivacyMCP["Privacy MCP<br/>FastAPI :8003"]
            Device["Local device sensor<br/><i>raw BP value</i>"]
            ZKP["Rust ZKP engine<br/>Bulletproofs"]
        end

        Postgres[("PostgreSQL :5432<br/><i>provisioned service</i>")]
    end

    subgraph Offline["Offline knowledge preparation"]
        PDFs["Clinical-guideline PDFs<br/>RAG/guidelines/"]
        Build["build_rag.py<br/>chunk + embed"]
    end

    Doctor --> Console
    Console -->|GET /run/{patient_id}| Coordinator
    Coordinator -->|GET /patient/{id}| PatientMCP
    PatientMCP --> PatientData
    Coordinator -->|POST /policy with patient profile| RuleEngine
    RuleEngine -->|GET /guidelines/{condition}| KnowledgeMCP
    KnowledgeMCP <--> Chroma
    RuleEngine -->|policy-generation prompt| Ollama
    KnowledgeMCP -->|embeddings| Ollama

    Coordinator -->|POST /request-proof: policy bounds only| PrivacyMCP
    PrivacyMCP -->|bounds only| Device
    Device -->|value + bounds stay local| ZKP
    ZKP -->|verified, status, proof type| PrivacyMCP
    PrivacyMCP -->|proof status; no raw value| Coordinator

    Coordinator -->|POST /decision: proof status only| DecisionEngine
    DecisionEngine -->|clinical decision| Coordinator
    Coordinator -->|decision and workflow result| Console

    PDFs --> Build
    Build -->|embedded chunks| Chroma
```

## Main runtime flow

1. The clinician selects a patient in the Doctor Console, which calls the LangGraph Coordinator.
2. The coordinator retrieves a minimal patient profile from Patient MCP.
3. The Rule Engine retrieves relevant guideline passages from Knowledge MCP/ChromaDB and uses Ollama to generate personalised safe bounds.
4. Only the bounds go to Privacy MCP. The raw sensor reading remains on the device side and is used by the Rust Bulletproofs engine to generate and verify a range proof.
5. The coordinator sends only the proof status (`NORMAL`, `ALERT`, or `PROOF_FAILED`) to the Decision Engine, then returns the resulting clinical decision to the doctor.

## Notes

- `device_agent/` exposes an alternative local `/prove` API and sensor simulation. It is not currently wired into `docker-compose.yml`; the deployed `privacy_mcp/zkp_client.py` performs the local sensor simulation and invokes the Rust engine directly.
- PostgreSQL is provisioned by Docker Compose, but the current Patient MCP reads the FHIR JSON sample data rather than querying PostgreSQL.
