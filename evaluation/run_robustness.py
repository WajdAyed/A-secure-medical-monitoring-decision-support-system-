"""Experiment D safety checks. Failure injection is opt-in to avoid stopping user services."""
import argparse, json
from .config import RESULTS
from .ground_truth import ensure_reference_ranges
def main():
 p=argparse.ArgumentParser();p.add_argument('--allow-service-stop',action='store_true');a=p.parse_args()
 report={"reference_ranges":ensure_reference_ranges(),"failure_injection":"not executed" if not a.allow_service_stop else "requires operator-managed services","privacy_audit":"Run after results/log paths are supplied; raw values are intentionally unavailable to this process."}
 RESULTS.mkdir(parents=True,exist_ok=True);(RESULTS/'robustness_report.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
