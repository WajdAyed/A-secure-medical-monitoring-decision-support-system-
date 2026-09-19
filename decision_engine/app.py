from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer

from .engine import evaluate


app = FastAPI(
    title="Decision Engine"
)
rpc = MCPJsonRpcServer("decision-engine")



@rpc.tool("evaluate_decision", "Generate a clinical decision from a proof status.", {
    "type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"],
})
def decision(status: str):


    print("\n" + "=" * 70)
    print("DECISION ENGINE")
    print("=" * 70)



    print("\nDecision request received")


    print("Proof status:")

    print(
        status
    )



    print("\nPrivacy check:")

    print(
        "✓ No sensor value received"
    )

    print(
        "✓ Decision based only on ZKP result"
    )



    print("\nEvaluating clinical status...")



    try:


        result = evaluate(
            status
        )


    except Exception as e:


        print("\n❌ DECISION ENGINE ERROR")

        print(e)


        return {
            "error": str(e)
        }



    print("\n✅ Clinical decision generated")


    print(result)



    print("=" * 70)



    return result


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
