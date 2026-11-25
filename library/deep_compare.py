"""
library/deep_compare.py — 加強比對: are two videos the same even when one has its start / end cut off
or is scaled, cropped or letterboxed? Run by hand for exactly two videos (never automatically), it
decodes far more than the normal check (library/similarity.py, which compares fixed screenshots at
10 / 50 / 90 % and so fails as soon as the timing or the framing differs).

1. Time offset: the brightness of the middle of the picture, sampled RATE times a second over the
   first WINDOW seconds of each video, barely changes with scaling, cropping, borders or watermarks.
   The shift that best correlates the two curves (and the change between frames, which marks scene
   cuts) says how many seconds were cut from one of them. Starts aligned and ends aligned are tried
   too, in case the curves are flat.
2. Verification: SAMPLES frame pairs at matching moments over the overlap. Black borders are trimmed,
   ORB feature points are matched and a scale + shift (+ small rotation) transform is fitted with
   RANSAC; the second frame is warped onto the first and SSIM is taken only where both have picture.
   A pair without such a transform falls back to plain SSIM of the trimmed frames.
3. Score = median of the pair scores (0..100).
"""

import base64
import logging
import subprocess
from typing import List, Optional, Tuple

import numpy as np

from . import media, similarity

logger = logging.getLogger(__name__)

WINDOW = 180.0          # seconds from the start of each video used to find the time offset
RATE = 4                # brightness samples per second
MAX_SHIFT = 150.0       # largest offset tried (s): more cut from the start than this isn't found
MIN_OVERLAP = 30.0      # seconds the two videos must share (less for short videos)
SAMPLES = 8             # frame pairs compared at the chosen offset
QUICK = 3               # frame pairs used to choose between offset candidates
FRAME_W = 640           # frames are compared at this width
PREVIEWS = 3            # frame pairs sent back as small pictures

_CURVE_W, _CURVE_H = 32, 18


def _ffmpeg() -> str:
    ff = media.find_tool('ffmpeg')
    if not ff:
        raise RuntimeError('找不到 ffmpeg')
    return ff


def _run(cmd: List[str], timeout: float) -> bytes:
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=media._NO_WINDOW)
    return proc.stdout


def _curves(path: str, seconds: float) -> Tuple[np.ndarray, np.ndarray]:
    """Brightness of the picture's middle and the change from the previous frame, RATE per second."""
    out = _run([_ffmpeg(), '-v', 'error', '-t', f'{seconds:.2f}', '-i', path, '-an', '-sn',
                '-vf', f'fps={RATE},scale={_CURVE_W}:{_CURVE_H},format=gray', '-f', 'rawvideo', '-'], timeout=300)
    frames = np.frombuffer(out, np.uint8)
    frames = frames[:len(frames) // (_CURVE_W * _CURVE_H) * _CURVE_W * _CURVE_H]
    frames = frames.reshape(-1, _CURVE_H, _CURVE_W).astype(np.float32)[:, 3:-3, 5:-5]   # skip borders
    level = frames.mean(axis=(1, 2))
    change = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2)) if len(frames) > 1 else np.zeros(0, np.float32)
    return level, change


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 1e-6 else 0.0


def _best_shift(ca: tuple, cb: tuple, min_overlap: float) -> Tuple[float, float]:
    """(offset s, correlation) where B(t) shows A(t + offset)."""
    best = (0.0, -1.0)
    max_shift = int(MAX_SHIFT * RATE)
    need = max(int(min_overlap * RATE), 8)
    for s in range(-max_shift, max_shift + 1):
        score, used = 0.0, 0
        for a, b in zip(ca, cb):
            ia, ib = max(0, s), max(0, -s)
            n = min(len(a) - ia, len(b) - ib)
            if n < need:
                continue
            score += _corr(a[ia:ia + n], b[ib:ib + n])
            used += 1
        if used and score / used > best[1]:
            best = (s / RATE, score / used)
    return best


def _frame(path: str, t: float) -> Optional[np.ndarray]:
    import cv2
    out = _run([_ffmpeg(), '-v', 'error', '-ss', f'{max(0.0, t):.3f}', '-i', path, '-frames:v', '1', '-an', '-sn',
                '-vf', f'scale={FRAME_W}:-2', '-f', 'image2pipe', '-vcodec', 'png', '-'], timeout=60)
    if not out:
        return None
    return cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)


def _trim(gray: np.ndarray, level: int = 18) -> np.ndarray:
    """Cut black borders (letterbox / pillarbox)."""
    rows = np.where(gray.mean(axis=1) > level)[0]
    cols = np.where(gray.mean(axis=0) > level)[0]
    if len(rows) < gray.shape[0] * 0.3 or len(cols) < gray.shape[1] * 0.3:
        return gray                          # mostly dark picture: keep it whole
    return gray[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]


