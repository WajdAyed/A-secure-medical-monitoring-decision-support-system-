# Project sequence diagram

This diagram follows one doctor request through the active CDSS workflow. A patient with several conditions repeats policy generation and proof verification for each condition.

```mermaid
sequenceDiagram
    autonumber
    actor Doctor
    participant Console as Doctor Console
    participant Coordinator as LangGraph Coordinator
    participant EMR as Patient / EMR service
    participant Dataset as Patient JSON dataset
    participant Ruler as Ruler Agent
    participant Chroma as ChromaDB guidelines
    participant Ollama as Ollama models
    participant Verifier as Privacy / ZKP verifier
    participant Device as Device Agent
    participant Sensor as Local sensor
    participant Prover as Rust ZKP engine (device)
    participant Checker as Rust ZKP engine (server)

    Doctor->>Console: Enter patient query
    Console->>Coordinator: run_cdss(patient_id)
    Coordinator->>EMR: get_patient(patient_id)
    EMR->>Dataset: Find patient record
    Dataset-->>EMR: FHIR-like record
    EMR-->>Coordinator: Minimum context (age, condition)

    alt Patient not found or EMR error
        Coordinator-->>Console: Workflow error
        Console-->>Doctor: Show error
    else Patient context available
        loop For each condition, if multiple
            Coordinator->>Ruler: generate_policy(patient context, use_rag)
            alt RAG enabled
                Ruler->>Ollama: Embed condition query
                Ollama-->>Ruler: Query embedding
                Ruler->>Chroma: Search guideline passages
                Chroma-->>Ruler: Relevant passages
                Ruler->>Ollama: Generate candidate clinical range
                Ollama-->>Ruler: Candidate policy
            else RAG disabled
                Ruler->>Ruler: Select configured fallback policy
            end
            Ruler->>Ruler: Normalize and validate bounds
            Ruler-->>Coordinator: Policy (parameter, min, max)
        end

        alt Policy generation fails
            Coordinator-->>Console: Workflow error
            Console-->>Doctor: Show error
        else Valid public range or ranges
            Coordinator->>Verifier: request_proof(s) (public bounds, patient_id)
            loop For each public range
                Verifier->>Verifier: Validate bounds and create fresh nonce
                Verifier->>Device: prove(min, max, nonce, patient_id)
                Device->>Sensor: Read measurement locally
                Sensor-->>Device: Private measurement
                Device->>Prover: Prove measurement within bounds
                alt Measurement within range
                    Prover-->>Device: Commitment and Bulletproof package
                    Device-->>Verifier: Proof package (no raw value)
                    Verifier->>Checker: Verify package and expected nonce
                    Checker-->>Verifier: Verification verdict
                else Measurement outside range
                    Prover-->>Device: ALERT (no range proof)
                    Device-->>Verifier: ALERT (no raw value)
                end
            end
            Verifier-->>Coordinator: Verification result(s)
            Coordinator->>Coordinator: Summarize IN_RANGE, OUT_OF_RANGE, or UNABLE_TO_ASSESS
            Coordinator-->>Console: Patient, policy, proof result, decision
            Console-->>Doctor: Display clinical assessment
        end
    end

    Note over Sensor,Prover: Raw measurements and proving secrets remain on the device.
```

Guideline PDFs are embedded into ChromaDB before this runtime sequence. The current EMR lookup uses the project JSON dataset; PostgreSQL is included in the development stack but is not in this lookup path.
