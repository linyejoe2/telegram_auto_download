"""
library/similarity.py — Is this the same video in another quality / with a watermark?

Videos whose lengths are within DURATION_TOLERANCE seconds are compared on three of their existing
screenshots: the first (10 %), the fifth (50 %) and the last (90 %). Each pair of frames is scored
with SSIM on grayscale images (like example/omni-video-tool), and the mean of the three is the
similarity. The decoded grayscale frames (the cv2.imread output, resized to SIG_SIZE) are cached in
the hidden shots folder as sig.npy and in memory, so a comparison costs no decoding at all.

SSIM here reproduces skimage.metrics.structural_similarity's defaults (7x7 uniform window, sample
covariance, K1=0.01, K2=0.03, data_range 255, borders cropped) with OpenCV, so scikit-image isn't needed.
"""

import os
from typing import Optional

import numpy as np

from . import media

DURATION_TOLERANCE = 3.0          # seconds
DEFAULT_THRESHOLD = 70            # percent
SIG_SIZE = (320, 180)             # (width, height) every frame is resized to
SIG_SHOTS = (0, 4, -1)            # first, fifth and last of the 9 screenshots
SIG_FILE = 'sig.npy'

_WIN = 7
_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Mean SSIM of two same-sized uint8 grayscale images (skimage defaults)."""
    import cv2
    x = a.astype(np.float64)
    y = b.astype(np.float64)
    n = _WIN * _WIN
    cov_norm = n / (n - 1)
    blur = lambda img: cv2.blur(img, (_WIN, _WIN), borderType=cv2.BORDER_REFLECT)
    ux, uy = blur(x), blur(y)
    vx = cov_norm * (blur(x * x) - ux * ux)
    vy = cov_norm * (blur(y * y) - uy * uy)
    vxy = cov_norm * (blur(x * y) - ux * uy)
    s = ((2 * ux * uy + _C1) * (2 * vxy + _C2)) / ((ux ** 2 + uy ** 2 + _C1) * (vx + vy + _C2))
    pad = (_WIN - 1) // 2
    return float(s[pad:-pad, pad:-pad].mean())


def similarity(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    """0..100: mean SSIM of the matching frames of two signatures."""
    scores = [ssim(fa, fb) for fa, fb in zip(sig_a, sig_b)]
    return max(0.0, sum(scores) / len(scores)) * 100


def build_signature(video: str, shots: list) -> Optional[np.ndarray]:
    """Grayscale first / middle / last screenshots as one (3, H, W) uint8 array, cached on disk."""
    import cv2
    if len(shots) < 3:
        return None
    folder = media.shots_dir(video)
    frames = []
    for index in SIG_SHOTS:
        # not cv2.imread: on Windows it can't open paths with non-ASCII characters (Chinese folder / file names)
        try:
            data = np.fromfile(os.path.join(folder, shots[index]), dtype=np.uint8)
        except OSError:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None
        if img is None:
            return None
        frames.append(cv2.resize(img, SIG_SIZE, interpolation=cv2.INTER_AREA))
    sig = np.stack(frames)
    try:
        np.save(os.path.join(folder, SIG_FILE), sig)
    except OSError:
        pass
    return sig


def load_signature(video: str, shots: list) -> Optional[np.ndarray]:
    """The cached signature, rebuilt when missing or older than the screenshots."""
    path = os.path.join(media.shots_dir(video), SIG_FILE)
    try:
        newest_shot = max(os.path.getmtime(os.path.join(media.shots_dir(video), s)) for s in shots)
        if os.path.getmtime(path) >= newest_shot:
            sig = np.load(path)
            if sig.shape == (len(SIG_SHOTS), SIG_SIZE[1], SIG_SIZE[0]):
                return sig
    except (OSError, ValueError):
        pass
    return build_signature(video, shots)