def _pair(fa: np.ndarray, fb: np.ndarray) -> Tuple[float, Optional[float]]:
    """(similarity 0..1, scale of B in A or None when no transform was found)."""
    import cv2
    ga = _trim(cv2.cvtColor(fa, cv2.COLOR_BGR2GRAY))
    gb = _trim(cv2.cvtColor(fb, cv2.COLOR_BGR2GRAY))
    orb = cv2.ORB_create(1500)
    ka, da = orb.detectAndCompute(ga, None)
    kb, db = orb.detectAndCompute(gb, None)
    if da is not None and db is not None and len(ka) >= 10 and len(kb) >= 10:
        good = [p[0] for p in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(db, da, k=2)
                if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
        if len(good) >= 12:
            src = np.float32([kb[m.queryIdx].pt for m in good])
            dst = np.float32([ka[m.trainIdx].pt for m in good])
            m, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
            if m is not None and inliers is not None and int(inliers.sum()) >= 10:
                scale = float(np.hypot(m[0, 0], m[1, 0]))
                if 0.25 < scale < 4:
                    h, w = ga.shape
                    warped = cv2.warpAffine(gb, m, (w, h))
                    mask = cv2.warpAffine(np.full(gb.shape, 255, np.uint8), m, (w, h))
                    mask = cv2.erode(mask, np.ones((9, 9), np.uint8)) > 0
                    if mask.mean() > 0.2:
                        smap = similarity.ssim_map(ga, warped)
                        pad = (ga.shape[0] - smap.shape[0]) // 2
                        inside = mask[pad:pad + smap.shape[0], pad:pad + smap.shape[1]]
                        return max(0.0, float(smap[inside].mean())), scale
    size = similarity.SIG_SIZE
    plain = similarity.ssim(cv2.resize(ga, size, interpolation=cv2.INTER_AREA), cv2.resize(gb, size, interpolation=cv2.INTER_AREA))
    return max(0.0, plain), None


def _times(offset: float, da: float, db: float, count: int) -> List[Tuple[float, float]]:
    """`count` moments (time in A, time in B) spread over the part both videos show."""
    start, end = max(0.0, -offset), min(db, da - offset)      # in B's time
    margin = (end - start) * 0.05
    start, end = start + margin, end - margin
    return [(start + offset + (end - start) * (i + 0.5) / count, start + (end - start) * (i + 0.5) / count)
            for i in range(count)]


def _overlap(offset: float, da: float, db: float) -> float:
    return min(db, da - offset) - max(0.0, -offset)


def _thumb(frame: np.ndarray) -> str:
    import cv2
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (320, max(2, round(h * 320 / w))), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return 'data:image/jpeg;base64,' + base64.b64encode(jpg.tobytes()).decode() if ok else ''


def _score_at(path_a: str, path_b: str, moments: List[Tuple[float, float]], keep: bool = False) -> dict:
    scores, scales, kept = [], [], []
    for ta, tb in moments:
        fa, fb = _frame(path_a, ta), _frame(path_b, tb)
        if fa is None or fb is None:
            continue
        s, scale = _pair(fa, fb)
        scores.append(s)
        if scale:
            scales.append(scale)
        if keep:
            kept.append((ta, tb, s, fa, fb))
    return {'score': float(np.median(scores)) * 100 if scores else 0.0, 'pairs': len(scores),
            'aligned': len(scales), 'scale': float(np.median(scales)) if scales else None, 'kept': kept}


def compare(path_a: str, dur_a: float, path_b: str, dur_b: float) -> dict:
    """Compare A with B (pass the longer one as A). Returns score (0..100), offset (B's start is at
    `offset` s of A), overlap (s), scale (B's picture in A, None if unknown), pairs / aligned counts,
    correlation of the brightness curves and a few frame pairs as small JPEG data URLs."""
    if dur_a <= 0 or dur_b <= 0:
        raise RuntimeError('沒有影片長度資訊')
    min_overlap = min(MIN_OVERLAP, 0.5 * min(dur_a, dur_b))
    ca = _curves(path_a, min(dur_a, WINDOW))
    cb = _curves(path_b, min(dur_b, WINDOW))
    shift, corr = _best_shift(ca, cb, min(min_overlap, min(len(ca[0]), len(cb[0])) / RATE * 0.5))
    candidates = []
    for off in (shift, 0.0, dur_a - dur_b):                   # best correlation, starts aligned, ends aligned
        if _overlap(off, dur_a, dur_b) >= min_overlap and all(abs(off - c) > 1.0 for c in candidates):
            candidates.append(off)
    if not candidates:
        raise RuntimeError('兩部影片沒有足夠的重疊部分可以比對')
    if len(candidates) > 1:
        quick = [(_score_at(path_a, path_b, _times(off, dur_a, dur_b, QUICK))['score'], off) for off in candidates]
        offset = max(quick)[1]
    else:
        offset = candidates[0]
    result = _score_at(path_a, path_b, _times(offset, dur_a, dur_b, SAMPLES), keep=True)
    kept = result.pop('kept')
    step = max(1, len(kept) // PREVIEWS)
    previews = [{'a': _thumb(fa), 'b': _thumb(fb), 'time_a': round(ta, 1), 'time_b': round(tb, 1), 'score': round(s * 100)}
                for ta, tb, s, fa, fb in kept[step // 2::step][:PREVIEWS]]
    logger.info(f"加強比對：{path_a} / {path_b} 相似度 {result['score']:.0f}%（偏移 {offset:.1f} 秒，"
                f"對齊 {result['aligned']}/{result['pairs']}，曲線相關 {corr:.2f}）")
    return {**result, 'offset': round(offset, 1), 'overlap': round(_overlap(offset, dur_a, dur_b), 1),
            'correlation': round(corr, 2), 'previews': previews}
