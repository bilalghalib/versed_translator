"""Optional local multilingual embeddings for semantic span scoring."""

from __future__ import annotations

import math
from collections.abc import Sequence

from versed_translator.align.dp import SpanScorer, pair_score

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class TransformerEmbedder:
    """Small wrapper over Transformers with remote model code disabled."""

    def __init__(
        self,
        model_name_or_path: str = DEFAULT_EMBEDDING_MODEL,
        *,
        batch_size: int = 16,
        max_length: int = 256,
        local_files_only: bool = False,
    ) -> None:
        if batch_size <= 0 or max_length <= 0:
            raise ValueError("batch_size and max_length must be positive")
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - dependency error is explicit
            raise RuntimeError(
                "semantic alignment requires torch and transformers"
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path,
            trust_remote_code=False,
            local_files_only=local_files_only,
        )
        self._model = AutoModel.from_pretrained(
            model_name_or_path,
            trust_remote_code=False,
            local_files_only=local_files_only,
        )
        self._model.eval()
        self.batch_size = batch_size
        self.max_length = max_length
        self.model_name = model_name_or_path
        self._cache: dict[str, tuple[float, ...]] = {}

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        missing = [text for text in dict.fromkeys(texts) if text not in self._cache]
        torch = self._torch
        for start in range(0, len(missing), self.batch_size):
            batch = missing[start : start + self.batch_size]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            with torch.inference_mode():
                output = self._model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).to(output.dtype)
                pooled = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            for text, vector in zip(batch, pooled.tolist(), strict=True):
                self._cache[text] = tuple(float(value) for value in vector)
        return [self._cache[text] for text in texts]

    def scorer(self, arabic: list[str], english: list[str]) -> SpanScorer:
        ar_vectors = self.encode(arabic)
        en_vectors = self.encode(english)

        def score(
            ar_items: list[str],
            ar_start: int,
            ar_end: int,
            en_items: list[str],
            en_start: int,
            en_end: int,
        ) -> float:
            ar_vector = _mean_normalized(ar_vectors[ar_start:ar_end])
            en_vector = _mean_normalized(en_vectors[en_start:en_end])
            cosine = sum(a * b for a, b in zip(ar_vector, en_vector, strict=True))
            heuristic = pair_score(
                " ".join(ar_items[ar_start:ar_end]),
                " ".join(en_items[en_start:en_end]),
            )
            ar_words = sum(len(value.split()) for value in ar_items[ar_start:ar_end])
            en_words = sum(len(value.split()) for value in en_items[en_start:en_end])
            expected_english = max(1.0, ar_words * 1.55)
            length_cost = abs(math.log(max(1.0, en_words) / expected_english))
            # The semantic term owns the decision.  Transliteration/numbers and
            # length break close calls; they cannot become hard anchors. The
            # explicit log penalty rejects gross 3-long-spans -> 1-short-span
            # matches that cosine alone can make look topically plausible.
            return 2.4 * cosine + 0.35 * heuristic - 0.45 * length_cost - 1.0

        return score


def _mean_normalized(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    if not vectors:
        return ()
    totals = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            totals[index] += float(value)
    norm = math.sqrt(sum(value * value for value in totals)) or 1.0
    return tuple(value / norm for value in totals)
