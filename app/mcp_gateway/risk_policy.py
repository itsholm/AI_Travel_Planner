from models.schemas import ApprovalDecision, Approval, ToolRiskLevel, ToolSpec


class PolicyDecision:
    def __init__(self, allowed: bool, requires_approval: bool, reason: str = ""):
        self.allowed = allowed
        self.requires_approval = requires_approval
        self.reason = reason


class PolicyEngine:
    """Deterministic guardrail for tool side effects."""

    def decide(self, spec: ToolSpec, approval: Approval = None) -> PolicyDecision:
        if spec.risk_level == ToolRiskLevel.HIGH:
            if approval and approval.decision == ApprovalDecision.APPROVED:
                return PolicyDecision(True, False, "high risk action approved")
            return PolicyDecision(False, True, "high risk action requires approval")

        if spec.risk_level == ToolRiskLevel.MEDIUM and spec.side_effect:
            return PolicyDecision(True, False, "medium risk action allowed by demo policy")

        return PolicyDecision(True, False, "low risk action allowed")
