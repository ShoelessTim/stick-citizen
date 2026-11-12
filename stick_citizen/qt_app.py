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

from . import config as configmod  # noqa: E402
from .actionmaps import AXIS_NAMES, find_actionmaps, load_profile  # noqa: E402
from .bindings import ACTIVATION_MODES, BindingSet, load_catalog, mappings_dir  # noqa: E402
from .callouts import spoken  # noqa: E402
from .devices import DeviceManager, hat_dirs  # noqa: E402
from .templates import TILE_H, TILE_W, auto_layout, load_template, parse_tile_key, tile_key  # noqa: E402

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
class Tile(QtWidgets.QGraphicsObject):
    def __init__(self, view, tkey):
        super().__init__()
        self.view = view
        self.tkey = tkey
        self.kind, self.index, self.direction = parse_tile_key(tkey)
        self.w = TILE_W * (0.62 if self.kind == "hat" else 1)
        self.h = TILE_H
        self.active = False
        self.value = 0.0
        self.flash_t = 0.0
        self.setAcceptDrops(True)
        self.setAcceptHoverEvents(True)
        self.drop_hover = False
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

    @property
    def key(self):
        return (self.view.instance, self.kind, self.index, self.direction)

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, p, opt, widget=None):
        binds = self.view.main.bset.at(self.key)
        r = self.boundingRect().adjusted(1, 1, -1, -1)
        fill = TILE_BOUND if binds else TILE
        flash = max(0.0, 1.0 - (time.time() - self.flash_t) / 0.6)
        if self.active or flash > 0:
            fill = QtGui.QColor(40, 120, 80) if self.active else fill
        if self.drop_hover:
            fill = QtGui.QColor(60, 90, 140)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        fill = QtGui.QColor(fill)
        if self.view.main.has_backdrop(self.view):
            fill.setAlpha(225)
        p.setBrush(fill)
        edge = ACCENT if len(binds) > 1 else (GOOD if self.active else QtGui.QColor(60, 68, 86))
        if flash > 0:
            edge = GOOD
        if self.isSelected():
            edge = HOT
        p.setPen(QtGui.QPen(edge, 2 if (len(binds) > 1 or self.isSelected() or flash) else 1))
        p.drawRoundedRect(r, 6, 6)
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
        p.setFont(f)
        p.setPen(DIM)
        title = input_label(self.kind, self.index, self.direction)
        if self.kind == "hat":
            title = title.replace("Hat ", "H")
        p.drawText(r.adjusted(6, 2, -4, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, title)
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(FG if binds else DIM)
        if binds:
            cat = self.view.main.catalog
            first = cat.label(binds[0].map, binds[0].action)
            if binds[0].activation:
                first += f" · {binds[0].activation.replace('_', ' ')}"
            text = first + (f"  +{len(binds) - 1}" if len(binds) > 1 else "")
        else:
            text = "—"
        p.drawText(r.adjusted(6, 15, -4, -6), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   p.fontMetrics().elidedText(text, QtCore.Qt.ElideRight, int(r.width() - 10)))

    def hoverEnterEvent(self, e):
        binds = self.view.main.bset.at(self.key)
        cat = self.view.main.catalog
        lines = [f"js{self.view.instance} {input_label(self.kind, self.index, self.direction)}"]
        lines += [f"• {cat.label(b.map, b.action)}" + (f" ({b.activation})" if b.activation else "") for b in binds]
        self.setToolTip("\n".join(lines))

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            self.drop_hover = True
            self.update()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.drop_hover = False
        self.update()

    def dropEvent(self, e):
        self.drop_hover = False
        mapname, action = bytes(e.mimeData().data(MIME)).decode().split("|", 1)
        self.view.main.assign(self.key, mapname, action)
        e.acceptProposedAction()

    def contextMenuEvent(self, e):
        self.view.main.tile_menu(self, e.screenPos())

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and not self.view.main.edit_layout:
            self.view.main.on_tile_click(self)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self.view.main.edit_layout:
            self.view.save_positions()


class DeviceView(QtWidgets.QGraphicsView):
    def __init__(self, main, instance):
        super().__init__()
        self.main = main
        self.instance = instance
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setBackgroundBrush(PANEL)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setAcceptDrops(True)
        self.tiles = {}
        self.template = None
        self.backdrop = None

    def build(self, device):
        sc = self.scene()
        sc.clear()
        self.tiles = {}
        self.backdrop = None
        if device is not None:
            name, na, nh, nb = device.name, device.num_axes, device.num_hats, device.num_buttons
        else:
            used = [k for k in self.main.bset.binds if k[0] == self.instance]
            nb = max([k[2] for k in used if k[1] == "button"] + [32])
            nh = max([k[2] for k in used if k[1] == "hat"] + [2])
            name, na = f"js{self.instance} (no device)", 6
        self.template = load_template(name, na, nh, nb)
        img = self.template.image_path()
        if img:
            pm = QtGui.QPixmap(str(img))
            if not pm.isNull():
                self.backdrop = sc.addPixmap(pm)
                self.backdrop.setZValue(-10)
        valid = set(auto_layout(na, nh, nb))
        for k, pos in self.template.tiles.items():
            if k not in valid:
                continue
            t = Tile(self, k)
            t.setPos(*pos)
            sc.addItem(t)
            self.tiles[k] = t
        self.set_editable(self.main.edit_layout)
        rect = sc.itemsBoundingRect().adjusted(-12, -12, 12, 12)
        sc.setSceneRect(rect)
        self.fit()

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
        for t in self.tiles.values():
            t.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, on)
            t.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
            t.setCursor(QtCore.Qt.SizeAllCursor if on else QtCore.Qt.PointingHandCursor)

    def save_positions(self):
        if not self.template:
            return
        grid = 4
        for k, t in self.tiles.items():
            x, y = round(t.pos().x() / grid) * grid, round(t.pos().y() / grid) * grid
            t.setPos(x, y)
            self.template.tiles[k] = [x, y]
        self.template.save()
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-12, -12, 12, 12))


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
        self.setWindowTitle(f"Stick Citizen — {name}{' •' if self.bset.dirty else ''}")
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
        moved = f" (moved from js{old[0]} {input_label(*old[1:])})" if old and old != key else ""
        others = len(self.bset.at(key)) - 1
        colour = ACCENT if others else GOOD
        msg = f"{cat.label(mapname, action)} → js{key[0]} {input_label(*key[1:])}{moved}"
        if others:
            msg += f"   [{others + 1} actions share this input]"
        self.callout(msg, colour)
        self.refresh_all()

    def tile_menu(self, tile, pos):
        m = QtWidgets.QMenu(self)
        binds = list(self.bset.at(tile.key))
        cat = self.catalog
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
                    x.triggered.connect(lambda _c=False, b=b, mode=mode: self._set_act(tile.key, b, mode))
            rm = sub.addAction("Remove")
            rm.triggered.connect(lambda _c=False, b=b: self._remove(tile.key, b))
        if binds:
            m.addSeparator()
            clr = m.addAction("Clear this input")
            clr.triggered.connect(lambda: (self.bset.clear(tile.key), self.refresh_all()))
        m.exec(pos)

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
            if any(t.isSelected() for t in v.tiles.values()):
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
        for inst, view in self.views.items():
            d = self.devices.device_for(inst)
            if d is None:
                continue
            for k, t in view.tiles.items():
                if t.kind == "button":
                    on = t.index <= d.num_buttons and bool(d.js.get_button(t.index - 1))
                elif t.kind == "hat":
                    on = t.index <= d.num_hats and t.direction in hat_dirs(d.js.get_hat(t.index - 1))
                else:
                    ai = order[t.index] if t.index < len(order) else t.index
                    v = d.js.get_axis(ai) if ai < d.num_axes else 0.0
                    if abs(v - t.value) > 0.005:
                        t.value = v
                        t.update()
                    on = abs(v) > max(0.5, dz)
                prev = self.prev.get((inst, k), False)
                if on != prev:
                    self.prev[(inst, k)] = on
                    t.active = on
                    if on:
                        t.flash_t = time.time()
                        self.on_press(view, t)
                    t.update()
                elif time.time() - t.flash_t < 0.7:
                    t.update()

    def on_tile_click(self, tile):
        self.show_binds(tile, speak=False)

    def on_press(self, view, tile):
        if self.bind_by_press and tile.kind != "axis":
            act = self.palette.current_action()
            if act:
                self.assign(tile.key, *act)
                return
        if self.bind_by_press and tile.kind == "axis":
            act = self.palette.current_action()
            if act and self.catalog.is_axis(*act):
                self.assign(tile.key, *act)
                return
        if tile.kind == "axis":
            return
        for t in view.tiles.values():
            t.setSelected(False)
        tile.setSelected(True)
        view.ensureVisible(tile)
        self.show_binds(tile, speak=True)

    def show_binds(self, tile, speak):
        binds = self.bset.at(tile.key)
        label = f"js{tile.view.instance} {input_label(tile.kind, tile.index, tile.direction)}"
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
