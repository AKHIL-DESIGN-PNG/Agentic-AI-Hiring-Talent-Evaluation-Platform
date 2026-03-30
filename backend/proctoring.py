from __future__ import annotations

import base64
import contextlib
import io
import importlib.util
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

project_root = Path(__file__).resolve().parent.parent
project_detection_root = Path(os.getenv("DETECTION_ROOT", str(project_root / "detection")))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(__file__).resolve().parent / ".ultralytics"))

if importlib.util.find_spec("google.protobuf.descriptor") is None:
    create_face_landmarker = None
    _import_error = ModuleNotFoundError("google.protobuf.descriptor is unavailable")
else:
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from detection.src.main import create_face_landmarker
    except Exception as exc:  # pragma: no cover
        create_face_landmarker = None
        _import_error = exc
    else:
        _import_error = None


@dataclass
class CandidateSignalState:
    last_face_time: float = 0.0
    face_streak: int = 0
    missing_face_streak: int = 0
    gadget_streak: int = 0


class ProctoringEngine:
    def __init__(self) -> None:
        self._init_lock = threading.Lock()
        self._lock = threading.Lock()
        self._ready = False
        self._error: Optional[str] = None
        self._face_backend: str = "none"
        self._phone_error: Optional[str] = None
        self._face_detect = None
        self._face_close = None
        self._phone_model = None
        self._phone_names: Dict[int, str] = {}
        self._phone_class_id: Optional[int] = None
        self._candidate_state: Dict[str, CandidateSignalState] = {}
        self._call_count = 0
        self._last_gadget = False
        self._missing_duration = float(os.getenv("PROCTOR_MISSING_DURATION", "5.0"))
        self._face_hold_seconds = float(os.getenv("PROCTOR_FACE_HOLD_SECONDS", "2.4"))
        self._face_confirm = int(os.getenv("PROCTOR_FACE_CONFIRM", os.getenv("PROCTOR_SINGLE_FACE_CONFIRM", "2")))
        self._missing_face_confirm = int(os.getenv("PROCTOR_MISSING_FACE_CONFIRM", "2"))
        self._gadget_confirm = int(os.getenv("PROCTOR_GADGET_CONFIRM", "2"))
        self._phone_interval = int(os.getenv("PROCTOR_PHONE_INTERVAL", "2"))
        self._phone_imgsz = int(os.getenv("PROCTOR_PHONE_IMGSZ", "640"))
        self._phone_conf = float(os.getenv("PROCTOR_PHONE_CONF", "0.20"))
        raw_model_path = os.getenv("PROCTOR_PHONE_MODEL", "detection/yolov8n.pt")
        candidate_paths = [
            Path(raw_model_path),
            Path.cwd() / raw_model_path,
            project_root / raw_model_path,
            project_root / "detection" / "yolov8n.pt",
            project_detection_root / "yolov8n.pt",
        ]
        resolved = next((p for p in candidate_paths if p.exists()), None)
        self._phone_model_path = str(resolved if resolved else raw_model_path)

    def _ensure_ready(self) -> None:
        if self._ready or self._error:
            return
        with self._init_lock:
            if self._ready or self._error:
                return
            try:
                if create_face_landmarker is not None:
                    self._face_detect, self._face_close = create_face_landmarker(lite=False)
                    self._face_backend = "mediapipe"
                else:
                    self._face_detect, self._face_close = self._create_opencv_face_detector()
                    self._face_backend = "opencv"
                self._load_phone_model()
                self._ready = True
            except Exception as exc:
                try:
                    self._face_detect, self._face_close = self._create_opencv_face_detector()
                    self._face_backend = "opencv"
                    self._load_phone_model()
                    self._ready = True
                    self._error = None
                    print(f"[proctoring] mediapipe_unavailable_fallback_opencv: {exc}")
                except Exception as fallback_exc:
                    self._error = f"proctoring_init_error: {fallback_exc}"

    def public_status(self) -> dict:
        self._ensure_ready()
        if self._ready:
            return {"status": "ready", "face_backend": self._face_backend}
        if self._error:
            return {"status": "unavailable"}
        return {"status": "initializing"}

    @staticmethod
    def _create_opencv_face_detector():
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        classifier = cv2.CascadeClassifier(str(cascade_path))
        if classifier.empty():
            raise RuntimeError("OpenCV face cascade is unavailable")

        def detect(frame_rgb):
            gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
            faces = classifier.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(70, 70),
            )
            return list(faces) if len(faces) else []

        def close():
            return None

        return detect, close

    def _load_phone_model(self) -> None:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                from ultralytics import YOLO  # type: ignore
                model = YOLO(self._phone_model_path)
            names = model.names
            class_id = None
            for key, value in names.items():
                if value.lower() in ("cell phone", "phone", "mobile", "mobile phone"):
                    class_id = key
                    break
            if class_id is None and 67 in names:
                class_id = 67
            self._phone_model = model
            self._phone_names = names
            self._phone_class_id = class_id
            self._phone_error = None
        except Exception as exc:
            self._phone_model = None
            self._phone_names = {}
            self._phone_class_id = None
            self._phone_error = f"phone_model_error: {exc}"

    @staticmethod
    def _decode_image(data_url: str) -> np.ndarray:
        if "," in data_url:
            _, data = data_url.split(",", 1)
        else:
            data = data_url
        raw = base64.b64decode(data)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid image payload")
        return img

    @staticmethod
    def _normalize_frame(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest <= 960:
            return img
        scale = 960.0 / float(longest)
        return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _enhance_frame(img: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        v = cv2.equalizeHist(v)
        enhanced = cv2.merge((h, s, v))
        return cv2.cvtColor(enhanced, cv2.COLOR_HSV2BGR)

    def _detect_faces_advanced(self, img: np.ndarray) -> list:
        variants = [img]
        enhanced = self._enhance_frame(img)
        variants.append(enhanced)
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest < 960:
            scale = 960 / float(longest)
            variants.append(cv2.resize(enhanced, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC))

        best_faces = []
        for variant in variants:
            rgb = cv2.cvtColor(variant, cv2.COLOR_BGR2RGB)
            faces = self._face_detect(rgb) or []
            if len(faces) > len(best_faces):
                best_faces = faces
            if len(best_faces) > 0:
                break
        return best_faces

    @staticmethod
    def _heuristic_phone_detector(img: np.ndarray) -> bool:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 140)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = img.shape[:2]
        min_area = 0.008 * h * w
        max_area = 0.22 * h * w
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) < 4 or len(approx) > 10:
                continue
            x, y, bw, bh = cv2.boundingRect(approx)
            aspect = bw / float(max(bh, 1))
            if 0.38 <= aspect <= 2.6:
                return True
        return False

    def analyze(self, image_data: str, candidate_id: str) -> dict:
        self._ensure_ready()
        if self._error:
            print(f"[proctoring] init_unavailable: {self._error}")
            return {
                "status": "unavailable",
                "blocked": True,
                "face_detected": False,
                "gadget_detected": False,
                "faces": 0,
                "multiple_faces": False,
                "mobile": False,
                "message": "Security monitoring is unavailable.",
            }
        if not self._ready:
            return {
                "status": "initializing",
                "blocked": True,
                "face_detected": False,
                "gadget_detected": False,
                "faces": 0,
                "multiple_faces": False,
                "mobile": False,
                "message": "Security monitoring is starting.",
            }

        img = self._normalize_frame(self._decode_image(image_data))
        now = time.time()

        with self._lock:
            signal = self._candidate_state.setdefault(candidate_id, CandidateSignalState(last_face_time=now))
            face_landmark_sets = self._detect_faces_advanced(img)
            face_count = len(face_landmark_sets)
            has_face = face_count > 0
            gadget_detected = False
            self._call_count += 1
            should_run_phone = (
                self._phone_model is not None
                and self._phone_interval > 0
                and self._call_count % self._phone_interval == 0
            )
            if should_run_phone:
                enhanced_phone_frame = self._enhance_frame(img)
                results = self._phone_model(
                    enhanced_phone_frame,
                    imgsz=self._phone_imgsz,
                    conf=self._phone_conf,
                    verbose=False,
                )
                for result in results:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        name = self._phone_names.get(class_id, "").lower()
                        name_match = name in ("cell phone", "mobile", "mobile phone", "phone")
                        id_match = self._phone_class_id is not None and class_id == self._phone_class_id
                        if name_match or id_match:
                            gadget_detected = True
                            break
                    if gadget_detected:
                        break
                # Heuristic fallback can create false positives.
                # Use it only when the model is unavailable.
                self._last_gadget = gadget_detected
            elif self._phone_model is not None:
                gadget_detected = self._last_gadget
            else:
                gadget_detected = self._heuristic_phone_detector(img)

            if has_face:
                signal.last_face_time = now
                signal.face_streak += 1
                signal.missing_face_streak = 0
            else:
                signal.face_streak = 0
                signal.missing_face_streak += 1

            if gadget_detected:
                signal.gadget_streak += 1
            else:
                signal.gadget_streak = 0

            confirmed_face = signal.face_streak >= self._face_confirm
            confirmed_missing_face = (
                not has_face
                and signal.missing_face_streak >= self._missing_face_confirm
                and (now - signal.last_face_time >= self._missing_duration)
            )
            confirmed_gadget = signal.gadget_streak >= self._gadget_confirm
            face_recently_seen = (now - signal.last_face_time) <= self._face_hold_seconds

        blocked = confirmed_gadget or confirmed_missing_face
        multiple_faces = face_count > 1
        if confirmed_gadget:
            status = "gadget_detected"
        elif confirmed_missing_face:
            status = "no_face"
        elif multiple_faces:
            status = "multiple_faces"
        elif confirmed_face or face_recently_seen:
            status = "face_detected"
        else:
            status = "initializing"

        payload = {
            "status": status,
            "blocked": blocked,
            "face_detected": (confirmed_face or face_recently_seen) and not blocked,
            "gadget_detected": confirmed_gadget,
            "faces": int(face_count),
            "multiple_faces": bool(multiple_faces),
            "mobile": bool(confirmed_gadget),
        }
        if self._phone_error:
            print(f"[proctoring] phone_warning: {self._phone_error}")
        return payload


_ENGINE: Optional[ProctoringEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> ProctoringEngine:
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = ProctoringEngine()
    return _ENGINE


def check_proctoring_frame(image: str, candidate_id: Optional[str] = None) -> dict:
    engine = get_engine()
    safe_id = candidate_id or "anonymous"
    try:
        return engine.analyze(image, safe_id)
    except Exception as exc:
        print(f"[proctoring] runtime_error: {exc.__class__.__name__}: {exc}")
        return {
            "status": "error",
            "blocked": True,
            "face_detected": False,
            "gadget_detected": False,
            "faces": 0,
            "multiple_faces": False,
            "mobile": False,
            "message": "Security monitoring is unavailable.",
        }
