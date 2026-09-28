import difflib
from typing import List

from agentqe.models.test_case import CandidateTest
from .interfaces import ITestDeduplicator

class DeterministicDeduplicator(ITestDeduplicator):
    def deduplicate(self, tests: List[CandidateTest]) -> List[CandidateTest]:
        """
        Deterministically merge similar tests. 
        Only merge if they test the same functional layer (e.g., both UI or both API).
        """
        final_tests = []
        merged_count = 0
        
        for test in tests:
            is_duplicate = False
            for existing in final_tests:
                # Must be the same test type to merge (UI vs API shouldn't merge)
                if existing.test_type != test.test_type:
                    continue
                    
                # Check semantic similarity of titles
                title_sim = difflib.SequenceMatcher(None, test.title.lower(), existing.title.lower()).ratio()
                
                # If titles are very similar and they are the same type, merge them
                if title_sim > 0.85:
                    is_duplicate = True
                    self._merge(existing, test)
                    merged_count += 1
                    break
                    
            if not is_duplicate:
                final_tests.append(test)
                
        # Update metadata to track deduplication count (stored on the first test just for counting, or global)
        return final_tests

    def _merge(self, base: CandidateTest, incoming: CandidateTest) -> None:
        """Merge incoming into base."""
        # Combine source agents safely
        sources = set(base.source_agent.split(","))
        for s in incoming.source_agent.split(","):
            sources.add(s.strip())
        base.source_agent = ",".join(sorted(list(sources)))
        
        # Merge references
        base.requirement_refs = list(set(base.requirement_refs + incoming.requirement_refs))
        base.page_refs = list(set(base.page_refs + incoming.page_refs))
        base.control_refs = list(set(base.control_refs + incoming.control_refs))
        base.form_refs = list(set(base.form_refs + incoming.form_refs))
        base.api_refs = list(set(base.api_refs + incoming.api_refs))
        base.flow_refs = list(set(base.flow_refs + incoming.flow_refs))
        base.evidence_refs = list(set(base.evidence_refs + incoming.evidence_refs))
        
        # Combine metadata
        base.metadata["merged_from"] = base.metadata.get("merged_from", []) + [incoming.test_id]
