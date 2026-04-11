import pytest
from unittest.mock import patch, MagicMock
import json

def test_testcase_agent_mocked():
    """Test that the testcase agent correctly parses and handles LLM output."""
    mock_response = {
        "score": 85,
        "issues": ["Missing exact values"],
        "suggestions": ["Add test data"],
        "improved_testcase": "Updated test case description"
    }
    
    with patch('agents.testcase_agent.client.chat.completions.create') as mock_create:
        # Mocking Groq response object structure
        mock_msg = MagicMock()
        mock_msg.content = json.dumps(mock_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_create.return_value.choices = [mock_choice]
        
        from agents.testcase_agent import review_testcase
        result = review_testcase("Verify login works")
        
        assert result['score'] == 85
        assert "Missing exact values" in result['issues']
        mock_create.assert_called_once()

def test_code_agent_mocked():
    """Test that the code agent correctly reviews code with a mock."""
    mock_response = {
        "score": 90,
        "issues": [{"line": 1, "severity": "low", "type": "style", "description": "missing docstring"}],
        "suggestions": ["Add docstring"],
        "summary": "Good code",
        "optimized_code": "def hello():\n    \"\"\"Doc.\"\"\"\n    pass"
    }
    
    with patch('agents.code_agent.client.chat.completions.create') as mock_create:
        mock_msg = MagicMock()
        mock_msg.content = json.dumps(mock_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_create.return_value.choices = [mock_choice]
        
        from agents.code_agent import review_code
        result = review_code("def hello(): pass", "Python")
        
        assert result['score'] == 90
        assert result['summary'] == "Good code"
