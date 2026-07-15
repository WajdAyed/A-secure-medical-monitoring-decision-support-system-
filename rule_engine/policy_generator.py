import requests
import ollama
import json
import re


def generate_policy(patient):


    print("\n" + "=" * 70)
    print("POLICY GENERATOR")
    print("=" * 70)


    condition = patient["condition"]
    age = patient["age"]


    print("\nPatient information:")
    print(patient)


    # ============================================
    # RAG retrieval
    # ============================================

    print("\nCalling Knowledge MCP (RAG)...")

    rag_url = (
        f"http://127.0.0.1:8010/guidelines/{condition}"
    )


    print("RAG URL:")
    print(rag_url)


    try:

        rag_response = requests.get(
            rag_url,
            timeout=30
        )


        print(
            "\nKnowledge MCP status:",
            rag_response.status_code
        )


        data = rag_response.json()

        print("\nKnowledge MCP response:")
        print(data)

        if "guidelines" not in data:

            print("\n❌ KNOWLEDGE MCP ERROR")
            print(data)

            raise Exception(
                f"Knowledge MCP Error:\n{data}"
            )

        docs = data["guidelines"]

    except Exception as e:

        print("\n❌ RAG ERROR")
        print(e)

        raise e



    print("\n✅ Guidelines retrieved from RAG")

    print(
        "Number of documents:",
        len(docs)
    )


    for i, doc in enumerate(docs):

        print("\n-----------------------------")
        print(
            "Guideline",
            i + 1
        )

        print(
            doc[:300]
        )



    context = "\n\n".join(docs)



    # ============================================
    # Ollama prompt
    # ============================================

    prompt = f"""
Patient:

Age: {age}
Condition: {condition}

Medical Guidelines:

{context}


Based on the medical guidelines,
generate personalized safe limits.

Return ONLY JSON.

Example:

{{
   "parameter":"systolic_bp",
   "min":110,
   "max":135
}}
"""


    print("\n" + "=" * 70)
    print("SENDING REQUEST TO OLLAMA")
    print("=" * 70)


    print("Model:")
    print("llama3")


    print("\nPrompt:")
    print(prompt)



    # ============================================
    # Ollama call
    # ============================================

    try:

        response = ollama.chat(

            model="llama3",

            format="json",

            messages=[
                {
                    "role":"user",
                    "content":prompt
                }
            ]

        )


    except Exception as e:

        print("\n❌ OLLAMA ERROR")
        print(e)

        raise e



    text = response["message"]["content"]



    print("\n" + "=" * 70)
    print("OLLAMA RESPONSE")
    print("=" * 70)

    print(text)



    # ============================================
    # JSON extraction
    # ============================================

    match = re.search(
        r"\{.*\}",
        text,
        re.S
    )


    if not match:

        print("\n❌ NO JSON FOUND")

        raise Exception(
            f"No JSON found:\n{text}"
        )


    policy = json.loads(
        match.group()
    )


    print("\n" + "=" * 70)
    print("GENERATED PERSONALIZED POLICY")
    print("=" * 70)

    print(policy)

    print("=" * 70)



    return policy