"""Pure measurement logic shared by the UI and OBS output."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import math
from typing import Deque

@dataclass(frozen=True)
class Sample:
    x: float
    y: float
    timestamp: float

@dataclass
class Measurement:
    current_speed: float = 0.0
    average_speed: float = 0.0
    max_speed: float = 0.0
    max_session_speed: float = 0.0
    map_distance: float = 0.0
    session_distance: float = 0.0
    x: float = 0.0
    y: float = 0.0
    unit: str = "px/s"

class Metrics:
    """Distance/speed engine. Coordinates and distance share their native unit."""
    def __init__(self, noise_threshold: float = 0.0, smoothing: float = 0.25, max_jump: float = 10000.0, average_window: float = 2.0):
        self.noise_threshold = max(0.0, noise_threshold)
        self.smoothing = min(1.0, max(0.0, smoothing))
        self.max_jump = max_jump
        self.average_window = max(0.1, average_window)
        self.previous: Sample | None = None
        self.samples: Deque[tuple[float, float]] = deque()
        self.measurement = Measurement()
        self._smooth = 0.0

    def add(self, x: float, y: float, timestamp: float, unit: str = "px/s") -> Measurement:
        if not all(map(math.isfinite, (x, y, timestamp))):
            return self.measurement
        m = self.measurement
        m.x, m.y, m.unit = x, y, unit
        speed = 0.0
        p = self.previous
        if p is not None:
            dt = timestamp - p.timestamp
            distance = math.hypot(x - p.x, y - p.y)
            if dt > 0 and distance <= self.max_jump:
                if distance >= self.noise_threshold:
                    speed = distance / dt
                    m.map_distance += distance
                    m.session_distance += distance
                else:
                    # Ignore jitter without moving the anchor, so it cannot accumulate into motion.
                    return m
            elif dt <= 0 or distance > self.max_jump:
                # Re-anchor after invalid timing/discontinuity; never emit a false spike.
                self.previous = Sample(x, y, timestamp)
                return m
        self.previous = Sample(x, y, timestamp)
        self._smooth = self.smoothing * speed + (1-self.smoothing) * self._smooth
        m.current_speed = self._smooth
        m.max_speed = max(m.max_speed, speed)
        m.max_session_speed = max(m.max_session_speed, speed)
        self.samples.append((timestamp, speed))
        while self.samples and (timestamp - self.samples[0][0] > self.average_window or len(self.samples) > 2000):
            self.samples.popleft()
        m.average_speed = sum(v for _, v in self.samples) / len(self.samples) if self.samples else 0.0
        return m

    def reset_map(self):
        self.measurement.map_distance = 0.0
        self.measurement.max_speed = 0.0
        self.samples.clear()
        self._smooth = 0.0

    def reset_session(self):
        self.measurement.session_distance = 0.0
        self.measurement.max_session_speed = 0.0

    def reset_max_speed(self):
        self.measurement.max_speed = 0.0
        self.measurement.max_session_speed = 0.0

    def reset_all(self):
        self.reset_map()
        self.reset_session()
        self.measurement.current_speed = self.measurement.average_speed = 0.0
        self.previous = None


def physical_size(diagonal: float, aspect_ratio: float) -> tuple[float, float]:
    if not math.isfinite(diagonal) or not math.isfinite(aspect_ratio) or diagonal <= 0 or aspect_ratio <= 0:
        raise ValueError("Diagonal and aspect ratio must be positive finite values")
    return diagonal * aspect_ratio / math.sqrt(aspect_ratio**2 + 1), diagonal / math.sqrt(aspect_ratio**2 + 1)


def screen_to_physical(x: float, y: float, screen_width_px: float, screen_height_px: float, active_width_cm: float, active_height_cm: float) -> tuple[float, float]:
    """Scale mapped cursor coordinates into user-calibrated active-area centimeters."""
    values=(x,y,screen_width_px,screen_height_px,active_width_cm,active_height_cm)
    if not all(math.isfinite(v) for v in values) or screen_width_px <= 0 or screen_height_px <= 0 or active_width_cm <= 0 or active_height_cm <= 0:
        raise ValueError("Screen and active-area dimensions must be positive finite values")
    return x * active_width_cm / screen_width_px, y * active_height_cm / screen_height_px


def convert_distance(value: float, from_unit: str, to_unit: str) -> float:
    factors = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "km": 1_000_000.0}
    if from_unit not in factors or to_unit not in factors:
        raise ValueError("Unsupported physical distance unit")
    return value * factors[from_unit] / factors[to_unit]
