"""
TF-IDF based semantic search over occupation Markdown profiles.

Loads all .md profiles from data/profiles/, builds a TF-IDF index,
and supports natural-language queries that return the most relevant
occupation profiles. Much better than keyword matching for student
queries like "I like helping people feel better".
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class ProfileSearch:
    """TF-IDF search index over occupation Markdown profiles."""

    def __init__(self, profiles_dir: str | Path):
        self.profiles_dir = Path(profiles_dir)
        self._codes: list[str] = []
        self._titles: list[str] = []
        self._contents: list[str] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._tfidf_matrix = None

        self._load_profiles()
        self._build_index()

    def _load_profiles(self):
        """Load all Markdown profile files."""
        profile_files = sorted(self.profiles_dir.glob("*.md"))
        if not profile_files:
            logger.warning("No profile files found in %s", self.profiles_dir)
            return

        for f in profile_files:
            code = f.stem  # filename without .md
            content = f.read_text(encoding="utf-8")

            # Extract title from first line (# Title)
            first_line = content.split("\n", 1)[0]
            title = first_line.lstrip("# ").strip()

            self._codes.append(code)
            self._titles.append(title)
            self._contents.append(content)

        logger.info("Loaded %d occupation profiles", len(self._codes))

    def _build_index(self):
        """Build TF-IDF index from profile contents."""
        if not self._contents:
            return

        # Use bigrams and custom stop words tuned for career data
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=20000,
            stop_words="english",
            sublinear_tf=True,  # log(1 + tf) — better for long documents
            min_df=1,
            max_df=0.95,
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(self._contents)
        logger.info("Built TF-IDF index: %d docs, %d features",
                     self._tfidf_matrix.shape[0], self._tfidf_matrix.shape[1])

    def search(self, query: str, top_n: int = 10) -> list[dict]:
        """
        Search profiles by natural language query.

        Returns list of dicts with: code, title, score, snippet
        """
        if self._vectorizer is None or self._tfidf_matrix is None:
            return []

        query_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

        # Get top N indices sorted by score
        top_indices = np.argsort(scores)[::-1][:top_n]

        results = []
        for idx in top_indices:
            if scores[idx] < 0.01:  # skip near-zero matches
                break
            # Extract a short snippet — first 300 chars after the header
            content = self._contents[idx]
            # Skip past the title and metadata to get description
            snippet = self._extract_snippet(content, query)
            results.append({
                "code": self._codes[idx],
                "title": self._titles[idx],
                "score": round(float(scores[idx]), 4),
                "snippet": snippet,
            })

        return results

    def _extract_snippet(self, content: str, query: str, max_len: int = 300) -> str:
        """Extract the most relevant snippet from a profile."""
        # Try to find the description (blockquote after header)
        lines = content.split("\n")
        for line in lines:
            if line.startswith("> "):
                return line[2:].strip()[:max_len]

        # Fallback: first non-empty, non-header line
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("**Code"):
                return stripped[:max_len]

        return content[:max_len]

    def get_profile(self, code: str) -> Optional[str]:
        """Get the full Markdown profile for an occupation code."""
        try:
            idx = self._codes.index(code)
            return self._contents[idx]
        except ValueError:
            return None

    def get_profile_from_file(self, code: str) -> Optional[str]:
        """Read a profile directly from disk (for freshness)."""
        filepath = self.profiles_dir / f"{code}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return None

    @property
    def count(self) -> int:
        return len(self._codes)


def load_profile_search(profiles_dir: str | Path | None = None) -> Optional[ProfileSearch]:
    """Load the profile search index, returns None if no profiles exist."""
    if profiles_dir is None:
        profiles_dir = Path(__file__).parent.parent / "data" / "profiles"

    profiles_dir = Path(profiles_dir)
    if not profiles_dir.exists() or not list(profiles_dir.glob("*.md")):
        logger.warning("No profiles directory or no .md files at %s", profiles_dir)
        return None

    return ProfileSearch(profiles_dir)
