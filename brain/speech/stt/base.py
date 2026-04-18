from abc import ABC, abstractmethod
from typing import Callable


class STTSession(ABC):
    @abstractmethod
    def feed(self, pcm_bytes: bytes) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class STTProvider(ABC):
    @abstractmethod
    def open_session(self, on_final: Callable[[str], None], label: str = "stt") -> STTSession: ...
