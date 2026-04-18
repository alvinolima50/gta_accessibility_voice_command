"""One Euro filter — suavização adaptativa pra input gestual.

Referência: Casiez, Roussel & Vogel (2012) — "1€ Filter: A Simple Speed-based
Low-pass Filter for Noisy Input in Interactive Systems".

Dois parâmetros:
  min_cutoff — cutoff quando parado (mais baixo = mais suave)
  beta       — velocidade com que cutoff sobe com o movimento (mais alto = mais
               responsivo)
Defaults (min_cutoff=1.0, beta=0.007) são os recomendados pelos autores.
"""

import math
import time
from typing import Optional


def _lowpass(alpha: float, x: float, prev: float) -> float:
    return alpha * x + (1.0 - alpha) * prev


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007,
                 d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: Optional[float] = None
        self._dx_prev: float = 0.0
        self._t_prev: Optional[float] = None

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, x: float, t: Optional[float] = None) -> float:
        if t is None:
            t = time.monotonic()
        if self._t_prev is None or self._x_prev is None:
            self._x_prev = x
            self._t_prev = t
            return x
        dt = max(1e-6, t - self._t_prev)
        dx = (x - self._x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = _lowpass(a_d, dx, self._dx_prev)
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _alpha(cutoff, dt)
        x_hat = _lowpass(a, x, self._x_prev)
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


class OneEuroFilter2D:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007) -> None:
        self._fx = OneEuroFilter(min_cutoff, beta)
        self._fy = OneEuroFilter(min_cutoff, beta)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()

    def __call__(self, x: float, y: float, t: Optional[float] = None
                 ) -> tuple[float, float]:
        return self._fx(x, t), self._fy(y, t)
