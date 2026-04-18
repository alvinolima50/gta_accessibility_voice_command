"""Matcher de keyword → command_id.

Estratégia:
  1. Normaliza transcript e keywords (lowercase, sem acento, sem pontuação).
  2. Procura cada keyword como substring de palavras inteiras no transcript.
  3. Retorna o comando com a keyword MAIS LONGA que casou
     (evita "corre" pegar antes de "para de correr").

Mantém as palavras-chave flexíveis mas determinísticas — sem LLM.
"""

import re
import unicodedata
from typing import List, Optional, Tuple

from commands.registry import Command


def _normalize(text: str) -> str:
    if not text:
        return ""
    # Remove acentos
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Remove pontuação mantendo letras/números/espaços
    ascii_text = re.sub(r"[^\w\s]", " ", ascii_text, flags=re.UNICODE)
    # Colapsa espaços
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _word_substring_match(haystack_norm: str, needle_norm: str) -> bool:
    """True se `needle_norm` aparece em `haystack_norm` respeitando
    fronteiras de palavra (evita que 'anda' case com 'andorinha')."""
    if not needle_norm:
        return False
    pattern = r"(?:^|\s)" + re.escape(needle_norm) + r"(?:\s|$)"
    return re.search(pattern, haystack_norm) is not None


class Matcher:
    def __init__(self, commands: List[Command]) -> None:
        self.update(commands)

    def update(self, commands: List[Command]) -> None:
        # Pré-normaliza todas as keywords; ordena por comprimento desc.
        items: list[tuple[str, Command, str]] = []
        for cmd in commands:
            for kw in cmd.keywords:
                norm = _normalize(kw)
                if norm:
                    items.append((norm, cmd, kw))
        items.sort(key=lambda t: len(t[0]), reverse=True)
        self._items = items

    def match(self, transcript: str) -> Optional[Tuple[Command, str]]:
        """Retorna (Command, keyword_original) ou None."""
        norm = _normalize(transcript)
        if not norm:
            return None
        for kw_norm, cmd, kw_raw in self._items:
            if _word_substring_match(norm, kw_norm):
                return cmd, kw_raw
        return None
