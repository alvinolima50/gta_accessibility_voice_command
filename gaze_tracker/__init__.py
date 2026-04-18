"""gaze_tracker — eye tracker com webcam baseado em MediaPipe.

Uso mínimo:

    from gaze_tracker import GazeTracker
    gt = GazeTracker()
    if not gt.is_calibrated():
        gt.run_calibration()
    gt.start()
    point = gt.get_gaze()  # GazePoint(x, y, confidence) ou None
"""

from gaze_tracker.api import GazePoint, GazeTracker

__all__ = ["GazeTracker", "GazePoint"]
