from agentqe.models.context import ApplicationContext
from typing import Dict, Any, List

class TestPlanningAgent:
    """
    Test Planning capability.
    Transforms ApplicationContext into a structured TestPlan.
    """

    def plan(self, context: ApplicationContext) -> Dict[str, Any]:
        
        objectives = []
        
        # Simple heuristic planning based on ApplicationContext
        if context.features:
            for feature in context.features:
                name = feature.get("name", "Unknown") if isinstance(feature, dict) else feature
                objectives.append({
                    "feature": name,
                    "test_types": ["UI", "functional"],
                    "priority_hint": "High",
                    "evidence": "features"
                })
        
        if context.user_flows:
            for flow in context.user_flows:
                name = flow.get("name", "Unknown Flow") if isinstance(flow, dict) else flow
                objectives.append({
                    "user_flow": name,
                    "test_types": ["workflow", "integration"],
                    "priority_hint": "High",
                    "evidence": "user_flows"
                })
                
        if context.api_endpoints:
            for endpoint in context.api_endpoints:
                name = endpoint.get("path", "Unknown") if isinstance(endpoint, dict) else endpoint
                objectives.append({
                    "api_endpoint": name,
                    "test_types": ["API", "validation"],
                    "priority_hint": "Medium",
                    "evidence": "api_endpoints"
                })
                
        if context.forms:
            for form in context.forms:
                name = form.get("name", "Unknown Form") if isinstance(form, dict) else form
                objectives.append({
                    "form": name,
                    "test_types": ["UI", "validation", "boundary"],
                    "priority_hint": "Medium",
                    "evidence": "forms"
                })

        # Add a default if nothing else
        if not objectives:
            objectives.append({
                "module": context.module_name or "General",
                "test_types": ["functional"],
                "priority_hint": "Medium",
                "evidence": "default"
            })
            
        test_plan = {
            "module": context.module_name,
            "objectives": objectives,
            "metadata": {
                "source": "TestPlanningAgent"
            }
        }
        
        return test_plan
