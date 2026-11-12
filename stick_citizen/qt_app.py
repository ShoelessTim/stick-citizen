"""Stick Citizen v2: see your sticks, drag SC actions onto them, save a layout SC can import."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from . import __version__, config as configmod  # noqa: E402
from .actionmaps import AXIS_NAMES, find_actionmaps, load_profile  # noqa: E402
from .bindings import ACTIVATION_MODES, BindingSet, load_catalog, mappings_dir  # noqa: E402
from .callouts import spoken  # noqa: E402
from .devices import DeviceManager, hat_dirs  # noqa: E402
from .templates import (COLS, CONTROL_H, GAP, TILE_H, TILE_W, auto_layout, load_template,  # noqa: E402
                        other_inputs, parse_tile_key)

MIME = "application/x-sc-action"

BG = QtGui.QColor(10, 12, 18)
PANEL = QtGui.QColor(18, 21, 30)
TILE = QtGui.QColor(30, 35, 48)
TILE_BOUND = QtGui.QColor(36, 52, 74)
FG = QtGui.QColor(222, 228, 238)
DIM = QtGui.QColor(118, 126, 140)
ACCENT = QtGui.QColor(255, 170, 40)
GOOD = QtGui.QColor(90, 220, 140)
HOT = QtGui.QColor(70, 200, 255)

STYLE = """
QWidget { background: #0a0c12; color: #dee4ee; font-family: 'Segoe UI', 'Bahnschrift', sans-serif; font-size: 10pt; }
QToolBar { background: #12151e; border: 0; spacing: 4px; padding: 4px; }
QToolButton { padding: 5px 10px; border-radius: 4px; }
QToolButton:hover { background: #242a38; }
QToolButton:checked { background: #2b4a6e; }
QLineEdit, QComboBox { background: #1a1e2a; border: 1px solid #2a3040; border-radius: 4px; padding: 4px 6px; }
QTreeWidget { background: #12151e; border: 0; }
QTreeWidget::item { padding: 3px 0; }
QTreeWidget::item:selected { background: #2b4a6e; }
QHeaderView::section { background: #12151e; color: #767e8c; border: 0; padding: 4px; }
QGraphicsView { border: 0; }
QStatusBar { background: #12151e; color: #767e8c; }
QMenu { background: #1a1e2a; border: 1px solid #2a3040; }
QMenu::item:selected { background: #2b4a6e; }
QSplitter::handle { background: #1a1e2a; }
"""


def input_label(kind, index, direction=""):
    if kind == "button":
        return f"Button {index}"
    if kind == "axis":
        return f"{AXIS_NAMES[index].upper()} axis"
    arrow = {"up": "▲", "down": "▼", "left": "◀", "right": "▶"}[direction]
    return f"Hat {index} {arrow}"


# ---------------------------------------------------------------- palette
class PaletteTree(QtWidgets.QTreeWidget):
    def mimeData(self, items):
        md = QtCore.QMimeData()
        it = items[0] if items else None
        data = it.data(0, QtCore.Qt.UserRole) if it else None
        if data:
            md.setData(MIME, f"{data[0]}|{data[1]}".encode())
            md.setText(data[1])
        return md

    def mimeTypes(self):
        return [MIME]


class Palette(QtWidgets.QWidget):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 4, 8)
        title = QtWidgets.QLabel("SC actions — drag onto a control")
        title.setStyleSheet("font-weight: 600; color: #ffaa28;")
        lay.addWidget(title)
        self.search = QtWidgets.QLineEdit(placeholderText="Search actions (e.g. gear, quantum, missile)")
        self.filter = QtWidgets.QComboBox()
        self.filter.addItems(["All actions", "Ship flight", "Unbound only", "Bound only", "Axes only"])
        lay.addWidget(self.search)
        lay.addWidget(self.filter)
        self.tree = PaletteTree()
        self.tree.setHeaderLabels(["Action", "On"])
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        lay.addWidget(self.tree, 1)
        self.items = []
        groups = {}
        for a in catalog.actions:
            a["_search"] = f"{a['label']} {a['action']} {spoken(a['action'])} {a['group']}".lower().replace("_", " ")
            g = groups.get(a["group"])
            if g is None:
                g = QtWidgets.QTreeWidgetItem([a["group"], ""])
                g.setFlags(QtCore.Qt.ItemIsEnabled)
                g.setForeground(0, QtGui.QBrush(ACCENT))
                groups[a["group"]] = g
                self.tree.addTopLevelItem(g)
            it = QtWidgets.QTreeWidgetItem([("⇕ " if a["axis"] else "") + a["label"], ""])
            it.setData(0, QtCore.Qt.UserRole, (a["map"], a["action"]))
            it.setToolTip(0, f"{a['action']}  ({a['map']})")
            it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDragEnabled)
            g.addChild(it)
            self.items.append((it, a))
        self.search.textChanged.connect(self.apply_filter)
        self.filter.currentIndexChanged.connect(self.apply_filter)
        self.bound = {}

    def current_action(self):
        it = self.tree.currentItem()
        return it.data(0, QtCore.Qt.UserRole) if it else None

    def refresh(self, bset: BindingSet):
        self.bound = {}
        for key, lst in bset.binds.items():
            kind, idx, d = key[1], key[2], key[3]
            short = {"button": f"B{idx}", "axis": AXIS_NAMES[idx] if kind == "axis" else "", "hat": f"H{idx}{d[:1].upper()}"}[kind]
            for b in lst:
                self.bound[(b.map, b.action)] = f"js{key[0]} {short}"
                self.bound.setdefault(("*", b.action), f"js{key[0]} {short}")
        for it, a in self.items:
            it.setText(1, self.bound.get((a["map"], a["action"])) or self.bound.get(("*", a["action"]), ""))
        self.apply_filter()

    def apply_filter(self):
        text = self.search.text().strip().lower()
        mode = self.filter.currentIndex()
        for it, a in self.items:
            show = True
            if text and text not in a["_search"]:
                show = False
            if mode == 1 and not a["map"].startswith("spaceship"):
                show = False
            bound = (a["map"], a["action"]) in self.bound or ("*", a["action"]) in self.bound
            if mode == 2 and bound or mode == 3 and not bound or mode == 4 and not a["axis"]:
                show = False
            it.setHidden(not show)
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            visible = any(not g.child(j).isHidden() for j in range(g.childCount()))
            g.setHidden(not visible)
            if text and visible:
                g.setExpanded(True)


# ---------------------------------------------------------------- tiles
class BaseTile(QtWidgets.QGraphicsObject):
    """Shared look and behaviour. A tile shows one or more inputs (rows); a control tile has a shift row."""

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.w, self.h = TILE_W, TILE_H
        self.active_keys = set()
        self.value = 0.0
        self.flash_t = 0.0
        self.drop_key = None
        self.setAcceptDrops(True)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

    # subclasses: rows() -> [(key, prefix)], title() -> str, kind
    kind = "button"
    movable = True

    def keys(self):
        return [k for k, _ in self.rows()]

    def key_at(self, pos):
        rows = self.rows()
        if len(rows) == 1:
            return rows[0][0]
        return rows[1][0] if pos.y() > 15 + 18 + 1 else rows[0][0]

    @property
    def active(self):
        return bool(self.active_keys)

    def set_key_active(self, key, on):
        if on:
            self.active_keys.add(key)
            self.flash_t = time.time()
        else:
            self.active_keys.discard(key)
        self.update()

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, p, opt, widget=None):
        main = self.view.main
        rows = [(k, pre, main.bset.at(k)) for k, pre in self.rows()]
        any_bound = any(b for _, _, b in rows)
        crowded = any(len(b) > 1 for _, _, b in rows)
        r = self.boundingRect().adjusted(1, 1, -1, -1)
        flash = max(0.0, 1.0 - (time.time() - self.flash_t) / 0.6)
        fill = QtGui.QColor(40, 120, 80) if self.active else QtGui.QColor(TILE_BOUND if any_bound else TILE)
        if main.has_backdrop(self.view):
            fill.setAlpha(225)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(fill)
        edge = ACCENT if crowded else (GOOD if self.active else QtGui.QColor(60, 68, 86))
        if flash > 0:
            edge = GOOD
        if self.isSelected():
            edge = HOT
        p.setPen(QtGui.QPen(edge, 2 if (crowded or self.isSelected() or flash) else 1))
        p.drawRoundedRect(r, 6, 6)
        if self.drop_key is not None:
            i = self.keys().index(self.drop_key) if self.drop_key in self.keys() else 0
            band = QtCore.QRectF(r.left() + 2, r.top() + 15 + i * 18 - 1, r.width() - 4, 19) if len(rows) > 1 else r
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(60, 90, 140))
            p.drawRoundedRect(band, 4, 4)
        if self.kind == "axis":
            v = max(-1.0, min(1.0, self.value))
            bar = QtCore.QRectF(r.left() + 4, r.bottom() - 6, (r.width() - 8), 3)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(50, 56, 72))
            p.drawRect(bar)
            mid = bar.left() + bar.width() / 2
            p.setBrush(GOOD)
            p.drawRect(QtCore.QRectF(min(mid, mid + v * bar.width() / 2), bar.top(), abs(v) * bar.width() / 2, 3))
        f = p.font()
        f.setPointSizeF(7.5)
        f.setBold(False)
        p.setFont(f)
        p.setPen(DIM)
        p.drawText(r.adjusted(6, 2, -4, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop,
                   p.fontMetrics().elidedText(self.title(), QtCore.Qt.ElideRight, int(r.width() - 10)))
        cat = main.catalog
        for i, (key, pre, binds) in enumerate(rows):
            f.setPointSizeF(8.5 if i == 0 else 8.0)
            f.setBold(i == 0)
            p.setFont(f)
            if key in self.active_keys:
                p.setPen(GOOD)
            else:
                p.setPen(FG if binds else DIM)
            if binds:
                text = cat.label(binds[0].map, binds[0].action)
                if binds[0].activation:
                    text += f" · {binds[0].activation.replace('_', ' ')}"
                if len(binds) > 1:
                    text += f"  +{len(binds) - 1}"
            else:
                text = "—"
            row = QtCore.QRectF(r.left() + 6, r.top() + 15 + i * 18, r.width() - 10, 18)
            p.drawText(row, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                       p.fontMetrics().elidedText(pre + text, QtCore.Qt.ElideRight, int(row.width())))

    def hoverEnterEvent(self, e):
        main = self.view.main
        lines = [self.title()]
        for key, pre in self.rows():
            for b in main.bset.at(key):
                lines.append(f"{pre or '• '}{main.catalog.label(b.map, b.action)}"
                             + (f" ({b.activation})" if b.activation else ""))
        self.setToolTip("\n".join(lines))

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            self.drop_key = self.key_at(e.pos())
            self.update()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        k = self.key_at(e.pos())
        if k != self.drop_key:
            self.drop_key = k
            self.update()
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.drop_key = None
        self.update()

    def dropEvent(self, e):
        key = self.key_at(e.pos())
        self.drop_key = None
        mapname, action = bytes(e.mimeData().data(MIME)).decode().split("|", 1)
        self.view.main.assign(key, mapname, action)
        e.acceptProposedAction()

    def contextMenuEvent(self, e):
        self.view.main.tile_menu(self, e.screenPos())

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and not self.view.main.edit_layout:
            self.view.main.on_tile_click(self, self.key_at(e.pos()))
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self.view.main.edit_layout and self.movable:
            self.view.save_positions()


class Tile(BaseTile):
    """One input: an axis, a hat direction, or a stray button number in the Other inputs drawer."""

    def __init__(self, view, tkey, in_drawer=False):
        super().__init__(view)
        self.tkey = tkey
        self.kind, self.index, self.direction = parse_tile_key(tkey)
        self.movable = not in_drawer
        if self.kind == "hat":
            self.w = TILE_W * 0.62

    @property
    def key(self):
        return (self.view.instance, self.kind, self.index, self.direction)

    def rows(self):
        return [(self.key, "")]

    def title(self):
        t = input_label(self.kind, self.index, self.direction)
        return t.replace("Hat ", "H") if self.kind == "hat" else t


class ControlTile(BaseTile):
    """A physical control from the device template; one row per layer (base, then shift)."""

    def __init__(self, view, control):
        super().__init__(view)
        self.control = control
        self.h = CONTROL_H if "shift" in control.inputs else TILE_H

    def rows(self):
        inst = self.view.instance
        out = [((inst, "button", self.control.inputs["base"], ""), "")] if "base" in self.control.inputs else []
        if "shift" in self.control.inputs:
            out.append(((inst, "button", self.control.inputs["shift"], ""), "⇧ "))
        return out

    def title(self):
        nums = " · ".join(("⇧" if layer == "shift" else "") + f"B{n}"
                          for layer, n in sorted(self.control.inputs.items()))
        return f"{self.control.label}   {nums}"


class DrawerHeader(QtWidgets.QGraphicsObject):
    """Click to show or hide button numbers that no physical control owns."""

    def __init__(self, view, count):
        super().__init__()
        self.view = view
        self.count = count
        self.flash_t = 0.0
        self.w = COLS * (TILE_W + GAP) - GAP
        self.h = 26
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip("Button numbers your stick reports that aren't mapped to a physical control: "
                        "shift layers, hat-as-buttons, tempo pulses. Only ones that are bound or have fired show here.")

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, p, opt, widget=None):
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        flash = max(0.0, 1.0 - (time.time() - self.flash_t) / 0.8)
        p.setPen(QtGui.QPen(GOOD if flash else QtGui.QColor(42, 48, 64), 1))
        p.setBrush(QtGui.QColor(22, 26, 36))
        p.drawRoundedRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        f = p.font()
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(DIM)
        arrow = "▾" if self.view.drawer_open else "▸"
        p.drawText(self.boundingRect().adjusted(10, 0, -10, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   f"{arrow}  Other inputs · {self.count}")
        f.setBold(False)
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.drawText(self.boundingRect().adjusted(10, 0, -10, 0), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                   "button numbers not on a physical control")

    def mousePressEvent(self, e):
        self.view.drawer_open = not self.view.drawer_open
        self.view.layout_drawer()


class DeviceView(QtWidgets.QGraphicsView):
    def __init__(self, main, instance):
        super().__init__()
        self.main = main
        self.instance = instance
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setBackgroundBrush(PANEL)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setAcceptDrops(True)
        self.tiles = {}            # axis + hat tiles by tile key
        self.control_tiles = {}    # control id -> ControlTile
        self.other_tiles = {}      # button number -> Tile (drawer)
        self.header = None
        self.drawer_open = None
        self.template = None
        self.backdrop = None
        self.num_buttons = None

    def all_tiles(self):
        return list(self.tiles.values()) + list(self.control_tiles.values()) + list(self.other_tiles.values())

    def build(self, device):
        sc = self.scene()
        sc.clear()
        self.tiles, self.control_tiles, self.other_tiles, self.header = {}, {}, {}, None
        self.backdrop = None
        if device is not None:
            name, na, nh, self.num_buttons = device.name, device.num_axes, device.num_hats, device.num_buttons
        else:
            used = [k for k in self.main.bset.binds if k[0] == self.instance]
            nh = max([k[2] for k in used if k[1] == "hat"] + [2])
            name, na, self.num_buttons = f"js{self.instance} (no device)", 6, None
        self.template = load_template(name, na, nh)
        if self.drawer_open is None:
            self.drawer_open = not self.template.controls
        img = self.template.image_path()
        if img:
            pm = QtGui.QPixmap(str(img))
            if not pm.isNull():
                self.backdrop = sc.addPixmap(pm)
                self.backdrop.setZValue(-10)
        valid = set(auto_layout(na, nh))
        for k, pos in self.template.tiles.items():
            if k not in valid:
                continue
            t = Tile(self, k)
            t.setPos(*pos)
            sc.addItem(t)
            self.tiles[k] = t
        for c in self.template.controls:
            t = ControlTile(self, c)
            t.setPos(*c.pos)
            sc.addItem(t)
            self.control_tiles[c.id] = t
        self.layout_drawer(fit=False)
        self.set_editable(self.main.edit_layout)
        self.fit()

    def bound_buttons(self):
        return {k[2] for k, v in self.main.bset.binds.items() if v and k[0] == self.instance and k[1] == "button"}

    def layout_drawer(self, fit=True):
        sc = self.scene()
        for t in self.other_tiles.values():
            sc.removeItem(t)
        if self.header is not None:
            sc.removeItem(self.header)
        self.other_tiles, self.header = {}, None
        nums = other_inputs(self.template, self.bound_buttons(), self.main.seen.get(self.instance, set()),
                            self.num_buttons)
        if nums:
            fixed = list(self.tiles.values()) + list(self.control_tiles.values())
            y = max([t.pos().y() + t.h for t in fixed] + [0]) + GAP * 3
            self.header = DrawerHeader(self, len(nums))
            self.header.setPos(0, y)
            sc.addItem(self.header)
            if self.drawer_open:
                for i, n in enumerate(nums):
                    t = Tile(self, f"b{n}", in_drawer=True)
                    t.setPos((i % COLS) * (TILE_W + GAP), y + 26 + GAP + (i // COLS) * (TILE_H + GAP))
                    sc.addItem(t)
                    self.other_tiles[n] = t
        rect = sc.itemsBoundingRect().adjusted(-12, -12, 12, 12)
        sc.setSceneRect(rect)
        if fit:
            self.fit()

    def button_changed(self, n, on):
        """Light whatever shows button n. Returns (tile or None, binding key)."""
        key = (self.instance, "button", n, "")
        c, _layer = self.template.control_for(n)
        if c:
            tile = self.control_tiles.get(c.id)
        else:
            tile = self.other_tiles.get(n)
            if tile is None and on:
                seen = self.main.seen.setdefault(self.instance, set())
                if n not in seen:
                    seen.add(n)
                    self.layout_drawer()
                    tile = self.other_tiles.get(n)
                if tile is None and self.header is not None:
                    self.header.flash_t = time.time()
                    self.header.update()
        if tile is not None:
            tile.set_key_active(key, on)
        return tile, key

    def selected_control(self):
        return next((t.control for t in self.control_tiles.values() if t.isSelected()), None)

    def fit(self):
        r = self.scene().sceneRect()
        if r.isEmpty():
            return
        self.fitInView(r, QtCore.Qt.KeepAspectRatio)
        if self.transform().m11() > 1.25:
            self.resetTransform()
            self.scale(1.25, 1.25)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit()

    def set_editable(self, on):
        for t in self.all_tiles():
            t.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, on and t.movable)
            t.setCursor(QtCore.Qt.SizeAllCursor if on and t.movable else QtCore.Qt.PointingHandCursor)

    def save_positions(self):
        if not self.template:
            return
        grid = 4
        for k, t in self.tiles.items():
            x, y = round(t.pos().x() / grid) * grid, round(t.pos().y() / grid) * grid
            t.setPos(x, y)
            self.template.tiles[k] = [x, y]
        for t in self.control_tiles.values():
            x, y = round(t.pos().x() / grid) * grid, round(t.pos().y() / grid) * grid
            t.setPos(x, y)
            t.control.pos = [x, y]
        self.template.save()
        self.layout_drawer(fit=False)


# ---------------------------------------------------------------- main window
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = configmod.load()
        self.catalog = load_catalog()
        self.bset = BindingSet()
        self.loaded_path = None
        self.loaded_mtime = 0.0
        self.edit_layout = False
        self.bind_by_press = False
        self.map_mode = False
        self.seen = {}   # SC instance -> button numbers seen firing this session
        from .speech import Speaker
        self.speaker = Speaker(enabled=self.cfg.get("speech", True))

        pygame.display.init()
        pygame.joystick.init()
        self.devices = DeviceManager(self.cfg)
        self.devices.refresh()
        self.prev = {}

        self.setWindowTitle("Stick Citizen")
        self.resize(1500, 900)
        self._build_ui()
        self.load_path(self.cfg.get("actionmaps_path") or find_actionmaps(), quiet=True)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(16)
        self.reload_timer = QtCore.QTimer(self)
        self.reload_timer.timeout.connect(self.check_reload)
        self.reload_timer.start(1000)

    # ----- UI -----
    def _build_ui(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        def act(text, slot, shortcut=None, checkable=False, tip=""):
            a = QtGui.QAction(text, self)
            a.setCheckable(checkable)
            a.setToolTip(tip or text)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act("Open…", self.open_dialog, "Ctrl+O", tip="Open actionmaps.xml or an exported layout")
        act("New (blank)", self.new_blank, tip="Start from no joystick bindings")
        act("Save layout…", self.save_dialog, "Ctrl+S", tip="Export a layout XML that SC can import")
        tb.addSeparator()
        act("Undo", self.undo, "Ctrl+Z")
        self.a_press = act("Bind by pressing", self.toggle_press, checkable=True,
                           tip="Select an action on the left, then press a stick button to bind it")
        self.a_map = act("Map controls", self.toggle_map, checkable=True,
                         tip="Press each physical control and name it. Press it again with your shift "
                             "button held to add its shift layer.")
        self.a_edit = act("Edit layout", self.toggle_edit, checkable=True,
                          tip="Drag tiles to match your stick; saved as a device template")
        self.a_bg = act("Set stick photo…", self.set_backdrop, tip="Put a photo of your stick behind the tiles")
        self.a_reset = act("Reset layout", self.reset_layout)
        tb.addSeparator()
        act("Fly test ▶", self.fly_test, "F5", tip="Fly the ring course with these bindings")
        self.a_mute = act("Mute", self.toggle_mute, checkable=True)
        self.a_mute.setChecked(not self.cfg.get("speech", True))
        self.a_bg.setEnabled(False)
        self.a_reset.setEnabled(False)

        split = QtWidgets.QSplitter()
        self.palette = Palette(self.catalog)
        split.addWidget(self.palette)
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(4, 8, 8, 8)
        self.devrow = QtWidgets.QHBoxLayout()
        rl.addLayout(self.devrow, 1)
        self.callout_lbl = QtWidgets.QLabel("Press a button on your stick")
        self.callout_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.callout_lbl.setStyleSheet("font-size: 20pt; font-weight: 700; padding: 10px; background: #12151e; border-radius: 8px;")
        rl.addWidget(self.callout_lbl)
        split.addWidget(right)
        split.setSizes([380, 1120])
        self.setCentralWidget(split)
        self.status = self.statusBar()
        self.views = {}
        self.combos = {}

    def has_backdrop(self, view):
        return view.backdrop is not None

    def rebuild_devices(self):
        while self.devrow.count():
            w = self.devrow.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.views, self.combos = {}, {}
        insts = sorted(set(self.devices.instances) | {k[0] for k in self.bset.binds} | {1, 2})
        for inst in insts:
            box = QtWidgets.QWidget()
            bl = QtWidgets.QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            head = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(f"SC js{inst}")
            lbl.setStyleSheet("font-weight: 700; color: #46c8ff;")
            combo = QtWidgets.QComboBox()
            combo.addItem("(no device)", -1)
            for i, d in enumerate(self.devices.devices):
                combo.addItem(d.name, i)
            cur = self.devices.instance_map.get(inst, -1)
            combo.setCurrentIndex(max(0, combo.findData(cur)))
            combo.currentIndexChanged.connect(lambda _i, inst=inst, c=combo: self.pick_device(inst, c.currentData()))
            head.addWidget(lbl)
            head.addWidget(combo, 1)
            bl.addLayout(head)
            view = DeviceView(self, inst)
            bl.addWidget(view, 1)
            self.devrow.addWidget(box, 1)
            self.views[inst] = view
            self.combos[inst] = combo
            view.build(self.devices.device_for(inst))

    def pick_device(self, inst, idx):
        if idx is None:
            return
        if idx < 0:
            self.devices.instance_map.pop(inst, None)
            self.cfg.setdefault("instances", {}).pop(str(inst), None)
        else:
            self.devices.instance_map[inst] = idx
            self.cfg.setdefault("instances", {})[str(inst)] = idx
        configmod.save(self.cfg)
        self.views[inst].build(self.devices.device_for(inst))

    def refresh_all(self):
        for v in self.views.values():
            v.scene().update()
        self.palette.refresh(self.bset)
        name = Path(self.loaded_path).name if self.loaded_path else "new layout"
        self.setWindowTitle(f"Stick Citizen {__version__} — {name}{' •' if self.bset.dirty else ''}")
        self.status.showMessage(f"{self.bset.count()} joystick bindings · {len(self.catalog.actions)} SC actions"
                                f" (SC {self.catalog.sc_version}) · {len(self.devices.devices)} controllers")

    # ----- bindings -----
    def load_path(self, path, quiet=False):
        if not path:
            self.bset = BindingSet()
            self.devices.assign({}, [1, 2])
            self.rebuild_devices()
            self.refresh_all()
            return
        try:
            prof = load_profile(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Couldn't open", f"{path}\n\n{e}")
            return
        self.bset = BindingSet.from_profile(prof)
        self.loaded_path = path
        self.loaded_mtime = os.path.getmtime(path)
        self.cfg["actionmaps_path"] = path
        configmod.save(self.cfg)
        self.devices.refresh()
        self.devices.assign(prof.devices, prof.instances)
        self.rebuild_devices()
        self.refresh_all()
        if not quiet:
            self.callout(f"Loaded {self.bset.count()} bindings", GOOD)

    def check_reload(self):
        if not self.loaded_path or self.bset.dirty:
            return
        try:
            m = os.path.getmtime(self.loaded_path)
        except OSError:
            return
        if m != self.loaded_mtime:
            self.load_path(self.loaded_path)
            self.callout("Bindings reloaded from disk", GOOD, speak="Bindings reloaded")

    def assign(self, key, mapname, action):
        cat = self.catalog
        is_axis_input = key[1] == "axis"
        if cat.is_axis(mapname, action) != is_axis_input:
            kind = "an axis" if cat.is_axis(mapname, action) else "a button"
            r = QtWidgets.QMessageBox.question(
                self, "Bind anyway?",
                f"“{cat.label(mapname, action)}” is {kind} action but you dropped it on "
                f"{'an axis' if is_axis_input else 'a button'}. Bind anyway?")
            if r != QtWidgets.QMessageBox.Yes:
                return
        old = self.bset.where(mapname, action)
        self.bset.assign(key, mapname, action, "" if is_axis_input else cat.default_activation(mapname, action))
        oldv = self.views.get(old[0]) if old else None
        moved = (f" (moved from js{old[0]} {self.input_name(oldv, old) if oldv else input_label(*old[1:])})"
                 if old and old != key else "")
        others = len(self.bset.at(key)) - 1
        colour = ACCENT if others else GOOD
        v = self.views.get(key[0])
        msg = f"{cat.label(mapname, action)} → js{key[0]} {self.input_name(v, key) if v else input_label(*key[1:])}{moved}"
        if others:
            msg += f"   [{others + 1} actions share this input]"
        self.callout(msg, colour)
        if v is not None:
            v.layout_drawer()
        self.refresh_all()

    def input_name(self, view, key):
        """Human name for a binding key: the physical control (and layer) when mapped."""
        if key[1] == "button" and view.template:
            c, layer = view.template.control_for(key[2])
            if c:
                return c.label + (" ⇧" if layer == "shift" else "")
        return input_label(*key[1:])

    def tile_menu(self, tile, pos):
        m = QtWidgets.QMenu(self)
        cat = self.catalog
        rows = tile.rows()
        for key, _pre in rows:
            binds = list(self.bset.at(key))
            if len(rows) > 1:
                m.addSection(self.input_name(tile.view, key))
            if not binds:
                a = m.addAction("Unbound — drag an action here")
                a.setEnabled(False)
            for b in binds:
                sub = m.addMenu(cat.label(b.map, b.action))
                if tile.kind != "axis":
                    am = sub.addMenu("Activation")
                    for mode in ACTIVATION_MODES:
                        x = am.addAction(mode.replace("_", " ") or "(game default)")
                        x.setCheckable(True)
                        x.setChecked(mode == b.activation)
                        x.triggered.connect(lambda _c=False, k=key, b=b, mode=mode: self._set_act(k, b, mode))
                rm = sub.addAction("Remove")
                rm.triggered.connect(lambda _c=False, k=key, b=b: self._remove(k, b))
            if binds:
                clr = m.addAction("Clear this input")
                clr.triggered.connect(lambda _c=False, k=key: (self.bset.clear(k), self.refresh_all()))
        if isinstance(tile, ControlTile):
            m.addSeparator()
            c, view = tile.control, tile.view
            m.addAction("Rename control…").triggered.connect(lambda: self.rename_control(view, c))
            if "shift" in c.inputs:
                m.addAction("Remove shift layer").triggered.connect(lambda: self.edit_control(view, c, drop_shift=True))
            m.addAction("Remove control (numbers go to Other inputs)").triggered.connect(
                lambda: self.edit_control(view, c, delete=True))
        m.exec(pos)

    # ----- mapping physical controls -----
    def toggle_map(self, on):
        self.map_mode = on
        if on and self.bind_by_press:
            self.a_press.setChecked(False)
            self.bind_by_press = False
        self.callout("Map controls: press each control on your stick and name it. "
                     "Select it, then press it with shift held to add the shift layer." if on else "Map saved", HOT)

    def _modal(self, fn):
        """Run a dialog with input polling paused, so held buttons don't re-fire behind it."""
        self.timer.stop()
        try:
            return fn()
        finally:
            self.timer.start(16)

    def map_button(self, view, n):
        t = view.template
        c, layer = t.control_for(n)
        if c:
            self._select_control(view, c.id)
            self.callout(f"{c.label}{' ⇧' if layer == 'shift' else ''} — already mapped (B{n})", DIM)
            return False
        sel = view.selected_control()
        choice = "new"
        if sel and "shift" not in sel.inputs:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Shift layer?")
            box.setText(f"Button {n} fired. Is that “{sel.label}” with shift held?")
            b_shift = box.addButton(f"Shift layer of {sel.label}", QtWidgets.QMessageBox.YesRole)
            b_new = box.addButton("New control", QtWidgets.QMessageBox.NoRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            self._modal(box.exec)
            clicked = box.clickedButton()
            choice = "shift" if clicked is b_shift else "new" if clicked is b_new else None
        if choice == "shift":
            t.set_layer(sel, "shift", n)
            cid, msg = sel.id, f"{sel.label} ⇧ = B{n}"
        elif choice == "new":
            name, ok = self._modal(lambda: QtWidgets.QInputDialog.getText(
                self, "Name this control", f"js{view.instance} button {n} — what is it on the stick?\n"
                "(e.g. Trigger, Pinky, A2 hat push, Thumb button)", text=f"Button {n}"))
            if not ok:
                return False
            c = t.add_control(name, n)
            cid, msg = c.id, f"{c.label} = B{n}"
        else:
            return False
        t.save()
        view.build(self.devices.device_for(view.instance))
        self._select_control(view, cid)
        self.callout(msg, GOOD)
        self.refresh_all()
        return True

    def _select_control(self, view, cid):
        for x in view.all_tiles():
            x.setSelected(False)
        tile = view.control_tiles.get(cid)
        if tile:
            tile.setSelected(True)
            view.ensureVisible(tile)

    def rename_control(self, view, c):
        name, ok = QtWidgets.QInputDialog.getText(self, "Rename control", "Name:", text=c.label)
        if ok and name.strip():
            c.label = name.strip()
            view.template.save()
            view.build(self.devices.device_for(view.instance))

    def edit_control(self, view, c, drop_shift=False, delete=False):
        if delete:
            view.template.remove_control(c)
        elif drop_shift:
            c.inputs.pop("shift", None)
        view.template.save()
        view.build(self.devices.device_for(view.instance))
        self.refresh_all()

    def _set_act(self, key, b, mode):
        self.bset.set_activation(key, b.map, b.action, mode)
        self.refresh_all()

    def _remove(self, key, b):
        self.bset.remove(key, b.map, b.action)
        self.refresh_all()

    def undo(self):
        if self.bset.undo():
            self.callout("Undone", DIM)
            self.refresh_all()

    # ----- files -----
    def open_dialog(self):
        if not self.confirm_discard():
            return
        start = str(Path(self.loaded_path).parent) if self.loaded_path else ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open SC bindings", start, "SC bindings (*.xml);;All files (*)")
        if path:
            self.load_path(path)

    def new_blank(self):
        if not self.confirm_discard():
            return
        devs = dict(self.bset.devices)
        self.bset = BindingSet("My HOSAS")
        self.bset.devices = devs
        self.loaded_path = None
        self.refresh_all()
        self.callout("Blank layout — drag actions onto your sticks", GOOD)

    def save_dialog(self):
        live = self.cfg.get("actionmaps_path") or find_actionmaps()
        d = mappings_dir(live)
        name = self.bset.name if self.bset.name and self.bset.name != "default" else "MyHOSAS"
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-") or "MyHOSAS"
        start = str((d or Path.home()) / f"layout_{safe}_exported.xml")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save SC layout", start, "SC layout (*.xml)")
        if not path:
            return False
        profile = Path(path).stem.removeprefix("layout_").removesuffix("_exported")
        for inst, idx in self.devices.instance_map.items():
            if 0 <= idx < len(self.devices.devices) and inst not in self.bset.devices:
                self.bset.devices[inst] = self.devices.devices[idx].name
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.bset.to_xml(profile), encoding="utf-8")
        self.bset.dirty = False
        self.refresh_all()
        in_sc = d is not None and Path(path).parent.resolve() == d.resolve()
        QtWidgets.QMessageBox.information(
            self, "Saved",
            f"Saved {self.bset.count()} bindings to\n{path}\n\n"
            + ("In Star Citizen: Options → Keybindings → Control Profiles → pick "
               f"“{profile}” and apply it to your joysticks." if in_sc else
               "Copy it into Star Citizen's user\\client\\0\\controls\\mappings folder, then in SC: "
               "Options → Keybindings → Control Profiles."))
        return True

    def confirm_discard(self):
        if not self.bset.dirty:
            return True
        r = QtWidgets.QMessageBox.question(
            self, "Unsaved changes", "Save your layout first?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if r == QtWidgets.QMessageBox.Save:
            return self.save_dialog()
        return r == QtWidgets.QMessageBox.Discard

    def closeEvent(self, e):
        if self.confirm_discard():
            e.accept()
        else:
            e.ignore()

    # ----- layout editing -----
    def toggle_edit(self, on):
        self.edit_layout = on
        self.a_bg.setEnabled(on)
        self.a_reset.setEnabled(on)
        for v in self.views.values():
            v.set_editable(on)
        self.callout("Layout edit: drag tiles to match your stick. Saved automatically." if on else "Layout saved", HOT)

    def _target_view(self):
        for v in self.views.values():
            if any(t.isSelected() for t in v.all_tiles()):
                return v
        insts = list(self.views)
        if not insts:
            return None
        name, ok = QtWidgets.QInputDialog.getItem(self, "Which stick?", "Stick:", [f"js{i}" for i in insts], 0, False)
        return self.views[int(name[2:])] if ok else None

    def set_backdrop(self):
        v = self._target_view()
        if not v:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Stick photo", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            v.template.image = path
            v.save_positions()
            v.build(self.devices.device_for(v.instance))

    def reset_layout(self):
        v = self._target_view()
        if not v:
            return
        if v.template and v.template.path and v.template.path.exists():
            v.template.path.unlink()
        v.build(self.devices.device_for(v.instance))

    # ----- live input -----
    def toggle_press(self, on):
        self.bind_by_press = on
        if on and self.map_mode:
            self.a_map.setChecked(False)
            self.map_mode = False
        self.callout("Pick an action on the left, then press the stick input to bind it" if on else "Bind by pressing off", HOT)

    def toggle_mute(self, on):
        self.cfg["speech"] = not on
        self.speaker.enabled = not on and os.name == "nt"
        configmod.save(self.cfg)

    def poll(self):
        try:
            for ev in pygame.event.get():
                if ev.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                    self.devices.refresh()
                    self.devices.assign(self.bset.devices, sorted(set(self.views) or {1, 2}))
                    self.rebuild_devices()
                    return
        except pygame.error:
            return
        order = self.cfg.get("axis_order") or list(range(8))
        dz = self.cfg.get("deadzone", 0.04)
        now = time.time()
        for inst, view in list(self.views.items()):
            d = self.devices.device_for(inst)
            if d is None:
                continue
            # every button number the device reports, mapped to a control or not
            for n in range(1, d.num_buttons + 1):
                on = bool(d.js.get_button(n - 1))
                pk = (inst, "b", n)
                if on != self.prev.get(pk, False):
                    self.prev[pk] = on
                    tile, key = view.button_changed(n, on)
                    if on and self.on_press(view, tile, key):
                        return   # view was rebuilt
            for k, t in view.tiles.items():
                if t.kind == "hat":
                    on = t.index <= d.num_hats and t.direction in hat_dirs(d.js.get_hat(t.index - 1))
                else:
                    ai = order[t.index] if t.index < len(order) else t.index
                    v = d.js.get_axis(ai) if ai < d.num_axes else 0.0
                    if abs(v - t.value) > 0.005:
                        t.value = v
                        t.update()
                    on = abs(v) > max(0.5, dz)
                pk = (inst, k)
                if on != self.prev.get(pk, False):
                    self.prev[pk] = on
                    t.set_key_active(t.key, on)
                    if on:
                        self.on_press(view, t, t.key)
            for t in view.all_tiles():
                if now - t.flash_t < 0.7:
                    t.update()
            if view.header is not None and now - view.header.flash_t < 0.9:
                view.header.update()

    def on_tile_click(self, tile, key):
        self.show_binds(tile.view, key, speak=False)

    def on_press(self, view, tile, key):
        """A physical press. Returns True if it rebuilt the view."""
        if self.map_mode and key[1] == "button":
            return self.map_button(view, key[2])
        if self.bind_by_press:
            act = self.palette.current_action()
            if act and (key[1] != "axis" or self.catalog.is_axis(*act)):
                self.assign(key, *act)
                return False
        if key[1] == "axis":
            return False
        if tile is not None:
            for t in view.all_tiles():
                t.setSelected(False)
            tile.setSelected(True)
            view.ensureVisible(tile)
        self.show_binds(view, key, speak=True)
        return False

    def show_binds(self, view, key, speak):
        binds = self.bset.at(key)
        label = f"js{view.instance} {self.input_name(view, key)}"
        if not binds:
            self.callout(f"{label}: unbound", DIM)
            return
        cat = self.catalog
        text = " / ".join(cat.label(b.map, b.action) for b in binds)
        self.callout(text, ACCENT if len(binds) > 1 else FG, speak=spoken(binds[0].action) if speak else None)

    def callout(self, text, colour=FG, speak=None):
        self.callout_lbl.setText(text)
        self.callout_lbl.setStyleSheet(
            f"font-size: 20pt; font-weight: 700; padding: 10px; background: #12151e; border-radius: 8px; color: {colour.name()};")
        if speak:
            self.speaker.say(speak)

    # ----- fly test -----
    def fly_test(self):
        tmp = Path(tempfile.gettempdir()) / "stick_citizen_flytest.xml"
        for inst, idx in self.devices.instance_map.items():
            if 0 <= idx < len(self.devices.devices) and inst not in self.bset.devices:
                self.bset.devices[inst] = self.devices.devices[idx].name
        tmp.write_text(self.bset.to_xml("FlyTest"), encoding="utf-8")
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "stick_citizen"]
        subprocess.Popen(cmd + ["--fly", str(tmp)])
        self.callout("Ring course launched — Esc to come back", HOT)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Stick Citizen")
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    return app.exec()
