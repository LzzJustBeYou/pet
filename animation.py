from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple

from PyQt5.QtCore import QObject, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QImageReader, QPainter, QPixmap, QRegion

from pet_package import CELL_HEIGHT, CELL_WIDTH, PetPackage


@dataclass(frozen=True)
class AnimationSpec:
    row: int
    durations_ms: Tuple[int, ...]


ANIMATION_SPECS: Dict[str, AnimationSpec] = {
    "idle": AnimationSpec(0, (280, 110, 110, 140, 140, 320)),
    "running-right": AnimationSpec(1, (120, 120, 120, 120, 120, 120, 120, 220)),
    "running-left": AnimationSpec(2, (120, 120, 120, 120, 120, 120, 120, 220)),
    "waving": AnimationSpec(3, (140, 140, 140, 280)),
    "jumping": AnimationSpec(4, (140, 140, 140, 140, 280)),
    "failed": AnimationSpec(5, (140, 140, 140, 140, 140, 140, 140, 240)),
    "waiting": AnimationSpec(6, (150, 150, 150, 150, 150, 260)),
    "running": AnimationSpec(7, (120, 120, 120, 120, 120, 220)),
    "review": AnimationSpec(8, (150, 150, 150, 150, 150, 280)),
}


def scaled_canvas_size(source_size: QSize, display_height: int) -> QSize:
    width = max(1, round(display_height * source_size.width() / source_size.height()))
    return QSize(width, display_height)


