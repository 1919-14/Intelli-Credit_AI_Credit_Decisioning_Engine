"""
Tavily Search API wrapper for Layer 4 research blocks.
"""
import os
from typing import List, Dict, Any


class TavilySearchClient:
    """Thin wrapper around Tavily API."""

    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                raise ImportError("tavily-python not installed. Run: pip install tavily-python")
        return self._client

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Execute a single search query. Returns list of {title, url, content}."""
        if not self.api_key:
            print(f"  ⚠ TAVILY_API_KEY not set — returning empty results for: {query[:50]}")
            return []

        try:
            client = self._get_client()
            result = client.search(query=query, max_results=max_results)
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0)
                }
                for r in result.get("results", [])
            ]
        except Exception as e:
            print(f"  ⚠ Tavily search error: {e}")
            return []

    def search_batch(self, queries: List[str], max_results: int = 3) -> Dict[str, List]:
        """Execute multiple queries. Returns {query: [results]}."""
        results = {}
        for q in queries:
            results[q] = self.search(q, max_results=max_results)
        return results
