"""
library/recognize.py — AI 辨識 (v3.5.0): suggest 主演 by face and 系列 by outfit for selected items.

辨識主演: OpenCV YuNet finds the faces in FRAMES frames of a video (or in the photo) and SFace turns
each into a 128-number vector; the faces of one item are grouped into persons. Items already tagged
with 主演 are the reference set (a single-actor item's main person is that actor; multi-actor items
are matched person by person). A person whose face is close enough to an actor's references
(cosine >= FACE_MATCH) gets that actor suggested; the others are grouped across the job as 未知人物
the user can name.

辨識系列: a series = the same person (主演 tag or face) in the same outfit. A vision model on Ollama
(OLLAMA_BASE_URL / OLLAMA_MODEL, set in the Windows app) describes the clothes of each item's main
person; candidate pairs (similar description and colours) are then confirmed by showing the model
both pictures side by side. Items of that person that already have a 系列 take part, so an existing
series name is suggested when the outfit matches.

Jobs run one at a time in a background thread; queue and results are kept in
<downloads>/.tad/recognition.json (a running job starts again after a restart; the caches make that
quick). Face data, crops and outfit descriptions are cached in the item's hidden shots folder
(faces.json, faces.npy, face_N.jpg, body_N.jpg, outfit_N.json), so they move with the file.
Nothing is changed in the library until the user applies a result.
"""

import base64
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import media

logger = logging.getLogger(__name__)

# ── tuning ──
FACE_VERSION = 1
FRAMES = 12                # frames looked at per video (evenly spread, skipping the first / last 5 %)
FRAME_MAX = 1280           # video frames are scaled to at most this on the long side
PHOTO_MAX = 1600           # photos likewise
DET_SCORE = 0.85           # YuNet face confidence
MIN_FACE = 40              # px, short side of the face box in the scaled frame
MAX_PERSONS = 4            # persons kept per item (the most seen)
SAME_IN_ITEM = 0.36        # SFace cosine: OpenCV's own "same person" line, used inside one item
FACE_MATCH = 0.40          # an actor is suggested at this face similarity or more
FACE_CLUSTER = 0.42        # 未知人物 / series identity across different items
HINT_MIN = 0.25            # 未知人物: show the closest actor from this similarity on
OUTFIT_SAME = 60           # the vision model's confidence needed for "same outfit"
NEIGHBORS = 4              # outfit pairs checked per item when a person has many items
ALL_PAIRS_UP_TO = 8        # ... up to this many items every pair is checked
VERIFY_LIMIT = 400         # outfit pair checks per job
SERIES_REFS = 3            # items of an existing series used as its reference
DEFAULT_OLLAMA = 'http://localhost:11434'

KINDS = {'actor': '辨識主演', 'series': '辨識系列'}
AI_FILE_RE = re.compile(r'^(face|body)_\d{1,2}\.jpg$')
MEDIA_URL = '/library/media'      # matches server.PREFIX

MODELS = {
    'detector': ('face_detection_yunet_2023mar.onnx',
                 '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',
                 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'),
    'recognizer': ('face_recognition_sface_2021dec.onnx',
                   '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79',
                   'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'),
}

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
_model_lock = threading.Lock()


class Cancelled(Exception):
    pass


# ─── face models ─────────────────────────────────────────────────────────────

def _model_dirs() -> List[str]:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cache = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), '.cache')
    return [os.path.join(base, 'library', 'models'), os.path.join(cache, 'TelegramAutoDownload', 'models')]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def model_path(key: str, download: bool = True) -> Optional[str]:
    """The ONNX file (bundled, or downloaded once from the official opencv_zoo and checked)."""
    name, sha, url = MODELS[key]
    for folder in _model_dirs():
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    if not download:
        return None
    with _model_lock:
        target = os.path.join(_model_dirs()[-1], name)
        if os.path.isfile(target):
            return target
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + '.part'
        logger.info(f"AI 辨識：下載人臉模型 {name}")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, open(tmp, 'wb') as f:
                shutil.copyfileobj(response, f)
        except OSError as e:
            raise RuntimeError(f'無法下載人臉模型 {name}：{e}')
        if _sha256(tmp) != sha:
            os.remove(tmp)
            raise RuntimeError(f'人臉模型 {name} 下載不完整')
        os.replace(tmp, target)
        return target


class FaceModel:
    """YuNet (find faces) + SFace (face -> normalized 128-number vector). Not thread safe."""

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(model_path('detector'), '', (320, 320), DET_SCORE, 0.3, 50)
        self.recognizer = cv2.FaceRecognizerSF.create(model_path('recognizer'), '')

    def faces(self, image) -> List[dict]:
        h, w = image.shape[:2]
        self.detector.setInputSize((w, h))
        _, rows = self.detector.detect(image)
        found = []
        for row in rows if rows is not None else []:
            x, y, fw, fh = (float(v) for v in row[:4])
            if min(fw, fh) < MIN_FACE:
                continue
            feat = self.recognizer.feature(self.recognizer.alignCrop(image, row)).flatten().astype(np.float32)
            feat /= float(np.linalg.norm(feat)) or 1.0
            found.append({'box': [x, y, fw, fh], 'score': float(row[14]), 'feat': feat})
        return found