def _blank_union(size: QSize) -> QImage:
    image = QImage(size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    return image


def _union_images(images: Iterable[QImage], size: QSize) -> QImage:
    union = _blank_union(size)
    painter = QPainter(union)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    for image in images:
        painter.drawImage(0, 0, image)
    painter.end()
    return union


def _region_from_union(union: QImage, target_size: QSize, padding: int) -> QRegion:
    scaled = union.scaled(
        target_size,
        Qt.IgnoreAspectRatio,
        Qt.SmoothTransformation,
    )
    pixmap = QPixmap.fromImage(scaled)
    if pixmap.isNull():
        return QRegion()
    alpha_mask = pixmap.mask()
    if alpha_mask.isNull():
        region = QRegion(QRect(0, 0, target_size.width(), target_size.height()))
    else:
        region = QRegion(alpha_mask)
    if padding > 0 and not region.isEmpty():
        expanded = QRegion(region)
        for dx in range(-padding, padding + 1):
            for dy in range(-padding, padding + 1):
                if dx * dx + dy * dy <= padding * padding:
                    expanded |= region.translated(dx, dy)
        region = expanded
    return region.intersected(QRegion(QRect(0, 0, target_size.width(), target_size.height())))


class SpriteAtlasPlayer(QObject):
    frame_changed = pyqtSignal(QPixmap)
    animation_finished = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance_frame)
        self._package: Optional[PetPackage] = None
        self._atlas = QImage()
        self._display_height = 100
        self._frame_cache: Dict[Tuple[str, int, int], QPixmap] = {}
        self._region_cache: Dict[int, Tuple[QRegion, QRegion]] = {}
        self._window_union = QImage()
        self._interaction_union = QImage()
        self._state: Optional[str] = None
        self._frame_index = 0
        self._loop = True

    @property
    def package(self) -> Optional[PetPackage]:
        return self._package

    @property
    def state(self) -> Optional[str]:
        return self._state

    @property
    def display_size(self) -> QSize:
        return QSize(
            max(1, round(self._display_height * CELL_WIDTH / CELL_HEIGHT)),
            self._display_height,
        )

    def load(self, package: PetPackage, display_height: int) -> None:
        atlas = QImage(str(package.sprite_path))
        if atlas.isNull():
            raise ValueError(f"cannot load spritesheet: {package.sprite_path}")
        self.clear()
        self._package = package
        self._atlas = atlas.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self._display_height = display_height
        self._build_union_images()

    def clear(self) -> None:
        self._timer.stop()
        self._package = None
        self._atlas = QImage()
        self._window_union = QImage()
        self._interaction_union = QImage()
        self._frame_cache.clear()
        self._region_cache.clear()
        self._state = None
        self._frame_index = 0

    def set_display_height(self, display_height: int) -> None:
        if display_height == self._display_height:
            return
        self._display_height = display_height
        self._frame_cache.clear()
        self._region_cache.clear()
        if self._state is not None:
            self._show_current_frame()

    def play(self, state: str, loop: bool) -> None:
        if self._package is None:
            return
        if state not in ANIMATION_SPECS:
            raise KeyError(f"unknown animation state: {state}")
        self._timer.stop()
        self._state = state
        self._loop = loop
        self._frame_index = 0
        self._show_current_frame()
        self._schedule_current_frame()

    def mask_regions(self, padding: int = 2) -> Tuple[QRegion, QRegion]:
        if self._package is None:
            return QRegion(), QRegion()
        cached = self._region_cache.get(self._display_height)
        if cached is None:
            target_size = self.display_size
            window_region = _region_from_union(self._window_union, target_size, padding)
            interaction_region = _region_from_union(
                self._interaction_union,
                target_size,
                padding,
            )
            cached = (window_region, interaction_region)
            self._region_cache[self._display_height] = cached
        return QRegion(cached[0]), QRegion(cached[1])

    def _build_union_images(self) -> None:
        all_frames = []
        for spec in ANIMATION_SPECS.values():
            for frame_index in range(len(spec.durations_ms)):
                all_frames.append(self._source_frame(spec, frame_index))
        idle_spec = ANIMATION_SPECS["idle"]
        idle_frames = [
            self._source_frame(idle_spec, frame_index)
            for frame_index in range(len(idle_spec.durations_ms))
        ]
        source_size = QSize(CELL_WIDTH, CELL_HEIGHT)
        self._window_union = _union_images(all_frames, source_size)
        self._interaction_union = _union_images(idle_frames, source_size)

    def _source_frame(self, spec: AnimationSpec, frame_index: int) -> QImage:
        return self._atlas.copy(
            frame_index * CELL_WIDTH,
            spec.row * CELL_HEIGHT,
            CELL_WIDTH,
            CELL_HEIGHT,
        )

    def _pixmap(self, state: str, frame_index: int) -> QPixmap:
        key = (state, frame_index, self._display_height)
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached
        spec = ANIMATION_SPECS[state]
        image = self._source_frame(spec, frame_index).scaled(
            self.display_size,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        pixmap = QPixmap.fromImage(image)
        self._frame_cache[key] = pixmap
        return pixmap

    def _show_current_frame(self) -> None:
        if self._state is None:
            return
        self.frame_changed.emit(self._pixmap(self._state, self._frame_index))

    def _schedule_current_frame(self) -> None:
        if self._state is None:
            return
        duration = ANIMATION_SPECS[self._state].durations_ms[self._frame_index]
        self._timer.start(duration)

    def _advance_frame(self) -> None:
        if self._state is None:
            return
        state = self._state
        frame_count = len(ANIMATION_SPECS[state].durations_ms)
        next_index = self._frame_index + 1
        if next_index >= frame_count:
            if not self._loop:
                self.animation_finished.emit(state)
                return
            next_index = 0
        self._frame_index = next_index
        self._show_current_frame()
        self._schedule_current_frame()


@dataclass(frozen=True)
class GifVisual:
    source_size: QSize
    union_image: QImage

    def display_size(self, display_height: int) -> QSize:
        return scaled_canvas_size(self.source_size, display_height)

    def mask_region(self, display_height: int, padding: int = 2) -> QRegion:
        return _region_from_union(
            self.union_image,
            self.display_size(display_height),
            padding,
        )


def load_gif_visual(path: str, frame_limit: int = 512) -> GifVisual:
    reader = QImageReader(path)
    source_size = reader.size()
    if not source_size.isValid():
        raise ValueError(f"cannot read GIF geometry: {reader.errorString()}")

    frames = []
    for _ in range(frame_limit):
        frame_rect = reader.currentImageRect()
        image = reader.read()
        if image.isNull():
            break
        if image.size() != source_size:
            canvas = _blank_union(source_size)
            painter = QPainter(canvas)
            if not frame_rect.isValid() or frame_rect.isEmpty():
                frame_rect = reader.currentImageRect()
            x = frame_rect.x() if frame_rect.isValid() else 0
            y = frame_rect.y() if frame_rect.isValid() else 0
            painter.drawImage(x, y, image)
            painter.end()
            image = canvas
        frames.append(image.convertToFormat(QImage.Format_ARGB32_Premultiplied))
    if not frames:
        raise ValueError(f"cannot decode GIF: {reader.errorString()}")
    return GifVisual(source_size, _union_images(frames, source_size))
