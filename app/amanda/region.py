"""Classificação local/longe baseada em cidade do lead."""
from __future__ import annotations

import unicodedata

LOCAL_CITIES = (
    "itajai",
    "navegantes",
    "balneario camboriu",
    "camboriu",
    "itapema",
    "penha",
    "picarras",
    "bombinhas",
    "porto belo",
)


def _normalize(s: str) -> str:
    n = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    return n.strip().lower()


def classify(cidade: str | None) -> str | None:
    if not cidade:
        return None
    norm = _normalize(cidade)
    if not norm:
        return None
    for c in LOCAL_CITIES:
        if c in norm or norm in c:
            return "local"
    return "longe"