# ─── frames & crops ──────────────────────────────────────────────────────────

def _decode(data: bytes):
    import cv2
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def _fit(image, limit: int):
    import cv2
    h, w = image.shape[:2]
    scale = limit / max(h, w)
    if scale >= 1:
        return image
    return cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)


def _video_frames(path: str, duration: float) -> List[tuple]:
    """[(seconds, BGR image)] for FRAMES evenly spread moments."""
    ffmpeg = media.find_tool('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('找不到 ffmpeg（請安裝並加入 PATH，或設定 FFMPEG_PATH）')
    times = [duration * (0.05 + 0.9 * (i + 0.5) / FRAMES) for i in range(FRAMES)] if duration > 0 else [0.0]
    scale = (f"scale=w='if(gte(iw,ih),min({FRAME_MAX},iw),-2)':h='if(gte(iw,ih),-2,min({FRAME_MAX},ih))'")

    def grab(t):
        r = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', f'{t:.2f}', '-i', path,
                            '-frames:v', '1', '-vf', scale, '-c:v', 'bmp', '-f', 'image2pipe', '-'],
                           capture_output=True, timeout=120, creationflags=_NO_WINDOW)
        return t, _decode(r.stdout)

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [(t, img) for t, img in pool.map(grab, times) if img is not None]


def _photo_frames(path: str) -> List[tuple]:
    import cv2
    image = None
    try:
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        pass
    if image is None:                            # e.g. GIF: the thumbnail made by the library
        thumb = os.path.join(media.shots_dir(path), '01.jpg')
        if os.path.isfile(thumb):
            image = cv2.imdecode(np.fromfile(thumb, dtype=np.uint8), cv2.IMREAD_COLOR)
    return [(0.0, _fit(image, PHOTO_MAX))] if image is not None else []


def _crop(image, x0, y0, x1, y1):
    h, w = image.shape[:2]
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return image[y0:y1, x0:x1]


