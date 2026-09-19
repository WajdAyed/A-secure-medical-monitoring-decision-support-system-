import os
import sys

from cdss_rpc import call_tool


def main() -> None:
    patient_id = sys.argv[1] if len(sys.argv) > 1 else "10009628"
    base_url = os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007")
    print(call_tool(base_url, "run_cdss", {"patient_id": patient_id}, timeout=180))


if __name__ == "__main__":
    main()
