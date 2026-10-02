"""Summarize contract evaluation rows and write an interpretation report."""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

RESULTS = Path(__file__).with_name("results")
INPUT = RESULTS / "contract_raw.csv"


def main() -> None:
    with INPUT.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    summaries = []
    for family in sorted({row["family"] for row in rows}):
        group = [row for row in rows if row["family"] == family]
        latencies = [float(row["latency_ms"]) for row in group]
        passed = sum(row["passed"].lower() == "true" for row in group)
        summaries.append({"family": family, "cases": len(group), "passed": passed, "failed": len(group) - passed, "pass_rate": passed / len(group), "median_latency_ms": statistics.median(latencies)})
    with (RESULTS / "contract_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0])); writer.writeheader(); writer.writerows(summaries)
    report = ["# Workflow contract and privacy robustness", "", "This report measures software contracts against the running local services. It is not clinical validation.", "", "## Results", ""]
    for item in summaries:
        report.append(f"- **{item['family']}**: {item['passed']}/{item['cases']} passed ({item['pass_rate']:.1%}); median latency {item['median_latency_ms']:.1f} ms.")
    failed = [row for row in rows if row["passed"].lower() != "true"]
    report.extend(["", "## Limitations", "", "- Valid workflows use one representative patient per condition and the local service configuration.", "- Fallback ranges are explicitly unverified project reference values.", "- The privacy scan checks returned JSON only; it cannot prove that a running process log or network intermediary did not retain a value."])
    if failed:
        report.extend(["", "## Failed cases", ""])
        report.extend(f"- `{item['family']}/{item['case']}`: {item['detail']}" for item in failed)
    (RESULTS / "contract_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("Wrote contract summary and report")


if __name__ == "__main__":
    main()