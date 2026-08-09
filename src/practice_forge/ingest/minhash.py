"""Cross-scan / cross-reprint dedup (S1b): MinHash-over-shingles Jaccard
estimate, computed from up to 200 sampled pages, so re-scanning or
re-uploading the same book under a different filename doesn't create a
second Book and doesn't reset that course's issued-problem history."""

from __future__ import annotations

import re

import numpy as np
from datasketch import MinHash

NUM_PERM = 128
SHINGLE_WORDS = 5
MAX_SAMPLED_PAGES = 200
# Pinned explicitly (datasketch >= 2.0 requires it on reconstruction from
# raw hashvalues, since values alone don't identify which scheme produced
# them) rather than relying on MinHash()'s implicit default staying stable.
SCHEME = "affine32"


def _shingles(text: str, k: int = SHINGLE_WORDS) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def build_minhash(page_texts: list[str], num_perm: int = NUM_PERM) -> MinHash:
    sampled = page_texts[:MAX_SAMPLED_PAGES]
    m = MinHash(num_perm=num_perm, scheme=SCHEME)
    for text in sampled:
        for shingle in _shingles(text):
            m.update(shingle.encode("utf-8"))
    return m


def signature_to_list(m: MinHash) -> list[int]:
    return [int(v) for v in m.hashvalues]


def list_to_minhash(values: list[int], num_perm: int = NUM_PERM) -> MinHash:
    return MinHash(
        num_perm=num_perm, hashvalues=np.array(values, dtype=np.uint64), scheme=SCHEME
    )


def jaccard(a: MinHash, b: MinHash) -> float:
    return float(a.jaccard(b))
