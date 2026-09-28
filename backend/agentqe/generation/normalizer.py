import re
from typing import List

from agentqe.models.test_case import CandidateTest
from .interfaces import ITestNormalizer

class DeterministicTestNormalizer(ITestNormalizer):
    def normalize(self, test: CandidateTest) -> CandidateTest:
        # Normalize title
        test.title = re.sub(r'\s+', ' ', test.title.strip())
        
        # Normalize test type to uppercase
        test.test_type = test.test_type.upper().strip()
        
        # Normalize steps
        normalized_steps = []
        for i, step in enumerate(test.steps):
            s = str(step).strip()
            # Remove leading numbers like "1. ", "2) ", etc
            s = re.sub(r'^\d+[\.\)]\s*', '', s)
            normalized_steps.append(s)
        test.steps = normalized_steps
        
        # Normalize expected results
        test.expected_result = re.sub(r'\s+', ' ', test.expected_result.strip())
        
        # Normalize refs lists to remove dupes within the test
        test.requirement_refs = list(set(test.requirement_refs))
        test.page_refs = list(set(test.page_refs))
        test.control_refs = list(set(test.control_refs))
        test.form_refs = list(set(test.form_refs))
        test.api_refs = list(set(test.api_refs))
        test.flow_refs = list(set(test.flow_refs))
        test.evidence_refs = list(set(test.evidence_refs))
        
        return test
