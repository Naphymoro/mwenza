from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable, Iterable

from .models import EvidenceSpan, RetrievedEvidence


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w'-]+", text.lower()) if len(token) > 2]


class HybridRetriever:
    """Deterministic lexical retrieval with an injectable semantic scorer.

    A real embedding provider can be added through ``semantic_scorer`` without
    weakening provenance or changing the evidence contract.
    """

    def __init__(self, semantic_scorer: Callable[[str, str], float] | None = None):
        self.semantic_scorer = semantic_scorer

    def search(self, question: str, spans: Iterable[EvidenceSpan], limit: int = 6) -> list[RetrievedEvidence]:
        documents = list(spans)
        query_terms = Counter(tokenize(question))
        doc_terms = [Counter(tokenize(span.text)) for span in documents]
        document_frequency = Counter(term for terms in doc_terms for term in terms)
        results: list[RetrievedEvidence] = []
        for span, terms in zip(documents, doc_terms):
            lexical = 0.0
            for term, query_count in query_terms.items():
                if term not in terms:
                    continue
                idf = math.log((1 + len(documents)) / (1 + document_frequency[term])) + 1
                lexical += idf * ((terms[term] * 2.2) / (terms[term] + 1.2)) * query_count
            lexical /= max(1.0, math.sqrt(len(terms)))
            semantic = self.semantic_scorer(question, span.text) if self.semantic_scorer else 0.0
            score = 0.68 * lexical + 0.32 * semantic
            if score > 0:
                results.append(RetrievedEvidence(span, score, lexical, semantic))
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]
