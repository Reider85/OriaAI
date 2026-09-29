"""Mock retrieval pipeline for A/B testing RAG quality."""

import math
import re
import time
from collections import Counter
from typing import Any

import numpy as np

from llm_client.rag.config import RetrievalStrategy, RetrieverConfig
from llm_client.rag.pipeline import rerank_after_fusion

# Mirrors sklearn's TfidfVectorizer default token_pattern r"(?u)\b\w\w+\b"
_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")

# Mirrors sklearn.feature_extraction.text.ENGLISH_STOP_WORDS (stop_words="english").
_ENGLISH_STOP_WORDS = frozenset(
    ["a", "about", "above", "across", "after", "afterwards", "again", "against", "ain", "all", "almost", "alone", "along", "already", "also", "although", "always", "am", "among", "amongst", "amoungst", "amount", "an", "and", "another", "any", "anyhow", "anyone", "anything", "anyway", "anywhere", "are", "around", "as", "at", "back", "be", "became", "because", "become", "becomes", "becoming", "been", "before", "beforehand", "behind", "being", "below", "beside", "besides", "between", "beyond", "bill", "both", "bottom", "but", "by", "call", "can", "cannot", "cant", "co", "con", "could", "couldnt", "cry", "de", "describe", "detail", "do", "done", "down", "due", "during", "each", "eg", "eight", "either", "eleven", "else", "elsewhere", "empty", "enough", "etc", "even", "ever", "every", "everyone", "everything", "everywhere", "except", "few", "fifteen", "fill", "find", "fire", "first", "five", "for", "former", "formerly", "forty", "found", "four", "from", "front", "full", "further", "get", "give", "go", "had", "has", "hasnt", "have", "he", "hence", "her", "here", "hereafter", "hereby", "herein", "hereupon", "hers", "herself", "him", "himself", "his", "how", "however", "hundred", "i", "ie", "if", "in", "inc", "indeed", "interest", "into", "is", "it", "its", "itself", "keep", "last", "latter", "latterly", "least", "less", "ltd", "made", "many", "may", "me", "meanwhile", "meantime", "might", "mill", "mine", "more", "moreover", "most", "mostly", "move", "much", "must", "my", "myself", "name", "namely", "neither", "never", "nevertheless", "next", "nine", "no", "nobody", "none", "noone", "nope", "nor", "not", "nothing", "now", "nowhere", "of", "off", "often", "on", "once", "one", "only", "onto", "or", "other", "others", "otherwise", "our", "ours", "ourselves", "out", "over", "own", "part", "per", "perhaps", "please", "put", "rather", "re", "same", "see", "seem", "seemed", "seeming", "seems", "serious", "several", "she", "should", "show", "side", "since", "sincere", "six", "sixty", "so", "some", "somehow", "someone", "something", "sometime", "sometimes", "somewhere", "still", "such", "system", "take", "ten", "than", "that", "the", "their", "them", "themselves", "then", "thence", "there", "thereafter", "thereby", "therefore", "therein", "theres", "thereupon", "these", "they", "thick", "thin", "third", "this", "those", "though", "three", "through", "throughout", "thru", "thus", "to", "together", "too", "top", "toward", "towards", "twelve", "twenty", "two", "un", "under", "until", "up", "upon", "us", "very", "via", "was", "we", "well", "were", "what", "whatever", "when", "whence", "whenever", "where", "whereafter", "whereas", "whereby", "wherein", "whereupon", "wherever", "whether", "which", "while", "whither", "who", "whoever", "whole", "whom", "whose", "why", "will", "with", "within", "without", "would", "yet", "you", "your", "yours", "yourself", "yourselves"]
)


