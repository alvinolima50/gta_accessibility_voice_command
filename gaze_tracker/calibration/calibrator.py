"""Calibração: mostra pontos na tela, coleta amostras, ajusta o mapper.

Rotina:
  1. Abre overlay fullscreen
  2. Para cada ponto da grade:
     - Mostra 600ms de "atenção" (sem coletar, só chamar atenção)
     - Coleta ~30 amostras em 1500ms
     - Se a confiança média for baixa, repete o ponto uma vez
  3. Fecha overlay, ajusta o modelo, retorna a Calibration.
"""

import time
from typing import List, Optional

import numpy as np

from gaze_tracker.calibration.overlay import CalibrationOverlay, grid_points
from gaze_tracker.core.gaze_estimator import GazeFeatures, compute_features
from gaze_tracker.core.screen_mapper import Calibration, fit, build_features  # noqa: F401
from gaze_tracker.core.tracker import FaceTracker


def _mean_features(samples: List[GazeFeatures]) -> tuple[np.ndarray, float]:
    if not samples:
        return np.zeros(4), 0.0
    arr = np.array([s.as_array() for s in samples])
    conf = float(np.mean([s.confidence for s in samples]))
    return arr.mean(axis=0), conf


def run_calibration(tracker: FaceTracker, quick: bool = False
                    ) -> Optional[Calibration]:
    """Roda a calibração interativa. Retorna Calibration ou None se abortada.

    `tracker` deve estar RODANDO (start() já chamado). Usa o last_frame() dele
    em loop pra coletar amostras.
    """
    overlay = CalibrationOverlay()
    overlay.open()

    w, h = overlay.size
    n = 5 if quick else 9
    points = grid_points(w, h, n=n)

    # Intro
    overlay.render_message(
        "Calibrando — olhe pro ponto que aparecer",
        "Mantenha a cabeça estável e os olhos no ponto até ele trocar."
    )
    t0 = time.monotonic()
    while time.monotonic() - t0 < 2.0:
        key = overlay.render_message(
            "Calibrando — olhe pro ponto que aparecer",
            "Mantenha a cabeça estável e os olhos no ponto até ele trocar."
        )
        if key == chr(27):  # ESC
            overlay.close()
            return None

    features_list: list[np.ndarray] = []
    targets_list: list[tuple[int, int]] = []

    aborted = False
    for px, py in points:
        got = _collect_point(tracker, overlay, px, py)
        if got is None:
            # Sem amostras suficientes OU ESC pressionado. Verifica o tracker.
            if tracker.last_frame() is None:
                # Webcam nunca entregou frame — aborta com mensagem.
                overlay.render_message(
                    "Webcam não está entregando frames",
                    "Feche o overlay (ESC) e veja o console.",
                )
                time.sleep(2.0)
                aborted = True
                break
            # Tenta uma vez mais esse ponto
            got = _collect_point(tracker, overlay, px, py)
            if got is None:
                aborted = True
                break
        feat_mean, conf = got
        if conf < 0.4:
            # Qualidade baixa — tenta uma vez mais
            got = _collect_point(tracker, overlay, px, py)
            if got is None:
                aborted = True
                break
            feat_mean, conf = got
        features_list.append(feat_mean)
        targets_list.append((px, py))

    if aborted:
        overlay.close()
        return None

    overlay.close()

    if len(features_list) < 4:
        print("[calibration] amostras insuficientes", flush=True)
        return None

    # Monta matriz de features polinomiais
    phi = np.array([build_features(*f) for f in features_list])
    tgt = np.array(targets_list, dtype=np.float64)
    cal = fit(phi, tgt, screen_w=w, screen_h=h)
    print(f"[calibration] concluída com {len(features_list)} pontos "
          f"({'rápida' if quick else 'completa'})", flush=True)
    return cal


def _collect_point(tracker: FaceTracker, overlay: CalibrationOverlay,
                   px: int, py: int
                   ) -> Optional[tuple[np.ndarray, float]]:
    # 600ms de foco antes de coletar
    t0 = time.monotonic()
    while time.monotonic() - t0 < 0.6:
        key = overlay.render_point(px, py, hint="Olhe para o ponto", progress=0.0)
        if key == chr(27):
            return None

    # 1500ms coletando
    samples: list[GazeFeatures] = []
    duration = 1.5
    t_start = time.monotonic()
    seen_ts = 0.0
    while True:
        dt = time.monotonic() - t_start
        if dt >= duration:
            break
        frame = tracker.last_frame()
        if frame is not None and frame.timestamp != seen_ts:
            seen_ts = frame.timestamp
            feats = compute_features(frame)
            if feats is not None and feats.confidence > 0.1:
                samples.append(feats)
        key = overlay.render_point(px, py, hint="Coletando...",
                                   progress=dt / duration)
        if key == chr(27):
            return None

    if len(samples) < 5:
        # Qualidade insuficiente — devolve None pra caller abortar.
        return None
    return _mean_features(samples)
