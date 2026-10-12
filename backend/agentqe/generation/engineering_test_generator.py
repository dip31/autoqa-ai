import json
import logging
import uuid
from typing import List, Dict, Any

from agentqe.models.test_case import CandidateTest
from .interfaces import ITestGenerator, ITestGenerationModel
from .prompts import ENGINEERING_AGENT_SYSTEM_PROMPT, COMPACT_GENERATION_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

class EngineeringTestGenerator(ITestGenerator):
    def __init__(self, model: ITestGenerationModel):
        self.model = model

    def generate(self, generation_context: Dict[str, Any]) -> List[CandidateTest]:
        # Use compact serialization for bounded context
        prompt = COMPACT_GENERATION_PROMPT_TEMPLATE.format(
            requirement=generation_context.get("requirement", ""),
            pages=self._format_list(generation_context.get("pages", [])),
            controls=self._format_list(generation_context.get("controls", [])),
            forms=self._format_list(generation_context.get("forms", [])),
            apis=self._format_list(generation_context.get("apis", [])),
            flows=self._format_list(generation_context.get("flows", [])),
            modules=self._format_list(generation_context.get("modules", [])),
            repo_context=json.dumps(generation_context.get("repository_context", {})),
            rag_docs=json.dumps(generation_context.get("rag_docs", []))
        )

        response_str = self.model.generate(prompt, system_prompt=ENGINEERING_AGENT_SYSTEM_PROMPT)
        data = json.loads(response_str)
        raw_tests = data.get("test_cases", [])
        
        candidates = []
        for t in raw_tests:
            steps = t.get("steps", [])
            if isinstance(steps, str):
                steps = [steps]
                
            candidate = CandidateTest(
                test_id=t.get("test_id", f"ENG-{uuid.uuid4().hex[:6]}"),
                title=t.get("title", "Untitled Engineering Test"),
                description=t.get("description", ""),
                perspective=t.get("perspective", "SYSTEM"),
                test_type=t.get("test_type", "API"),
                source_agent=t.get("source_agent", "engineering_agent"),
                preconditions=t.get("preconditions", []),
                steps=steps,
                expected_result=t.get("expected_result", ""),
                requirement_refs=t.get("requirement_refs", []),
                page_refs=t.get("page_refs", []),
                control_refs=t.get("control_refs", []),
                form_refs=t.get("form_refs", []),
                api_refs=t.get("api_refs", []),
                flow_refs=t.get("flow_refs", []),
                evidence_refs=t.get("evidence_refs", [])
            )
            candidates.append(candidate)
            
        return candidates
    
    def _format_list(self, items: List) -> str:
        """Format list items compactly."""
        if not items:
            return "None"
        if isinstance(items[0], str):
            # Already compact strings
            return ", ".join(items[:10])
        else:
            # List of dicts - extract IDs or names
            formatted = []
            for item in items[:10]:
                if isinstance(item, dict):
                    formatted.append(item.get("id", item.get("name", str(item))))
                else:
                    formatted.append(str(item))
            return ", ".join(formatted)