def _analyze(text: str, ngram_range: tuple[int, int] = (1, 2)) -> list[str]:
    """Tokenize and produce n-grams the same way sklearn's TfidfVectorizer does.

    Lowercases, keeps tokens of 2+ word characters, drops English stop words,
    then builds n-grams from the filtered token sequence.
    """
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _ENGLISH_STOP_WORDS]
    ngrams = list(tokens)
    for n in range(2, ngram_range[1] + 1):
        ngrams.extend(" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1))
    return ngrams


def _bm25_tokens(text: str) -> list[str]:
    """Tokenize for BM25 scoring (kept independent from the TF-IDF analyzer)."""
    return re.findall(r"\b\w+\b", text.lower())


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization; all-zero rows are left untouched."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


class MockRetrievalPipeline:
    """Mock RAG pipeline that simulates vector + BM25 retrieval + reranking.

    For A/B testing purposes when real retrieval isn't implemented yet.
    Uses a pure-NumPy TF-IDF for vector similarity and BM25 term frequency for
    lexical search, so the evaluation harness has no extra ML dependencies.
    """

    def __init__(
        self,
        corpus: list[dict[str, Any]],
        *,
        ngram_range: tuple[int, int] = (1, 2),
        min_df: int = 1,
        max_df: float = 0.8,
    ):
        """Initialize with document corpus.

        Args:
            corpus: List of documents with 'id', 'content', 'metadata' fields
            ngram_range: TF-IDF n-gram range, mirrors TfidfVectorizer
            min_df: Minimum document frequency for a term to be kept
            max_df: Maximum document frequency ratio for a term to be kept
        """
        self.corpus = corpus
        self.corpus_texts = [doc["content"] for doc in corpus]
        self.corpus_ids = [doc["id"] for doc in corpus]

        self._tfidf = _TfidfIndex(
            self.corpus_texts,
            ngram_range=ngram_range,
            min_df=min_df,
            max_df=max_df,
        )

        # Pre-compute document lengths for BM25
        self.doc_lengths = [len(doc["content"].split()) for doc in corpus]
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths)

        # BM25 tokenized corpus + document frequency per token (pre-computed so
        # scoring is O(len(query)) instead of rescanning every document).
        self._corpus_tokens = [_bm25_tokens(text) for text in self.corpus_texts]
        self._doc_freq: Counter[str] = Counter()
        for tokens in self._corpus_tokens:
            self._doc_freq.update(set(tokens))

        # BM25 parameters
        self.k1 = 1.2  # document saturation parameter
        self.b = 0.75  # length normalization parameter

    async def search(self, query: str, config: RetrieverConfig) -> list[dict[str, Any]]:
        """Perform search based on retrieval strategy.

        Args:
            query: Search query
            config: RetrieverConfig with retrieval strategy and parameters

        Returns:
            List of retrieved documents with scores
        """
        start_time = time.time()
        strategy = RetrievalStrategy(config.retrieval_strategy)

        if strategy is RetrievalStrategy.VECTOR:
            vector_docs = await self._vector_search(query, config.vector_top_k)
            bm25_docs = []
        elif strategy is RetrievalStrategy.BM25:
            vector_docs = []
            bm25_docs = await self._bm25_search(query, config.bm25_top_k)
        else:
            vector_docs = await self._vector_search(query, config.vector_top_k)
            bm25_docs = await self._bm25_search(query, config.bm25_top_k)
            vector_docs = await self._rrf_fusion(vector_docs, bm25_docs, config.hybrid_top_k)

        # Apply reranking if enabled
        if config.reranker_enabled:
            reranked_docs = await rerank_after_fusion(
                query=query,
                fused_docs=vector_docs,
                config=config,
            )
        else:
            reranked_docs = vector_docs[: config.reranker_top_k]

        latency_ms = (time.time() - start_time) * 1000

        # Add latency to each document for reporting
        for doc in reranked_docs:
            doc["latency_ms"] = latency_ms

        return reranked_docs[: config.reranker_top_k]

    async def _vector_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Simulate vector search using TF-IDF cosine similarity."""
        similarities = self._tfidf.similarities(query)

        # Get top-k documents
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            doc = self.corpus[idx].copy()
            doc["score"] = float(similarities[idx])
            doc["retrieval_method"] = "vector"
            results.append(doc)

        return results

    async def _bm25_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Simulate BM25 search using term frequency scoring."""
        query_terms = _bm25_tokens(query)

        scores = []
        for i, doc_terms in enumerate(self._corpus_tokens):
            # Calculate BM25 score
            score = 0.0
            length_norm = self.k1 * (
                1 - self.b + self.b * (self.doc_lengths[i] / self.avg_doc_length)
            )
            for term in set(query_terms):
                term_freq = doc_terms.count(term)
                if term_freq > 0:
                    # BM25 formula (idf with the +1 smoothing already included)
                    idf = math.log((len(self.corpus) + 1) / (self._doc_freq[term] + 1) + 1)
                    numerator = term_freq * (self.k1 + 1)
                    score += idf * (numerator / (term_freq + length_norm))

            if score > 0:
                scores.append((i, score))

        # Sort by score and get top-k
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scores[:top_k]:
            doc = self.corpus[idx].copy()
            doc["score"] = score
            doc["retrieval_method"] = "bm25"
            results.append(doc)

        return results

    async def _rrf_fusion(
        self,
        vector_docs: list[dict[str, Any]],
        bm25_docs: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Reciprocal Rank Fusion of vector and BM25 results."""
        # Create a mapping of document IDs to scores from both methods
        doc_scores: dict[str, dict[str, Any]] = {}

        # Add vector scores
        for rank, doc in enumerate(vector_docs):
            doc_id = doc["id"]
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {"vector_score": 0.0, "bm25_score": 0.0, "doc": doc}
            doc_scores[doc_id]["vector_score"] += 1.0 / (rank + 1)

        # Add BM25 scores
        for rank, doc in enumerate(bm25_docs):
            doc_id = doc["id"]
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {"vector_score": 0.0, "bm25_score": 0.0, "doc": doc}
            doc_scores[doc_id]["bm25_score"] += 1.0 / (rank + 1)

        # Apply RRF: score = 1 / (rank_vector + rank_bm25)
        fused_docs = []
        for doc_id, scores in doc_scores.items():
            rrf_score = 1.0 / (scores["vector_score"] + scores["bm25_score"])
            fused_doc = scores["doc"].copy()
            fused_doc["score"] = rrf_score
            fused_doc["retrieval_method"] = "hybrid"
            fused_docs.append(fused_doc)

        # Sort by RRF score and return top-k
        fused_docs.sort(key=lambda x: x["score"], reverse=True)
        return fused_docs[:top_k]


class _TfidfIndex:
    """Minimal TF-IDF index with a cosine-similarity query path.

    Reproduces the sklearn ``TfidfVectorizer(stop_words="english", min_df=1,
    max_df=0.8)`` semantics used by the previous implementation, so A/B test
    numbers stay comparable, without pulling in scikit-learn.
    """

    def __init__(
        self,
        texts: list[str],
        *,
        ngram_range: tuple[int, int] = (1, 2),
        min_df: int = 1,
        max_df: float = 0.8,
    ) -> None:
        analyzed = [_analyze(text, ngram_range) for text in texts]
        n_docs = len(analyzed)

        doc_freq: Counter[str] = Counter()
        for terms in analyzed:
            doc_freq.update(set(terms))

        max_doc_count = max_df * n_docs if isinstance(max_df, float) else max_df
        self._vocabulary = {
            term: idx
            for idx, term in enumerate(
                sorted(
                    term
                    for term, df in doc_freq.items()
                    if min_df <= df <= max_doc_count
                )
            )
        }
        n_features = len(self._vocabulary)
        matrix = np.zeros((n_docs, n_features), dtype=np.float64)
        for row, terms in enumerate(analyzed):
            for term, tf in Counter(terms).items():
                col = self._vocabulary.get(term)
                if col is None:
                    continue
                # smooth_idf=True, as in sklearn's default
                idf = math.log((1 + n_docs) / (1 + doc_freq[term])) + 1
                matrix[row, col] = tf * idf

        self._matrix = _l2_normalize(matrix)
        self._n_docs = n_docs
        self._doc_freq = doc_freq

    def similarities(self, query: str) -> np.ndarray:
        """Return cosine similarity of the query against every document."""
        terms = _analyze(query)
        vector = np.zeros(len(self._vocabulary), dtype=np.float64)
        for term, tf in Counter(terms).items():
            col = self._vocabulary.get(term)
            if col is None:
                continue
            idf = math.log((1 + self._n_docs) / (1 + self._doc_freq[term])) + 1
            vector[col] = tf * idf

        norm = np.linalg.norm(vector)
        if norm > 0.0:
            vector /= norm
        return self._matrix @ vector
