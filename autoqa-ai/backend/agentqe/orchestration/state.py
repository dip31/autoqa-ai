#LangGraph state
from typing import Any, Dict, List, TypedDict

class AgentQEState(TypedDict, total=False):

    run_id: int

    application_context: Any

    strategy: Dict[str, Any]

    user_tests: List[Any]

    engineering_tests: List[Any]

    candidate_tests: List[Any]

    enriched_tests: List[Any]

    ranked_tests: List[Any]

    selected_tests: List[Any]

    execution_results: List[Any]

    failures: List[Any]

    quality_score: float

    human_decision: str

    human_feedback: str

    cycle: int

    max_cycles: int

    final_report: Dict[str, Any]