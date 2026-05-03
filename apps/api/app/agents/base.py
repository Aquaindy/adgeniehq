from app.agents.types import AgentContext, AgentResult


class BaseAgent:
    """Specialized agents subclass this. The runner instantiates the class, calls
    `run()`, and persists every record returned in the AgentResult."""

    type: str = ""
    title: str = ""
    description: str = ""

    def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover — abstract
        raise NotImplementedError("Subclasses must implement run().")