def _face_crop(image, box):
    x, y, w, h = box
    side = max(w, h) * 1.5
    cx, cy = x + w / 2, y + h / 2
    crop = _crop(image, cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
    return None if crop is None else _fit(crop, 160)


def _body_crop(image, box):
    """The person below (and including) the face: what the outfit is judged on."""
    x, y, w, h = box
    cx = x + w / 2
    crop = _crop(image, cx - 2.2 * w, y - 0.4 * h, cx + 2.2 * w, y + 7.5 * h)
    return None if crop is None else _fit(crop, 512)


def _body_rows(image, box) -> float:
    """How much of the body shows below the face, in face heights."""
    x, y, w, h = box
    return max(0.0, (image.shape[0] - (y + h)) / max(h, 1))


def _write_jpg(path: str, image):
    import cv2
    ok, data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if ok:
        data.tofile(path)


def _read_json(path: str):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path: str, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def analyze(path: str, kind: str, duration: float, model_getter) -> dict:
    """Faces of one item, grouped into persons (cached in the shots folder for this file version).
    Returns {'persons': [{count, size, face, body, time}], 'feats': array (persons x 128), 'frames'}."""
    folder = media.shots_dir(path)
    mtime = os.path.getmtime(path)
    info_file, feat_file = os.path.join(folder, 'faces.json'), os.path.join(folder, 'faces.npy')
    cached = _read_json(info_file)
    if (isinstance(cached, dict) and cached.get('version') == FACE_VERSION and cached.get('mtime') == mtime
            and (not cached.get('persons') or os.path.isfile(feat_file))):
        try:
            with open(feat_file, 'rb') as f:
                feats = np.load(f) if cached.get('persons') else np.zeros((0, 128), np.float32)
            if len(feats) == len(cached['persons']):
                return {**cached, 'feats': feats}
        except (OSError, ValueError):
            pass

    frames = _photo_frames(path) if kind == 'photo' else _video_frames(path, duration)
    if not frames:
        raise RuntimeError('無法讀取畫面')
    model = model_getter()
    dets = []
    for index, (t, image) in enumerate(frames):
        for face in model.faces(image):
            face.update(frame=index, time=t)
            dets.append(face)

    # group the faces of this item into persons (biggest faces first)
    dets.sort(key=lambda d: -d['box'][2] * d['box'][3])
    persons = []
    for d in dets:
        best, score = None, SAME_IN_ITEM
        for p in persons:
            if d['frame'] in p['frames']:
                continue                     # one person appears once per frame
            s = float(np.dot(p['mean'], d['feat']))
            if s >= score:
                best, score = p, s
        if best is None:
            persons.append({'dets': [d], 'frames': {d['frame']}, 'sum': d['feat'].copy(), 'mean': d['feat']})
        else:
            best['dets'].append(d)
            best['frames'].add(d['frame'])
            best['sum'] += d['feat']
            best['mean'] = best['sum'] / (float(np.linalg.norm(best['sum'])) or 1.0)

    size = lambda p: float(np.median([min(d['box'][2], d['box'][3]) for d in p['dets']]))
    persons.sort(key=lambda p: (-len(p['dets']), -size(p)))
    if persons:
        if kind == 'photo':                  # every clear face (not the small ones in the background)
            biggest = max(size(p) for p in persons)
            persons = [p for p in persons if size(p) >= 0.35 * biggest]
        elif len(frames) > 1:                # people seen in a few frames are passers-by
            top = len(persons[0]['dets'])
            persons = [p for p in persons if len(p['dets']) >= max(2, 0.3 * top)] or persons[:1]
        persons = persons[:MAX_PERSONS]

    os.makedirs(folder, exist_ok=True)
    media._hide(folder)
    for old in os.listdir(folder):
        if AI_FILE_RE.match(old) or old.startswith('outfit_'):
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
    out = []
    for i, p in enumerate(persons, 1):
        big = max(p['dets'], key=lambda d: d['box'][2] * d['box'][3])
        # the outfit frame: as much body below the face as possible, the face not tiny
        body = max(p['dets'], key=lambda d: min(_body_rows(frames[d['frame']][1], d['box']), 5)
                   * min(d['box'][3], 150))
        face_img = _face_crop(frames[big['frame']][1], big['box'])
        body_img = _body_crop(frames[body['frame']][1], body['box'])
        entry = {'count': len(p['dets']), 'size': round(size(p)), 'time': round(body['time'], 1),
                 'face': None, 'body': None, 'body_rows': round(_body_rows(frames[body['frame']][1], body['box']), 1)}
        if face_img is not None:
            entry['face'] = f'face_{i}.jpg'
            _write_jpg(os.path.join(folder, entry['face']), face_img)
        if body_img is not None:
            entry['body'] = f'body_{i}.jpg'
            _write_jpg(os.path.join(folder, entry['body']), body_img)
        out.append(entry)
    feats = np.stack([p['mean'] for p in persons]).astype(np.float32) if persons else np.zeros((0, 128), np.float32)
    if persons:
        with open(feat_file, 'wb') as f:
            np.save(f, feats)
    data = {'version': FACE_VERSION, 'mtime': mtime, 'frames': len(frames), 'faces': len(dets), 'persons': out}
    _write_json(info_file, data)
    return {**data, 'feats': feats}


# ─── Ollama ──────────────────────────────────────────────────────────────────

DESCRIBE = (
    "Look at the main person in this picture and describe ONLY the clothing they wear (ignore the face, "
    "body, pose, background and lighting). Answer in JSON: "
    '{"visible": true or false (false when the clothes can\'t be seen, e.g. only a face, or no clothes), '
    '"garments": ["each visible garment with its colour and pattern, e.g. white sailor blouse with navy collar"], '
    '"colors": ["main colours"], "style": "one to three words, e.g. school uniform, swimsuit, office suit", '
    '"name_zh": "2 到 8 個字的繁體中文服裝簡稱，例如：白色水手服", "zh": "一句繁體中文的服裝描述"}')

COMPARE = (
    "This picture shows two photos side by side: LEFT and RIGHT. Is the person wearing the SAME OUTFIT in "
    "both - the same garments with the same colours and patterns? Ignore pose, camera angle, zoom, "
    "lighting, background, hair and the face. A garment that is partly hidden or cropped still counts as "
    "the same. Different colours, a different pattern or a different kind of garment means not the same. "
    'Answer in JSON: {"same": true or false, "confidence": 0-100, "reason": "short"}')


class Ollama:
    def __init__(self, url: str = '', model: str = ''):
        self.url = (url or os.environ.get('OLLAMA_BASE_URL', '') or DEFAULT_OLLAMA).strip().rstrip('/')
        self.model = (model or os.environ.get('OLLAMA_MODEL', '')).strip()
        self.thinking = False

    def _call(self, path: str, body: Optional[dict] = None, timeout: float = 10):
        data = json.dumps(body).encode('utf-8') if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = json.load(e).get('error', '')
            except Exception:
                pass
            raise RuntimeError(f'Ollama 回應錯誤 {e.code}：{detail or e.reason}')
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise RuntimeError(f'無法連線到 Ollama（{self.url}）：{getattr(e, "reason", e)}')

    def models(self) -> List[dict]:
        """Installed models with their capabilities (vision = can look at pictures)."""
        out = []
        for m in self._call('/api/tags').get('models') or []:
            name = m.get('name') or m.get('model')
            try:
                caps = self._call('/api/show', {'model': name}).get('capabilities') or []
            except RuntimeError:
                caps = []
            out.append({'name': name, 'vision': 'vision' in caps, 'thinking': 'thinking' in caps,
                        'size': m.get('size')})
        return out

    def resolve(self) -> str:
        """The vision model to use: OLLAMA_MODEL, else the first installed one that can see pictures."""
        models = self.models()
        if self.model:
            found = next((m for m in models if m['name'] == self.model), None)
            if not found:
                raise RuntimeError(f'Ollama 上沒有模型 {self.model}')
            if not found['vision']:
                raise RuntimeError(f'模型 {self.model} 不能看圖片，請在 Windows 程式選擇有 vision 的模型')
        else:
            vision = [m for m in models if m['vision']]
            if not vision:
                raise RuntimeError('Ollama 上沒有能看圖片（vision）的模型')
            found = vision[0]
            self.model = found['name']
        self.thinking = found['thinking']
        return self.model

    def ask(self, prompt: str, images: List[bytes], timeout: float = 300) -> dict:
        body = {'model': self.model, 'stream': False, 'format': 'json', 'keep_alive': '10m',
                'options': {'temperature': 0},
                'messages': [{'role': 'user', 'content': prompt,
                              'images': [base64.b64encode(i).decode('ascii') for i in images]}]}
        if self.thinking:
            body['think'] = False
        for attempt in range(2):
            text = (self._call('/api/chat', body, timeout=timeout).get('message') or {}).get('content') or ''
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except ValueError:
                pass
        raise RuntimeError('模型回答的格式不正確')


def status() -> dict:
    """For the 辨識 page: face models present, Ollama reachable, which model will be used."""
    out = {'face_models': all(model_path(k, download=False) for k in MODELS)}
    client = Ollama()
    out['ollama'] = {'url': client.url, 'model': client.model}
    try:
        out['ollama']['model'] = client.resolve()
        out['ollama']['ok'] = True
    except RuntimeError as e:
        out['ollama'].update(ok=False, error=str(e))
    return out


# ─── outfit helpers ──────────────────────────────────────────────────────────

_STOP = {'a', 'an', 'the', 'with', 'and', 'of', 'in', 'on', 'to', 'its', 'her', 'his', 'their', 'light', 'dark'}


def _tokens(outfit: dict) -> set:
    words = ' '.join([*(outfit.get('garments') or []), *(outfit.get('colors') or []), outfit.get('style') or ''])
    return {w for w in re.findall(r'[a-z]+', words.lower()) if w not in _STOP and len(w) > 1}


def _hist(path: str):
    import cv2
    try:
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    if image is None:
        return None
    body = image[int(image.shape[0] * 0.2):]          # below the head
    hsv = cv2.cvtColor(body, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 16], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def _side_by_side(a: str, b: str) -> Optional[bytes]:
    import cv2
    images = []
    for path in (a, b):
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        h, w = image.shape[:2]
        images.append(cv2.resize(image, (max(1, round(w * 448 / h)), 448)))
    gap = np.full((448, 16, 3), 255, np.uint8)
    ok, data = cv2.imencode('.jpg', np.hstack([images[0], gap, images[1]]), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return data.tobytes() if ok else None


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


# ─── the queue ───────────────────────────────────────────────────────────────

class Recognizer:
    def __init__(self, library):
        self.library = library
        self._lock = threading.RLock()
        self._jobs: Optional[List[dict]] = None
        self._jobs_base = None
        self._wake = threading.Event()
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._face: Optional[FaceModel] = None
        self._cancel = set()

    # ── storage ──

    def _file(self) -> str:
        folder = os.path.join(self.library.base(), '.tad')
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
            media._hide(folder)
        return os.path.join(folder, 'recognition.json')

    def _load(self) -> List[dict]:
        base = self.library.base()
        if self._jobs is None or self._jobs_base != base:
            data = _read_json(self._file())
            jobs = data.get('jobs') if isinstance(data, dict) else None
            self._jobs = [j for j in jobs or [] if isinstance(j, dict) and j.get('id')]
            self._jobs_base = base
            for job in self._jobs:
                if job.get('status') == 'running':    # stopped mid-way: start again (caches make it quick)
                    job['status'] = 'queued'
        return self._jobs

    def _save(self):
        try:
            _write_json(self._file(), {'version': 1, 'jobs': self._jobs or []})
        except OSError as e:
            logger.warning(f"AI 辨識：無法儲存佇列 {e}")

    # ── API ──

    @staticmethod
    def _summary(job: dict) -> dict:
        out = {k: v for k, v in job.items() if k not in ('result', 'ids')}
        out['count'] = len(job.get('ids') or [])
        result = job.get('result') or {}
        pending = [x for key in ('matches', 'unknown', 'groups') for x in result.get(key) or []
                   if x.get('state') == 'pending']
        out['pending'] = len(pending)
        return out

    def jobs(self) -> List[dict]:
        with self._lock:
            return [self._summary(j) for j in reversed(self._load())]

    def job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = next((j for j in self._load() if j['id'] == job_id), None)
            return json.loads(json.dumps(job)) if job else None

    def add(self, kind: str, ids: List[str]) -> dict:
        if kind not in KINDS:
            raise ValueError('不明的辨識種類')
        with self.library._lock:
            ids = [v for v in dict.fromkeys(str(i) for i in ids) if v in self.library.entries]
            first = self.library.entries[ids[0]]['rel'] if ids else ''
        if not ids:
            raise ValueError('沒有可以辨識的項目')
        job = {'id': uuid.uuid4().hex[:12], 'kind': kind, 'title': KINDS[kind], 'ids': ids,
               'label': os.path.basename(first) + (f' 等 {len(ids)} 個' if len(ids) > 1 else ''),
               'created': time.time(), 'status': 'queued', 'progress': None, 'error': None}
        with self._lock:
            self._load().append(job)
            self._save()
        self.start()
        self._wake.set()
        logger.info(f"AI 辨識：加入佇列 {KINDS[kind]} {len(ids)} 個")
        return self._summary(job)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = next((j for j in self._load() if j['id'] == job_id), None)
            if not job:
                return False
            if job['status'] == 'queued':
                job['status'] = 'cancelled'
                job['finished'] = time.time()
                self._save()
            elif job['status'] == 'running':
                self._cancel.add(job_id)
            return True

    def remove(self, job_id: str) -> bool:
        with self._lock:
            jobs = self._load()
            job = next((j for j in jobs if j['id'] == job_id), None)
            if not job:
                return False
            if job['status'] == 'running':
                self._cancel.add(job_id)
            jobs.remove(job)
            self._save()
            return True

    def apply(self, job_id: str, entries: List[dict]) -> dict:
        """Apply / skip results: [{key, action: 'apply'|'reject', name?, items?: [id]}]."""
        applied, missing = 0, 0
        with self._lock:
            job = next((j for j in self._load() if j['id'] == job_id), None)
            if not job or not job.get('result'):
                raise ValueError('找不到辨識結果')
            result = job['result']
            index = {x['key']: x for key in ('matches', 'unknown', 'groups') for x in result.get(key) or []}
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                target = index.get(entry.get('key'))
                if not target:
                    continue
                if entry.get('action') == 'reject':
                    target['state'] = 'rejected'
                    continue
                if entry.get('action') != 'apply':
                    continue
                if target['key'].startswith('m'):        # suggested actor for one item
                    r = self.library.update_many([target['item']['id']], add_actors=[target['actor']])
                else:
                    name = str(entry.get('name') or '').strip()[:200]
                    if not name:
                        raise ValueError('請輸入名稱')
                    members = [m['item']['id'] for m in target['members']]
                    chosen = entry.get('items')
                    if isinstance(chosen, list):
                        members = [m for m in members if m in set(str(c) for c in chosen)]
                    if not members:
                        raise ValueError('沒有選取任何項目')
                    if target['key'].startswith('u'):
                        r = self.library.update_many(members, add_actors=[name])
                    else:
                        r = self.library.update_many(members, series=name)
                    target['name'] = name
                    target['applied_items'] = members
                target['state'] = 'applied'
                applied += r['updated']
                missing += r['missing']
            self._save()
            return {'job': json.loads(json.dumps(job)), 'updated': applied, 'missing': missing}

    # ── worker ──

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._run, daemon=True, name='ai-recognition')
            self._thread.start()

    def shutdown(self):
        self._stop = True
        self._wake.set()

    def _run(self):
        while not self._stop:
            with self._lock:
                job = next((j for j in self._load() if j['status'] == 'queued'), None)
                if job:
                    job.update(status='running', started=time.time(), error=None,
                               progress={'phase': '準備中', 'done': 0, 'total': 0})
                    self._save()
            if not job:
                self._wake.wait(10)
                self._wake.clear()
                continue
            logger.info(f"AI 辨識：開始 {job['title']}（{len(job['ids'])} 個）")
            try:
                result = self._actor_job(job) if job['kind'] == 'actor' else self._series_job(job)
                status, error = 'done', None
            except Cancelled:
                if self._stop and job['id'] not in self._cancel:
                    # the server is stopping: leave the file saying "running", the next start runs it again
                    logger.info(f"AI 辨識：{job['title']} 暫停，下次啟動時繼續")
                    return
                result, status, error = None, 'cancelled', None
            except Exception as e:
                logger.warning(f"AI 辨識失敗: {e}", exc_info=not isinstance(e, RuntimeError))
                result, status, error = None, 'failed', str(e)
            with self._lock:
                self._cancel.discard(job['id'])
                job.update(status=status, error=error, finished=time.time(), progress=None)
                if result is not None:
                    job['result'] = result
                if any(j is job for j in self._jobs or []):
                    self._save()
            logger.info(f"AI 辨識：{job['title']} {status}")

    def _step(self, job: dict, phase: str, done: int, total: int):
        if self._stop or job['id'] in self._cancel:
            raise Cancelled()
        job['progress'] = {'phase': phase, 'done': done, 'total': total}

    def _face_model(self) -> FaceModel:
        if self._face is None:
            self._face = FaceModel()
        return self._face

    # ── items ──

    def _items(self, ids: Optional[List[str]] = None) -> List[dict]:
        lib = self.library
        with lib._lock:
            pairs = [(v, lib.entries.get(v)) for v in ids] if ids is not None else list(lib.entries.items())
            out = []
            for vid, e in pairs:
                if not e:
                    continue
                meta = e['meta']
                out.append({'id': vid, 'path': e['path'], 'rel': e['rel'], 'kind': e['kind'],
                            'actors': list(meta.get('actors') or []), 'series': meta.get('series') or '',
                            'group': meta.get('group') or '', 'ready': bool(meta.get('info')),
                            'duration': (meta.get('info') or {}).get('duration') or 0,
                            'cover': f"{MEDIA_URL}/{vid}/shots/{meta['shots'][0]}" if meta.get('shots') else None})
            return out

    @staticmethod
    def _ref(item: dict) -> dict:
        return {'id': item['id'], 'name': os.path.basename(item['rel']), 'folder': os.path.dirname(item['rel']),
                'kind': item['kind'], 'cover': item['cover'], 'actors': item['actors'], 'series': item['series']}

    @staticmethod
    def _img(item: dict, name: Optional[str]) -> Optional[str]:
        return f"{MEDIA_URL}/{item['id']}/ai/{name}" if name else None

    def _analyze(self, item: dict) -> Tuple[Optional[dict], Optional[str]]:
        """(analysis, None) or (None, reason it can't be used)."""
        if item['kind'] == 'video' and not item['ready']:
            return None, '影片資訊還沒產生完成'
        try:
            data = analyze(item['path'], item['kind'], item['duration'], self._face_model)
        except Exception as e:
            if isinstance(e, RuntimeError) and '模型' in str(e):
                raise
            return None, f'無法分析：{e}'
        if not data['persons']:
            return None, '找不到清楚的人臉'
        return data, None

    def _analyze_targets(self, job: dict):
        targets = self._items(job['ids'])
        found, skipped = [], []
        for i, item in enumerate(targets):
            self._step(job, '分析人臉', i, len(targets))
            data, reason = self._analyze(item)
            if data:
                found.append((item, data))
            else:
                skipped.append({'item': self._ref(item), 'reason': reason})
        gone = len(job['ids']) - len(targets)
        if gone:
            skipped.append({'item': None, 'reason': f'{gone} 個項目已不在媒體庫（被移動或刪除）'})
        return found, skipped

    # ── 主演 references ──

    def _actor_refs(self, job: dict, done: Dict[str, dict]):
        """Faces of every item tagged with 主演: {actor lower: {'name', 'feats', 'items', 'groups'}} and,
        per item, which person is which of its actors ({id: {person index: actor}})."""
        tagged = [it for it in self._items() if it['actors']]
        analysed = []
        for i, item in enumerate(tagged):
            self._step(job, '建立主演參考', i, len(tagged))
            data = done.get(item['id'])
            if data is None:
                data, _ = self._analyze(item)
            if data:
                analysed.append((item, data))
        refs, own = {}, {}

        def add(actor, item, feat):
            r = refs.setdefault(actor.lower(), {'name': actor, 'feats': [], 'items': [], 'groups': []})
            r['feats'].append(feat)
            r['items'].append(item['id'])
            r['groups'].append(item['group'])
            r.pop('matrix', None)

        multi = []
        for item, data in analysed:
            if len(item['actors']) == 1:
                add(item['actors'][0], item, data['feats'][0])
                own[item['id']] = {0: item['actors'][0]}
            else:
                multi.append((item, data))
        for item, data in multi:                 # several actors: tell them apart by the references
            left, assigned = list(item['actors']), {}
            for pi in range(len(data['persons'])):
                best = self._best(refs, data['feats'][pi], item, among=left)
                if best and best[1] >= FACE_MATCH:
                    assigned[pi] = best[0]
                    left = [a for a in left if a.lower() != best[0].lower()]
            rest = [pi for pi in range(len(data['persons'])) if pi not in assigned]
            if len(left) == 1 and len(rest) == 1:
                assigned[rest[0]] = left[0]
            own[item['id']] = assigned
            for pi, actor in assigned.items():
                add(actor, item, data['feats'][pi])
        return refs, own, analysed

    @staticmethod
    def _best(refs: dict, feat, item: dict, among=None) -> Optional[tuple]:
        """(actor name, score) of the closest actor; the item's own faces and its other versions don't count."""
        wanted = {a.lower() for a in among} if among is not None else None
        best = None
        for key, r in refs.items():
            if wanted is not None and key not in wanted:
                continue
            if 'matrix' not in r:
                r['matrix'] = np.stack(r['feats'])
            keep = [i for i, (vid, g) in enumerate(zip(r['items'], r['groups']))
                    if vid != item['id'] and not (g and g == item['group'])]
            if not keep:
                continue
            sims = np.sort(r['matrix'][keep] @ feat)[::-1]
            score = float(sims[:3].mean())
            if best is None or score > best[1]:
                best = (r['name'], score)
        return best

    @staticmethod
    def _cluster(feats: List[np.ndarray]) -> List[int]:
        """Greedy grouping of faces from different items; returns a cluster number per face."""
        centers, labels = [], []
        for f in feats:
            sims = [float(np.dot(c / (np.linalg.norm(c) or 1), f)) for c in centers]
            best = int(np.argmax(sims)) if sims else -1
            if best >= 0 and sims[best] >= FACE_CLUSTER:
                centers[best] = centers[best] + f
                labels.append(best)
            else:
                centers.append(f.copy())
                labels.append(len(centers) - 1)
        return labels

    # ── 辨識主演 ──

    def _actor_job(self, job: dict) -> dict:
        found, skipped = self._analyze_targets(job)
        refs, own, _ = self._actor_refs(job, {item['id']: data for item, data in found})
        self._step(job, '比對人臉', 0, 1)
        matches, strangers, already = {}, [], 0
        for item, data in found:
            known = own.get(item['id'], {})
            tagged = {a.lower() for a in item['actors']}
            for pi, person in enumerate(data['persons']):
                if pi in known:
                    already += 1
                    continue
                best = self._best(refs, data['feats'][pi], item)
                if best and best[1] >= FACE_MATCH:
                    if best[0].lower() in tagged:
                        already += 1
                        continue
                    key = (item['id'], best[0].lower())
                    if key not in matches or matches[key]['score'] < round(best[1] * 100):
                        matches[key] = {'item': self._ref(item), 'face': self._img(item, person['face']),
                                        'actor': best[0], 'score': round(best[1] * 100), 'state': 'pending'}
                else:
                    strangers.append((item, person, data['feats'][pi], best))
        matches = sorted(matches.values(), key=lambda m: -m['score'])
        for n, m in enumerate(matches):
            m['key'] = f'm{n}'

        labels = self._cluster([s[2] for s in strangers])
        clusters = {}
        for (item, person, feat, best), label in zip(strangers, labels):
            c = clusters.setdefault(label, {'members': [], 'hints': Counter()})
            c['members'].append({'item': self._ref(item), 'face': self._img(item, person['face'])})
            if best and best[1] >= HINT_MIN:
                c['hints'][best[0]] = max(c['hints'][best[0]], round(best[1] * 100))
        unknown = []
        for c in sorted(clusters.values(), key=lambda c: -len(c['members'])):
            hint = c['hints'].most_common(1)
            unknown.append({'key': f'u{len(unknown)}', 'members': c['members'], 'state': 'pending', 'name': '',
                            'hint': {'actor': hint[0][0], 'score': hint[0][1]} if hint else None})
        return {'matches': matches, 'unknown': unknown, 'skipped': skipped, 'already': already,
                'actors': len(refs), 'threshold': round(FACE_MATCH * 100)}

    # ── 辨識系列 ──

    def _series_job(self, job: dict) -> dict:
        client = Ollama()
        model = client.resolve()                 # fail early when Ollama isn't reachable
        found, skipped = self._analyze_targets(job)
        done = {item['id']: data for item, data in found}
        refs, own, analysed = self._actor_refs(job, done)
        self._step(job, '判斷人物', 0, 1)

        # who is the main person of each target: its single 主演, a face match, or an unknown person
        people, unnamed = {}, []
        for item, data in found:
            actor = own.get(item['id'], {}).get(0)
            if not actor:
                best = self._best(refs, data['feats'][0], item)
                actor = best[0] if best and best[1] >= FACE_MATCH else None
            if actor:
                p = people.setdefault(actor.lower(), {'name': actor, 'actor': actor, 'members': []})
                p['members'].append((item, data, 0))
            else:
                unnamed.append((item, data))
        for (item, data), label in zip(unnamed, self._cluster([d['feats'][0] for _, d in unnamed])):
            p = people.setdefault(f'#{label}', {'name': f'人物 {label + 1}', 'actor': None, 'members': []})
            p['members'].append((item, data, 0))

        # items of the same actor that already have a 系列: the reference for existing series names
        targets = set(job['ids'])
        for p in people.values():
            p['refs'] = []
            if not p['actor']:
                continue
            per_series = {}
            for item, data in analysed:
                if item['id'] in targets or not item['series']:
                    continue
                person = next((pi for pi, a in own.get(item['id'], {}).items() if a.lower() == p['actor'].lower()), None)
                if person is None:
                    continue
                per_series.setdefault(item['series'], []).append((item, data, person))
            for series, items in per_series.items():
                p['refs'].extend(items[:SERIES_REFS])

        # describe the outfit of every person in play
        everyone = [(p, m, False) for p in people.values() for m in p['members']] + \
                   [(p, m, True) for p in people.values() for m in p['refs']]
        outfits = {}
        for i, (p, (item, data, pi), is_ref) in enumerate(everyone):
            self._step(job, '描述服裝', i, len(everyone))
            outfits[(item['id'], pi)] = self._outfit(client, model, item, data, pi)

        # compare outfits of the same person
        checks, groups, loose = [], [], []
        verified = 0
        for p in people.values():
            members = [(m, False) for m in p['members']] + [(m, True) for m in p['refs']]
            usable = []
            for m, is_ref in members:
                o = outfits.get((m[0]['id'], m[2])) or {}
                if o.get('visible'):
                    usable.append((m, is_ref))
                elif not is_ref:
                    skipped.append({'item': self._ref(m[0]), 'reason': o.get('error') or '看不到服裝'})
            pairs = self._candidate_pairs(usable, outfits)
            checks.append((p, usable, pairs))
        total = sum(len(c[2]) for c in checks)
        for p, usable, pairs in checks:
            union = _Union()
            for i in range(len(usable)):
                union.find(i)
            by_series = {}
            for i, (m, is_ref) in enumerate(usable):      # references of one series belong together
                if is_ref:
                    by_series.setdefault(m[0]['series'], []).append(i)
            for idx in by_series.values():
                for j in idx[1:]:
                    union.join(idx[0], j)
            scores = {}
            for i, j in pairs:
                self._step(job, '比對服裝', verified, total)
                verified += 1
                if verified > VERIFY_LIMIT:
                    break
                if union.find(i) == union.find(j) and usable[i][1] and usable[j][1]:
                    continue
                same, confidence = self._same_outfit(client, usable[i][0], usable[j][0])
                if same and confidence >= OUTFIT_SAME:
                    union.join(i, j)
                    scores[(i, j)] = confidence
            comps = {}
            for i in range(len(usable)):
                comps.setdefault(union.find(i), []).append(i)
            for comp in comps.values():
                members = [usable[i][0] for i in comp if not usable[i][1]]
                refs_in = [usable[i][0] for i in comp if usable[i][1]]
                if not members:
                    continue
                if len(members) == 1 and not refs_in:
                    item, data, pi = members[0]
                    o = outfits[(item['id'], pi)]
                    loose.append({'item': self._ref(item), 'body': self._img(item, data['persons'][pi]['body']),
                                  'person': p['name'], 'outfit': o.get('zh') or '',
                                  'reason': '沒有找到同一人穿同一套衣服的其他項目'})
                    continue
                existing = Counter(m[0]['series'] for m in refs_in).most_common(1)
                first = outfits[(members[0][0]['id'], members[0][2])]
                short = (first.get('name_zh') or first.get('style') or '').strip()
                suggested = existing[0][0] if existing else (f"{p['actor']} {short}".strip() if p['actor'] else short)
                pair_scores = [s for (i, j), s in scores.items() if i in comp and j in comp]
                groups.append({
                    'person': p['name'], 'actor': p['actor'],
                    'face': self._img(members[0][0], members[0][1]['persons'][members[0][2]]['face']),
                    'outfit': first.get('zh') or '', 'suggested': suggested[:200], 'existing': bool(existing),
                    'confidence': min(pair_scores) if pair_scores else None,
                    'members': [{'item': self._ref(it), 'body': self._img(it, d['persons'][pi]['body']),
                                 'outfit': outfits[(it['id'], pi)].get('zh') or ''} for it, d, pi in members],
                    'refs': [{'item': self._ref(it), 'body': self._img(it, d['persons'][pi]['body'])}
                             for it, d, pi in refs_in],
                    'state': 'pending', 'name': ''})
        groups.sort(key=lambda g: (not g['existing'], -len(g['members'])))
        for n, g in enumerate(groups):
            g['key'] = f'g{n}'
        return {'groups': groups, 'loose': loose, 'skipped': skipped, 'model': model,
                'checked': min(verified, VERIFY_LIMIT), 'limited': verified > VERIFY_LIMIT}

    def _outfit(self, client: Ollama, model: str, item: dict, data: dict, pi: int) -> dict:
        person = data['persons'][pi]
        if not person.get('body'):
            return {'visible': False, 'error': '畫面裡看不到身體'}
        folder = media.shots_dir(item['path'])
        cache_file = os.path.join(folder, f'outfit_{pi + 1}.json')
        mtime = os.path.getmtime(item['path'])
        cached = _read_json(cache_file)
        if isinstance(cached, dict) and cached.get('model') == model and cached.get('mtime') == mtime:
            return cached['data']
        try:
            with open(os.path.join(folder, person['body']), 'rb') as f:
                answer = client.ask(DESCRIBE, [f.read()])
        except (OSError, RuntimeError) as e:
            if isinstance(e, RuntimeError) and '連線' in str(e):
                raise
            return {'visible': False, 'error': f'服裝描述失敗：{e}'}
        visible = answer.get('visible')
        data_out = {'visible': visible is not False and str(visible).lower() != 'false' and bool(answer.get('garments')),
                    'garments': [str(g) for g in answer.get('garments') or []][:12],
                    'colors': [str(c) for c in answer.get('colors') or []][:8],
                    'style': str(answer.get('style') or '')[:60], 'name_zh': str(answer.get('name_zh') or '')[:30],
                    'zh': str(answer.get('zh') or '')[:200]}
        try:
            _write_json(cache_file, {'model': model, 'mtime': mtime, 'data': data_out})
        except OSError:
            pass
        return data_out

    def _candidate_pairs(self, usable: list, outfits: dict) -> List[tuple]:
        """Pairs worth showing to the model: all of them for a few items, else each item's closest."""
        n = len(usable)
        if n < 2:
            return []
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n) if not (usable[i][1] and usable[j][1])]
        if n <= ALL_PAIRS_UP_TO:
            return pairs
        toks, hists = [], []
        for (item, data, pi), _ in usable:
            toks.append(_tokens(outfits[(item['id'], pi)]))
            hists.append(_hist(os.path.join(media.shots_dir(item['path']), data['persons'][pi]['body'])))

        def score(i, j):
            union = toks[i] | toks[j]
            text = len(toks[i] & toks[j]) / len(union) if union else 0
            color = 0.0
            if hists[i] is not None and hists[j] is not None:
                import cv2
                color = max(0.0, float(cv2.compareHist(hists[i], hists[j], cv2.HISTCMP_CORREL)))
            return 0.5 * text + 0.5 * color

        scored = {(i, j): score(i, j) for i, j in pairs}
        keep = set()
        for i in range(n):
            mine = sorted(((s, p) for p, s in scored.items() if i in p), reverse=True)[:NEIGHBORS]
            keep.update(p for _, p in mine)
        return sorted(keep, key=lambda p: -scored[p])

    def _same_outfit(self, client: Ollama, a: tuple, b: tuple) -> Tuple[bool, int]:
        paths = [os.path.join(media.shots_dir(it['path']), d['persons'][pi]['body']) for it, d, pi in (a, b)]
        image = _side_by_side(*paths)
        if image is None:
            return False, 0
        try:
            answer = client.ask(COMPARE, [image])
        except RuntimeError as e:
            if '連線' in str(e):
                raise
            return False, 0
        same = answer.get('same')
        same = same is True or str(same).lower() == 'true'
        try:
            confidence = int(float(answer.get('confidence') or 0))
        except (TypeError, ValueError):
            confidence = 0
        return same, max(0, min(100, confidence))
