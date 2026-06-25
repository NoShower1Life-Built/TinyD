from typing import List, Dict

class RepositoryIndexer:
    def __init__(self):
        self.index = {}

    def ingest_repo(self, repo_name: str, files: List[Dict]):
        """Ingest repository structure"""
        self.index[repo_name] = {
            "files": files,
            "dependencies": [],
            "apis": [],
            "services": []
        }

    def compare(self, repo_a: str, repo_b: str):
        a = self.index.get(repo_a, {})
        b = self.index.get(repo_b, {})

        return {
            "repo_a": repo_a,
            "repo_b": repo_b,
            "shared": list(set(str(a.get("files", []))) & set(str(b.get("files", [])))),
            "differences": {
                "a_only": a,
                "b_only": b
            }
        }

    def get_index(self):
        return self.index