import requests

class GitHubAgent:
    def __init__(self, token=None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AutoQA-AI-Platform"
        }
        if token:
            self.headers["Authorization"] = f"token {token}"

    def get_user_repos(self):
        """Fetches repositories for the authenticated user."""
        if not self.token:
            return []
        res = requests.get(f"{self.base_url}/user/repos?sort=updated&per_page=100", headers=self.headers)
        if res.status_code != 200:
            return []
        return res.json()

    def get_repo_branches(self, owner, repo):
        """Fetches branches for a repository."""
        res = requests.get(f"{self.base_url}/repos/{owner}/{repo}/branches", headers=self.headers)
        if res.status_code != 200:
            return []
        return res.json()

    def get_repo_metadata(self, owner, repo):
        """Fetches detailed repository metadata."""
        res = requests.get(f"{self.base_url}/repos/{owner}/{repo}", headers=self.headers)
        if res.status_code != 200:
            return None
        return res.json()

    def get_file_tree(self, owner, repo, branch="main"):
        """Fetches the recursive file tree for a repository."""
        res = requests.get(f"{self.base_url}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1", headers=self.headers)
        if res.status_code != 200:
            # Try 'master' if 'main' fails
            if branch == "main":
                return self.get_file_tree(owner, repo, "master")
            return None
        return res.json()

    def get_file_content(self, owner, repo, path, branch="main"):
        """Fetches content of a specific file."""
        res = requests.get(f"{self.base_url}/repos/{owner}/{repo}/contents/{path}?ref={branch}", headers=self.headers)
        if res.status_code != 200:
            return None
        data = res.json()
        if 'content' not in data:
            return None
        
        import base64
        return base64.b64decode(data['content']).decode('utf-8', errors='ignore')

    def parse_repo_url(self, url):
        """Extracts owner and repo from a GitHub URL."""
        parts = url.strip().rstrip('/').split('/')
        if len(parts) >= 2:
            return parts[-2], parts[-1]
        return None, None
