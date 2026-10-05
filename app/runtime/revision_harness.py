"""Reuse the original revision safeguards with a task-local agent.

Gateway owns tool retries; failed planning is resumed through Task checkpoints.
Do not turn a failed revision into a successful generic fallback response.
"""
from harness_enhanced import EnhancedAgentHarness, EnhancedHarnessConfig, EnhancedOutputHarness
from models.schemas import TripPlan


class PlanOutputHarness(EnhancedOutputHarness):
    def sanitize_output(self, output):
        if isinstance(output, dict):
            return {key: self.sanitize_output(value) for key, value in output.items()}
        if isinstance(output, list):
            return [self.sanitize_output(value) for value in output]
        return super().sanitize_output(output)

    def risk_assessment(self, output):
        # Coordinates, dates and prices are structured data, not free-text PII.
        def strings(value):
            if isinstance(value, dict):
                return " ".join(strings(v) for v in value.values())
            if isinstance(value, list):
                return " ".join(strings(v) for v in value)
            return value if isinstance(value, str) else ""
        return super().risk_assessment(strings(output))


class StructuredAgent:
    def __init__(self, agent):
        self.agent = agent
        self.name = getattr(agent, "name", "trip_planner")

    async def run(self, prompt):
        plan = await self.agent.run_structured(prompt, TripPlan)
        return plan.model_dump(mode="json")


class RevisionGuard:
    def __init__(self):
        self.execution_count = {}
        self.last_execution = {}
        self.error_counts = {}

    async def run(self, agent, prompt, session_id):
        config = EnhancedHarnessConfig()
        config.ENABLE_RETRY = False
        config.ENABLE_FALLBACK = False
        harness = EnhancedAgentHarness(StructuredAgent(agent), config)
        harness.output_harness = PlanOutputHarness(config)
        harness.execution_count = self.execution_count
        harness.last_execution = self.last_execution
        harness.error_counts = self.error_counts
        result = await harness.execute(prompt, {"session_id": session_id})
        if not result.success:
            raise ValueError(str(result.error))
        return TripPlan.model_validate(result.data)
