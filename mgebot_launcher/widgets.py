from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSize, QTimer, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel,
    QPushButton, QSlider, QSpinBox, QStyle, QVBoxLayout, QWidget)

ASSETS = Path(__file__).parent / "assets"


def icon(name: str) -> QIcon:
    return QIcon(str(ASSETS / "icons" / f"{name}.svg"))


def mix(a: str, b: str, ratio: float) -> QColor:
    x, y = QColor(a), QColor(b)
    return QColor(*(round(v + (w - v) * ratio) for v, w in zip(x.getRgb(), y.getRgb())))


class ActionButton(QPushButton):
    def __init__(self, text: str = "", symbol: str | None = None, primary=False, parent=None):
        super().__init__(text, parent)
        self.setProperty("primary", primary)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self.symbol = symbol
        self.hover = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._hover_changed)

    def _hover_changed(self, value):
        self.hover = float(value)
        self.update()

    def enterEvent(self, event):
        self.animation.stop(); self.animation.setStartValue(self.hover); self.animation.setEndValue(1.0); self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animation.stop(); self.animation.setStartValue(self.hover); self.animation.setEndValue(0.0); self.animation.start()
        super().leaveEvent(event)

    def sizeHint(self):
        base = super().sizeHint()
        return QSize(max(base.width() + (24 if self.symbol else 12), 42), max(base.height(), 40))

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary = bool(self.property("primary"))
        selected = self.isCheckable() and self.isChecked()
        ghost = bool(self.property("ghost"))
        if primary:
            fill = mix("#a78bfa", "#c4b5fd", self.hover); ink = QColor("#150f24")
        else:
            fill = mix("#17131f" if not ghost else "#0b0b0e", "#292037", self.hover)
            ink = QColor("#c4b5fd" if selected else "#ededf2")
        if selected:
            fill = QColor("#292037")
        if self.isDown():
            fill = fill.darker(116)
        if not self.isEnabled():
            fill = QColor("#25202f" if primary else "#131117"); ink = QColor("#776e88")
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor("#c4b5fd" if self.hasFocus() else "#59466f" if selected else "#30243f"), 1.5 if self.hasFocus() else 1))
        painter.drawRoundedRect(box, 9, 9)
        painter.setFont(QFont("Manrope", 10, QFont.Weight.DemiBold))
        painter.setPen(ink)
        text_box = box.adjusted(13, 0, -13, 0)
        if self.symbol:
            size = 18
            x = text_box.left() + (text_box.width() - self.fontMetrics().horizontalAdvance(self.text()) - 26) / 2 if self.text() else (self.width() - size) / 2
            pixmap = icon(self.symbol).pixmap(size, size)
            tinted = pixmap.copy()
            p = QPainter(tinted); p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn); p.fillRect(tinted.rect(), ink); p.end()
            painter.drawPixmap(round(x), round((self.height() - size) / 2), tinted)
            text_box.setLeft(x + size + 8)
            if self.text():
                painter.drawText(text_box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        else:
            painter.drawText(text_box, Qt.AlignmentFlag.AlignCenter, self.text())


class Toggle(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.position = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(30)
        self.anim = QVariantAnimation(self); self.anim.setDuration(160); self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._position)
        self.toggled.connect(self._toggle)

    def _position(self, value):
        self.position = float(value); self.update()

    def _toggle(self, checked):
        self.anim.stop(); self.anim.setStartValue(self.position); self.anim.setEndValue(1.0 if checked else 0.0); self.anim.start()

    def sizeHint(self):
        return QSize(43 + self.fontMetrics().horizontalAdvance(self.text()) + 8, 32)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled(): p.setOpacity(0.45)
        track = QRectF(1, (self.height() - 20) / 2, 34, 20)
        p.setPen(QPen(QColor("#c4b5fd" if self.hasFocus() else "#59466f"), 1))
        p.setBrush(mix("#292331", "#a78bfa", self.position)); p.drawRoundedRect(track, 10, 10)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#160f23" if self.isChecked() else "#d3cadf"))
        p.drawEllipse(QRectF(4 + 14 * self.position, track.top() + 3, 14, 14))
        p.setPen(QColor("#d6cce4")); p.drawText(QRectF(45, 0, self.width() - 45, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())


class SeekSlider(QSlider):
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = 8 + (self.width() - 16) * (self.value() - self.minimum()) / max(1, self.maximum() - self.minimum())
        y = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#392c49")); p.drawRoundedRect(QRectF(8, y - 2, self.width() - 16, 4), 2, 2)
        p.setBrush(QColor("#a78bfa" if self.isEnabled() else "#5c4c6d")); p.drawRoundedRect(QRectF(8, y - 2, max(0, x - 8), 4), 2, 2)
        p.setPen(QPen(QColor("#d8c8ff"), 1) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(QColor("#e0d2ff" if self.isEnabled() else "#83728e")); p.drawEllipse(QRectF(x - 7, y - 7, 14, 14))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            position = max(0, min(self.width() - 16, round(event.position().x()) - 8))
            self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, max(1, self.width() - 16)))
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus(): super().wheelEvent(event)
        else: event.ignore()


class NumberBox(QSpinBox):
    def focusInEvent(self, event):
        super().focusInEvent(event); QTimer.singleShot(0, self.lineEdit().selectAll)


class DecimalBox(QDoubleSpinBox):
    def focusInEvent(self, event):
        super().focusInEvent(event); QTimer.singleShot(0, self.lineEdit().selectAll)


class NumericControl(QWidget):
    valueChanged = pyqtSignal(object)

    def __init__(self, title: str, low: float, high: float, step=1, unit="", automatic=None,
                 automatic_label="Auto", automatic_hint="Uses the selected difficulty", parent=None):
        super().__init__(parent)
        self.automatic_value = automatic
        self.integer = isinstance(step, int)
        self.loading = False
        box = QVBoxLayout(self); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(9)
        top = QHBoxLayout(); top.setSpacing(8)
        label = QLabel(title); label.setTextFormat(Qt.TextFormat.PlainText); label.setObjectName("FieldLabel")
        top.addWidget(label, 1)
        self.automatic = Toggle(automatic_label) if automatic is not None else None
        if self.automatic:
            self.automatic.setAccessibleName(title + ": " + automatic_label)
            self.automatic.toggled.connect(self._changed)
            top.addWidget(self.automatic)
        box.addLayout(top)
        self.value_row = QWidget(); row = QHBoxLayout(self.value_row); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(12)
        self.slider = SeekSlider(Qt.Orientation.Horizontal); self.slider.setAccessibleName(title)
        self.scale = 1 if self.integer else 100
        self.slider.setRange(round(low * self.scale), round(high * self.scale)); self.slider.setSingleStep(max(1, round(step * self.scale)))
        self.spin = NumberBox() if self.integer else DecimalBox()
        self.spin.setRange(low, high); self.spin.setSingleStep(step)
        if not self.integer: self.spin.setDecimals(2)
        self.spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin.setFixedWidth(76); self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setAccessibleName(title + ": value")
        self.spin.setObjectName("NumericValue"); label.setBuddy(self.spin); self.setFocusProxy(self.spin)
        row.addWidget(self.slider, 1); row.addWidget(self.spin)
        if unit:
            suffix = QLabel(unit); suffix.setObjectName("Muted"); row.addWidget(suffix)
        self.slider.valueChanged.connect(self._slider_changed)
        self.spin.valueChanged.connect(self._spin_changed)
        box.addWidget(self.value_row)
        self.hint = QLabel(automatic_hint); self.hint.setObjectName("Muted"); self.hint.setMinimumHeight(36); self.hint.hide(); box.addWidget(self.hint)
        self.setMinimumHeight(79)

    def _changed(self, *args):
        auto = bool(self.automatic and self.automatic.isChecked())
        self.value_row.setVisible(not auto); self.hint.setVisible(auto)
        if not self.loading: self.valueChanged.emit(self.value())

    def _slider_changed(self, value):
        self.spin.blockSignals(True); self.spin.setValue(value if self.integer else value / self.scale); self.spin.blockSignals(False)
        if not self.loading: self.valueChanged.emit(self.value())

    def _spin_changed(self, value):
        self.slider.blockSignals(True); self.slider.setValue(round(value * self.scale)); self.slider.blockSignals(False)
        if not self.loading: self.valueChanged.emit(self.value())

    def value(self):
        if self.automatic and self.automatic.isChecked(): return self.automatic_value
        return self.spin.value()

    def setValue(self, value):
        self.loading = True
        auto = self.automatic_value is not None and value == self.automatic_value
        if self.automatic: self.automatic.setChecked(auto)
        if not auto:
            self.spin.setValue(value); self.slider.setValue(round(value * self.scale))
        elif self.spin.value() == self.spin.minimum():
            default = min(self.spin.maximum(), max(self.spin.minimum(), 75 if self.automatic_value == -1 else 300))
            self.spin.setValue(default); self.slider.setValue(round(default * self.scale))
        self._changed(); self.loading = False


class WindowBar(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window(); window.showNormal() if window.isMaximized() else window.showMaximized()


class ClassButton(QPushButton):
    def __init__(self, class_id: int, name: str, filename: str, parent=None):
        super().__init__(name, parent)
        self.class_id = class_id; self.class_icon = QIcon(str(ASSETS / "classes" / f"{filename}.svg"))
        self.setCheckable(True); self.setMinimumSize(58, 70); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(name)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        chosen = self.isChecked(); hover = self.underMouse()
        p.setBrush(QColor("#282037" if chosen else "#1a1524" if hover else "#111016"))
        p.setPen(QPen(QColor("#a78bfa" if chosen or self.hasFocus() else "#30243f"), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
        self.class_icon.paint(p, int((self.width() - 30) / 2), 10, 30, 30)
        p.setFont(QFont("Manrope", 8, QFont.Weight.DemiBold)); p.setPen(QColor("#d7c8ff" if chosen else "#b4a9c3"))
        p.drawText(QRectF(1, 43, self.width() - 2, 24), Qt.AlignmentFlag.AlignCenter, self.text())


class WelcomeReveal(QWidget):

    def __init__(self, parent):
        super().__init__(parent)
        self.progress = 0.0; self.setGeometry(parent.rect())
        self.animation = QVariantAnimation(self); self.animation.setDuration(760)
        self.animation.setStartValue(0.0); self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self.deleteLater)
        self.show(); self.raise_(); self.animation.start()

    def _frame(self, value): self.progress = float(value); self.update()

    def mousePressEvent(self, event): self.animation.stop(); self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fade = min(1.0, (1.0 - self.progress) / .32)
        p.setOpacity(fade); p.fillRect(self.rect(), QColor("#0b0b0e"))
        center = self.rect().center(); glow = QRadialGradient(center.x(), center.y() - 24, 230)
        glow.setColorAt(0, QColor("#241934")); glow.setColorAt(1, QColor("#0b0b0e")); p.fillRect(self.rect(), glow)
        arrival = 1.0 - pow(1.0 - min(1.0, self.progress / .6), 4)
        p.setOpacity(fade * arrival)
        QIcon(str(ASSETS / "logo.svg")).paint(p, center.x() - 38, round(center.y() - 80 + (1 - arrival) * 14), 76, 76)
        p.setFont(QFont("Golos Text", 26, QFont.Weight.ExtraBold)); p.setPen(QColor("#ededf2"))
        p.drawText(QRectF(0, center.y() + 16, self.width(), 58), Qt.AlignmentFlag.AlignCenter, "mgebot duel")
