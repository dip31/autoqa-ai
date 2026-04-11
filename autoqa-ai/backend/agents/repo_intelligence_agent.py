import os
import json
import re
from groq import Groq
from agents.github_agent import GitHubAgent
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class RepoIntelligenceAgent:
    def __init__(self, github_token=None):
        self.gh = GitHubAgent(github_token)

    def analyze(self, repo_url, branch="main"):
        owner, repo = self.gh.parse_repo_url(repo_url)
        if not owner or not repo:
            return {"error": "Invalid repository URL"}

        # 1. Fetch Metadata
        metadata_res = self.gh.get_repo_metadata(owner, repo)
        if not metadata_res:
             return {"error": "Could not fetch repository metadata. Please verify the URL and ensure the repository is public or your GitHub account is linked."}
        metadata = metadata_res

        # 2. Fetch File Tree
        tree_res = self.gh.get_file_tree(owner, repo, branch)
        tree = tree_res.get("tree", []) if tree_res else []
        file_paths = [f["path"] for f in tree]

        # 3. Identify Hero Files
        hero_files = self._identify_hero_files(file_paths)
        file_contents = {}
        for f in hero_files:
            content = self.gh.get_file_content(owner, repo, f, branch)
            if content:
                file_contents[f] = content[:8000] # Cap content for LLM

        # 4. Perform AI Analysis
        analysis = self._run_ai_analysis(metadata, file_paths, file_contents)
        
        return {
            "metadata": metadata,
            "analysis": analysis,
            "repo_url": repo_url,
            "owner": owner,
            "repo_name": repo
        }

    def _identify_hero_files(self, paths):
        priority = [
            r"README\.md$", r"package\.json$", r"requirements\.txt$", r"pyproject\.toml$",
            r"Dockerfile$", r"docker-compose\.yml$", r"github/workflows/.*\.yml$",
            r"src/app\.js$", r"src/index\.js$", r"app\.py$", r"main\.py$",
            r"src/routes/.*", r"src/components/.*", r"tests/.*"
        ]
        heroes = []
        for p in priority:
            pattern = re.compile(p, re.IGNORECASE)
            matches = [f for f in paths if pattern.search(f)]
            heroes.extend(matches[:3]) # Take top 3 matches per pattern
        return list(set(heroes))

    def _run_ai_analysis(self, metadata, file_paths, file_contents):
        # Concatenate hero content for context
        context = f"Repo: {metadata.get('full_name')}\nDesc: {metadata.get('description')}\nLang: {metadata.get('language')}\n\n"
        for f, content in file_contents.items():
            context += f"--- FILE: {f} ---\n{content}\n\n"

        prompt = f"""
        Analyze this repository as a Senior QA and Software Architect.
        
        Repository Structure (Sample):
        {json.dumps(file_paths[:100], indent=2)}
        
        Key File Contents:
        {context}

        Provide a deep intellectual analysis in VALID JSON format with these exact keys:
        - tech_stack: {{ backend: string, frontend: string, database: string, tools: [string] }}
        - architecture_overview: string (describe pattern like MVC, Microservices, etc.)
        - code_quality: {{ score: 0-100, observations: [string] }}
        - bugs_and_risks: {{ high_risk_modules: [string], probable_issues: [string] }}
        - test_coverage: {{ maturity: string, missing_scenarios: [string], suggested_frameworks: [string] }}
        - generated_test_cases: [
            {{ id: string, title: string, objective: string, module: string, steps: [string], expected: string, priority: string, category: string }}
          ]
        - fix_suggestions: [{{ area: string, suggestion: string, benefit: string }}]
        - health_indicators: {{ quality: 0-100, test_readiness: 0-100, maintainability: 0-100 }}
        
        Be thorough, professional, and heuristic. Do not claim absolute certainty.
        """

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            raw = response.choices[0].message.content.strip()
            # Extract JSON
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(raw)
        except Exception as e:
            print(f"[AI Analysis Error] {e}")
            return {"error": "AI analysis failed"}
