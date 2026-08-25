"""Command-line entry point for the complete AI QA Engineer workflow."""
import asyncio

from agents.qa_orchestrator import QAOrchestrator, WorkflowResult


def read_multiline_requirement(input_fn=input) -> str:
    """Read requirement lines until END is entered on its own line."""
    lines = []

    while True:
        line = input_fn()
        if line.strip().upper() == "END":
            break
        lines.append(line)

    return "\n".join(lines).strip()


def print_summary(result: WorkflowResult) -> None:
    passed = sum(item.status == "passed" for item in result.execution_results)
    failed = sum(item.status == "failed" for item in result.execution_results)
    errors = sum(item.status == "error" for item in result.execution_results)
    scenarios = len(result.requirement_analysis.scenarios) if result.requirement_analysis else 0
    print("\n# AI QA ENGINEER REPORT\n")
    print(f"Scenarios identified: {scenarios}")
    print(f"Tests generated: {len(result.generated_tests)}")
    print(f"Unable to generate: {len(result.skipped_tests)}\n")
    print(f"Executed: {len(result.execution_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Infrastructure errors: {errors}\n")
    print(f"RCA generated: {len(result.rca_results)}\n")
    print("Measured run metrics:")
    print(f"Requirement analysis latency: {result.metrics.requirement_analysis_latency_seconds}s")
    print(f"Generation latency: {result.metrics.generation_latency_seconds}s")
    print(f"Execution duration: {result.metrics.execution_duration_seconds}s")
    print(f"RCA latency: {result.metrics.rca_latency_seconds}s")
    print(f"Grounding success rate: {result.metrics.grounding_success_rate}")
    print(f"Generated/skipped ratio: {result.metrics.generated_to_skipped_ratio}\n")
    print("Overall status:")
    print(result.overall_status)
    print(f"\nRun report: reports/runs/{result.run_id}/final_report.json")


def main() -> None:
    print("Enter requirement:")
    print("Type END on a new line when finished.\n")

    requirement = read_multiline_requirement()

    if not requirement:
        print("No requirement entered.")
        raise SystemExit(1)

    print("\n--- REQUIREMENT RECEIVED ---")
    print(requirement)
    print("----------------------------\n")

    result = asyncio.run(QAOrchestrator().run(requirement))
    print_summary(result)


if __name__ == "__main__":
    main()
