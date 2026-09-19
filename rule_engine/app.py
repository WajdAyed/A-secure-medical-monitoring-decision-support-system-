from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer
from .policy_generator import generate_policy


app = FastAPI(
    title="Ruler Agent"
)
rpc = MCPJsonRpcServer("ruler-agent")


@rpc.tool("generate_policy", "Check patient context, retrieve ChromaDB guideline knowledge, and use Ollama to generate a safe clinical range.", {
    "type": "object", "properties": {"patient": {"type": "object"}, "use_rag": {"type": "boolean"}}, "required": ["patient"],
})
def policy(patient: dict, use_rag: bool = True):

    print("\n" + "=" * 70)
    print("RULER AGENT")
    print("=" * 70)

    print("Policy generation request received")

    print("\nPatient data received:")
    print(patient)


    print("\nGenerating personalized clinical policy...")


    try:

        result = generate_policy(patient, use_rag=use_rag)


        print("\n✅ Policy generated")

        print("Generated policy:")
        print(result)


        print("=" * 70)


        return result


    except Exception as e:


        print("\n❌ RULE ENGINE ERROR")

        print(e)

        print("=" * 70)


        return {
            "error": str(e)
        }


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
