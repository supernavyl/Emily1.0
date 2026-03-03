"""BM25 sparse index for keyword-based RAG retrieval.

Tokenization pipeline: lowercase → regex word extraction → stopword removal
→ Porter stemming.  Applied identically to both indexing and search.
"""

from __future__ import annotations

import json
import pickle
import re
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

# ── Tokenization helpers ─────────────────────────────────────────────────

_WORD_RE = re.compile(r"\w+")

_STOPWORDS: frozenset[str] = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren't",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "can't",
        "cannot",
        "could",
        "couldn't",
        "d",
        "did",
        "didn't",
        "do",
        "does",
        "doesn't",
        "doing",
        "don",
        "don't",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "get",
        "got",
        "had",
        "hadn't",
        "has",
        "hasn't",
        "have",
        "haven't",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "isn't",
        "it",
        "it's",
        "its",
        "itself",
        "just",
        "ll",
        "let",
        "let's",
        "m",
        "me",
        "might",
        "more",
        "most",
        "mustn't",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "o",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "re",
        "s",
        "same",
        "shan't",
        "she",
        "should",
        "shouldn't",
        "so",
        "some",
        "such",
        "t",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "ve",
        "very",
        "was",
        "wasn't",
        "we",
        "were",
        "weren't",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "won't",
        "would",
        "wouldn't",
        "y",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    ]
)


def _stem(word: str) -> str:
    """Minimal Porter stemmer — handles the most impactful suffix rules.

    Covers ~90% of English morphological variance without adding a dependency.
    """
    if len(word) <= 3:
        return word

    # Step 1: plurals and -ed/-ing
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "i"
    elif word.endswith("sses"):
        word = word[:-2]
    elif word.endswith("ss"):
        pass
    elif word.endswith("s") and not word.endswith("us") and len(word) > 3:
        word = word[:-1]

    if word.endswith("eed"):
        if len(word) > 4:
            word = word[:-1]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
        if word.endswith("at") or word.endswith("bl") or word.endswith("iz"):
            word += "e"
        elif len(word) > 2 and word[-1] == word[-2] and word[-1] in "bdfgmnprst":
            word = word[:-1]
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
        if word.endswith("at") or word.endswith("bl") or word.endswith("iz"):
            word += "e"
        elif len(word) > 2 and word[-1] == word[-2] and word[-1] in "bdfgmnprst":
            word = word[:-1]

    # Step 2: common derivational suffixes
    for suffix, min_len in (
        ("ational", 8),
        ("tional", 7),
        ("tion", 5),
        ("ness", 5),
        ("ment", 5),
        ("ful", 4),
        ("ously", 6),
        ("ively", 6),
        ("ize", 4),
        ("ise", 4),
        ("ly", 4),
        ("ous", 4),
        ("ive", 4),
        ("able", 5),
        ("ible", 5),
    ):
        if word.endswith(suffix) and len(word) >= min_len:
            word = word[: -len(suffix)]
            break

    return word


def _tokenize(text: str) -> list[str]:
    """Tokenize text: lowercase, extract words, remove stopwords, stem."""
    words = _WORD_RE.findall(text.lower())
    return [_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1]


# ── BM25 Index ───────────────────────────────────────────────────────────


class BM25Index:
    """
    Rank-BM25 based sparse retrieval index.

    Maintains an in-memory BM25 index over all ingested chunks.
    Serialized to disk for persistence across restarts.

    NOTE: pickle is used here because rank_bm25.BM25Okapi objects are not
    JSON-serializable.  The pickle files are only written and read locally
    by this module — never from untrusted sources.
    """

    def __init__(self, index_path: str = "data/bm25_index") -> None:
        self._index_path = Path(index_path)
        self._model: object | None = None
        self._chunks: list[dict[str, Any]] = []
        self._available = False

    def load(self) -> None:
        """Load the index from disk if it exists, or initialize an empty one."""
        index_file = self._index_path / "bm25.pkl"
        chunks_file = self._index_path / "chunks.json"

        if index_file.exists() and chunks_file.exists():
            try:
                with index_file.open("rb") as f:
                    self._model = pickle.load(f)  # noqa: S301 — trusted local data only
                self._chunks = json.loads(chunks_file.read_text())
                self._available = bool(self._chunks)
                log.info("bm25_index_loaded", n_docs=len(self._chunks))
            except Exception as exc:
                log.warning("bm25_index_load_failed", error=str(exc))

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """
        Add new chunks to the BM25 index.

        Args:
            chunks: List of chunk dicts with "content" and "chunk_id" keys.
        """
        try:
            from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
        except ImportError:
            log.warning("rank_bm25_not_installed_bm25_disabled")
            return

        self._chunks.extend(chunks)
        tokenized = [_tokenize(doc["content"]) for doc in self._chunks]
        self._model = BM25Okapi(tokenized)
        self._available = True
        self._persist()
        log.debug("bm25_index_updated", n_docs=len(self._chunks))

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        """
        Search the BM25 index for the most relevant chunks.

        Args:
            query: Search query string.
            top_k: Number of results to return.

        Returns:
            List of chunk dicts sorted by BM25 score (descending).
        """
        if not self._available or self._model is None:
            return []

        tokenized_query = _tokenize(query)
        if not tokenized_query:
            return []

        scores = self._model.get_scores(tokenized_query)  # type: ignore[union-attr]

        results = []
        for i, score in enumerate(scores):
            if score > 0:
                results.append(
                    {
                        **self._chunks[i],
                        "bm25_score": float(score),
                    }
                )

        results.sort(key=lambda r: r["bm25_score"], reverse=True)
        return results[:top_k]

    def _persist(self) -> None:
        """Persist the index to disk."""
        try:
            self._index_path.mkdir(parents=True, exist_ok=True)
            with (self._index_path / "bm25.pkl").open("wb") as f:
                pickle.dump(self._model, f)
            (self._index_path / "chunks.json").write_text(
                json.dumps(self._chunks, ensure_ascii=False)
            )
        except Exception as exc:
            log.warning("bm25_persist_failed", error=str(exc))
