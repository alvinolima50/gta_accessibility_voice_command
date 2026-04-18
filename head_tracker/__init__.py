"""head_tracker — controla câmera por rotação de cabeça (não por olhar).

Muito mais estável que eye tracking com webcam: a pose da cabeça via solvePnP
do MediaPipe é precisa em sub-grau, sem o jitter da íris.

Uso:
    from head_tracker import HeadTracker
    ht = HeadTracker(camera_index=0)
    ht.start()
    ht.capture_neutral()                 # 2s olhando pra frente
    d = ht.get_direction()               # HeadDirection(dyaw_deg, dpitch_deg, ...)
    ht.set_mouth_callback(lambda o: ...) # reusa o detector de boca do gaze_tracker
"""

from head_tracker.api import HeadDirection, HeadTracker

__all__ = ["HeadTracker", "HeadDirection"]
