"""GUI command and Task panel for building the honeycomb sketch."""

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part

try:
    from PySide import QtGui, QtCore
    from PySide.QtGui import (
        QWidget, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout,
        QDoubleSpinBox, QCheckBox, QComboBox, QToolButton, QPushButton,
        QButtonGroup, QGroupBox, QDialogButtonBox, QLabel, QMessageBox
    )
except ImportError:
    try:
        from PySide2 import QtGui, QtCore
        from PySide2.QtWidgets import (
            QWidget, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout,
            QDoubleSpinBox, QCheckBox, QComboBox, QToolButton, QPushButton,
            QButtonGroup, QGroupBox, QDialogButtonBox, QLabel, QMessageBox
        )
    except ImportError:
        from PySide6 import QtGui, QtCore
        from PySide6.QtWidgets import (
            QWidget, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout,
            QDoubleSpinBox, QCheckBox, QComboBox, QToolButton, QPushButton,
            QButtonGroup, QGroupBox, QDialogButtonBox, QLabel, QMessageBox
        )


try:
    from pivy import coin
except Exception:
    coin = None


def _help_icon(size=16):
    """Return a QIcon with a drawn "?" so it renders regardless of font."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setBrush(QtGui.QColor("#5a6b86"))
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(0, 0, size - 1, size - 1)
    f = p.font()
    f.setBold(True)
    f.setPointSizeF(size * 0.55)
    p.setFont(f)
    p.setPen(QtGui.QColor("white"))
    p.drawText(pix.rect(), QtCore.Qt.AlignCenter, "?")
    p.end()
    return QtGui.QIcon(pix)


def _arrow_icon(dx, dy, size=20):
    """Return a QIcon: arrow pointing in (dx, dy) screen direction, or a dot.

    dx, dy in {-1, 0, 1}; (0, 0) draws a centre dot.
    """
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    col = QtGui.QColor("#d0d0d0")
    c = size / 2.0
    if dx == 0 and dy == 0:
        p.setBrush(col)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(QtCore.QPointF(c, c), size * 0.16, size * 0.16)
    else:
        import math as _m
        length = size * 0.32
        n = _m.hypot(dx, dy)
        ux, uy = dx / n, dy / n
        ex, ey = c + ux * length, c + uy * length
        sx, sy = c - ux * length, c - uy * length
        pen = QtGui.QPen(col)
        pen.setWidthF(2.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(sx, sy), QtCore.QPointF(ex, ey))
        # arrowhead
        head = size * 0.18
        ang = _m.atan2(uy, ux)
        for da in (_m.radians(150), _m.radians(-150)):
            hx = ex + head * _m.cos(ang + da)
            hy = ey + head * _m.sin(ang + da)
            p.drawLine(QtCore.QPointF(ex, ey), QtCore.QPointF(hx, hy))
    p.end()
    return QtGui.QIcon(pix)


class _HelpLabel(QLabel):
    """A small clickable "?" badge that pops *text* on hover or click.

    QLabel is used instead of a tool button because FreeCAD's dark stylesheet
    can suppress custom content on QToolButton.
    """

    def __init__(self, text):
        super().__init__()
        self._help = text
        self.setPixmap(_help_icon(16).pixmap(16, 16))
        self.setFixedSize(18, 18)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setWhatsThis(text)
        self.setCursor(QtCore.Qt.WhatsThisCursor)

    def mousePressEvent(self, event):
        # Passing self.rect() makes Qt hide the tip once the cursor leaves it.
        QtGui.QToolTip.showText(QtGui.QCursor.pos(), self._help, self, self.rect())

    def leaveEvent(self, event):
        QtGui.QToolTip.hideText()


def _help_button(text):
    return _HelpLabel(text)


def _row_with_help(control, help_text):
    """Pack *control* and a help button side by side."""
    box = QHBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    box.addWidget(control)
    box.addWidget(_help_button(help_text))
    box.addStretch(1)
    return box


class HexFillTaskPanel:
    """Docked Task panel to configure and build the hexagonal grid."""

    def __init__(self, source, face, placement):
        self._source = source
        self._face = face
        self._placement = placement
        # Preview is drawn in the global scene graph, so it must account for any
        # parent Body/Part placement, not just the sketch's local one.
        try:
            self._global_placement = source.getGlobalPlacement()
        except Exception:
            self._global_placement = placement
        self._preview_node = None
        self._preview_sg = None

        self.form = QWidget()
        self.form.setWindowTitle("HexFill")
        root = QVBoxLayout(self.form)

        # --- Mode ---
        mode_form = QFormLayout()
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Manual", "Auto (strength)"])
        mode_form.addRow(
            "Mode:",
            _row_with_help(
                self.combo_mode,
                "Manual: set cell size and wall gap yourself.\n"
                "Auto: pick a strong honeycomb automatically from the profile "
                "size (~10 cells across, walls ≈ 20% of the cell)."))
        root.addLayout(mode_form)

        # --- Manual group ---
        self.grp_manual = QGroupBox("Manual parameters")
        mform = QFormLayout(self.grp_manual)

        self.spin_diameter = QDoubleSpinBox()
        self.spin_diameter.setSuffix(" mm")
        self.spin_diameter.setDecimals(3)
        self.spin_diameter.setRange(0.001, 1e6)
        self.spin_diameter.setValue(5.0)
        self.spin_diameter.setToolTip(
            "Circumscribed-circle diameter of one cell "
            "(vertex → center → vertex). Wrench size ≈ Diameter × √3/2.")
        mform.addRow("Diameter:", self.spin_diameter)

        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setSuffix(" mm")
        self.spin_gap.setDecimals(3)
        self.spin_gap.setRange(0.0, 1e6)
        self.spin_gap.setValue(1.0)
        self.spin_gap.setToolTip(
            "Wall-to-wall distance between neighbouring cells (= wall thickness).")
        mform.addRow("Gap:", self.spin_gap)

        self.chk_autofit = QCheckBox("shrink to fit")
        self.chk_autofit.setChecked(True)
        mform.addRow(
            "Auto-fit:",
            _row_with_help(
                self.chk_autofit,
                "Manual-mode safety net: if no cell fits at the given "
                "Diameter/Gap,\nthe Diameter is reduced automatically until "
                "the grid fits. Gap is kept."))
        root.addWidget(self.grp_manual)

        # --- Auto group ---
        self.grp_auto = QGroupBox("Auto parameters")
        aform = QVBoxLayout(self.grp_auto)
        self.lbl_auto = QLabel("…")
        self.lbl_auto.setWordWrap(True)
        aform.addWidget(self.lbl_auto)
        root.addWidget(self.grp_auto)

        # --- Layout group ---
        grp_layout = QGroupBox("Layout")
        lform = QFormLayout(grp_layout)

        self.chk_outfill = QCheckBox("fill to edge")
        self.chk_outfill.setChecked(False)
        lform.addRow(
            "Outfill:",
            _row_with_help(
                self.chk_outfill,
                "Trim border cells to the profile outline (fill up to the "
                "edge).\nOff: keep only fully-enclosed cells."))

        self._anchor_h = ["left", "center", "right"]
        self._anchor_v = ["top", "center", "bottom"]
        anchor_grid = QGridLayout()
        anchor_grid.setSpacing(2)
        self._anchor_group = QButtonGroup(self.form)
        self._anchor_group.setExclusive(True)
        anchor_wrap = QHBoxLayout()
        anchor_inner = QGridLayout()
        anchor_inner.setSpacing(2)
        for r in range(3):
            for c in range(3):
                btn = QPushButton()
                btn.setCheckable(True)
                btn.setIcon(_arrow_icon(c - 1, r - 1, 20))
                btn.setIconSize(QtCore.QSize(20, 20))
                btn.setFixedSize(30, 30)
                btn.setToolTip(f"anchor: {self._anchor_v[r]} / {self._anchor_h[c]}")
                self._anchor_group.addButton(btn, r * 3 + c)
                anchor_inner.addWidget(btn, r, c)
        self._anchor_group.button(4).setChecked(True)
        anchor_wrap.addLayout(anchor_inner)
        anchor_wrap.addStretch(1)
        lform.addRow("Anchor:", anchor_wrap)
        root.addWidget(grp_layout)

        # --- Preview ---
        self.chk_preview = QCheckBox("Live preview")
        self.chk_preview.setChecked(True)
        self.chk_preview.setToolTip(
            "Show a temporary preview of the grid in the 3D view while tuning.")
        root.addWidget(self.chk_preview)

        # --- Status ---
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)
        root.addStretch(1)

        # --- Signals ---
        self.combo_mode.currentIndexChanged.connect(self._refresh)
        self.spin_diameter.valueChanged.connect(self._refresh)
        self.spin_gap.valueChanged.connect(self._refresh)
        self.chk_outfill.toggled.connect(self._refresh)
        self.chk_autofit.toggled.connect(self._refresh)
        self.chk_preview.toggled.connect(self._refresh)
        self._anchor_group.buttonToggled.connect(self._refresh)

        self._refresh()

    @property
    def is_auto(self):
        return self.combo_mode.currentIndex() == 1

    @property
    def outfill(self):
        return self.chk_outfill.isChecked()

    @property
    def anchor(self):
        idx = self._anchor_group.checkedId()
        if idx < 0:
            idx = 4
        r, c = divmod(idx, 3)
        return (self._anchor_h[c], self._anchor_v[r])

    def _effective_params(self):
        if self.is_auto:
            from HexFillCore import auto_parameters
            return auto_parameters(self._face, self._placement)
        return self.spin_diameter.value(), self.spin_gap.value()

    def _resolve_diameter(self, diameter, gap):
        """Apply manual auto-fit shrinking; return the diameter to use."""
        from HexFillCore import generate_hex_cells_local
        if self.is_auto or not self.chk_autofit.isChecked():
            return diameter
        if generate_hex_cells_local(self._face, self._placement,
                                    diameter, gap, self.outfill, self.anchor):
            return diameter
        d = diameter
        for _ in range(20):
            d *= 0.8
            if d < 0.05:
                break
            if generate_hex_cells_local(self._face, self._placement,
                                        d, gap, self.outfill, self.anchor):
                return d
        return diameter

    def _refresh(self, *args):
        from HexFillCore import generate_hex_cells_local

        auto = self.is_auto
        self.grp_manual.setVisible(not auto)
        self.grp_auto.setVisible(auto)

        diameter, gap = self._effective_params()
        if auto:
            self.lbl_auto.setText(
                f"Picked automatically:\n"
                f"  • Diameter ≈ {diameter:.2f} mm\n"
                f"  • Gap ≈ {gap:.2f} mm  (wall ≈ 20%)")

        eff_d = self._resolve_diameter(diameter, gap)
        try:
            n = len(generate_hex_cells_local(
                self._face, self._placement, eff_d, gap, self.outfill, self.anchor))
        except Exception:
            n = 0

        if n > 0:
            self.lbl_status.setText(f"✓ About {n} cells will fit.")
            self.lbl_status.setStyleSheet("color: #3a8a3a;")
        else:
            self.lbl_status.setText(
                "✗ Nothing fits. Reduce Diameter/Gap, or enable "
                "Outfill / Auto / Auto-fit.")
            self.lbl_status.setStyleSheet("color: #b03030;")

        self._update_preview(eff_d, gap, n)

    def _update_preview(self, diameter, gap, n):
        """Draw the grid directly into the Coin3D scene graph (no tree object)."""
        self._clear_preview()
        if coin is None or not self.chk_preview.isChecked() or n <= 0:
            return
        from HexFillCore import generate_hex_wires_local
        try:
            wires = generate_hex_wires_local(
                self._face, self._placement, diameter, gap, self.outfill, self.anchor)
        except Exception:
            return
        if not wires:
            return

        # Collect each contour as a global-coordinate polyline. Walk the wire in
        # connection order (discretize) so edges never zig-zag across the cell.
        defl = max(diameter * 0.03, 0.05)
        polylines = []
        for wire in wires:
            try:
                samples = wire.discretize(Deflection=defl)
            except Exception:
                try:
                    samples = wire.discretize(60)
                except Exception:
                    continue
            pts = []
            for v in samples:
                g = self._global_placement.multVec(v)
                if not pts or (g - pts[-1]).Length > 1e-7:
                    pts.append(g)
            if len(pts) >= 2:
                if (pts[0] - pts[-1]).Length > 1e-7:
                    pts.append(pts[0])
                polylines.append(pts)
        if not polylines:
            return

        sep = coin.SoSeparator()
        color = coin.SoBaseColor()
        color.rgb.setValue(0.95, 0.6, 0.1)
        sep.addChild(color)
        dstyle = coin.SoDrawStyle()
        dstyle.lineWidth = 2.0
        sep.addChild(dstyle)

        coords = coin.SoCoordinate3()
        all_pts = []
        counts = []
        for pl in polylines:
            for p in pl:
                all_pts.append((p.x, p.y, p.z))
            counts.append(len(pl))
        coords.point.setValues(0, len(all_pts), all_pts)
        sep.addChild(coords)
        lineset = coin.SoLineSet()
        lineset.numVertices.setValues(0, len(counts), counts)
        sep.addChild(lineset)

        view = Gui.ActiveDocument.ActiveView
        sg = view.getSceneGraph()
        sg.addChild(sep)
        self._preview_node = sep
        self._preview_sg = sg

    def _clear_preview(self):
        node = getattr(self, "_preview_node", None)
        sg = getattr(self, "_preview_sg", None)
        if node is not None and sg is not None:
            try:
                sg.removeChild(node)
            except Exception:
                pass
        self._preview_node = None
        self._preview_sg = None

    def getStandardButtons(self):
        buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        try:
            return int(buttons)
        except TypeError:
            return buttons.value  # PySide6 strict enums

    def reject(self):
        self._clear_preview()
        App.ActiveDocument.recompute()
        Gui.Control.closeDialog()
        return True

    def accept(self):
        from HexFillCore import generate_hex_wires_local

        diameter, gap = self._effective_params()
        diameter = self._resolve_diameter(diameter, gap)
        wires = generate_hex_wires_local(
            self._face, self._placement, diameter, gap, self.outfill, self.anchor)
        if not wires:
            QMessageBox.information(
                self.form, "HexFill",
                "Nothing fits. Reduce Diameter/Gap, or enable "
                "Outfill / Auto / Auto-fit.")
            return False

        self._clear_preview()
        doc = App.ActiveDocument
        doc.openTransaction("HexFill grid")
        _build_hex_sketch(self._source, wires, self._placement)
        try:
            self._source.Visibility = False
        except Exception:
            pass
        doc.commitTransaction()
        doc.recompute()
        App.Console.PrintMessage(f"HexFill: created {len(wires)} cells.\n")
        Gui.Control.closeDialog()
        try:
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass
        return True


def _edge_to_geometry(edge):
    """Convert a local (Z=0) Part.Edge into a Sketcher geometry object.

    Handles straight segments and circular arcs (produced when outfill cells
    are clipped against a curved boundary); anything else is discretised.
    """
    curve = edge.Curve
    try:
        if isinstance(curve, Part.Line):
            p1 = edge.Vertexes[0].Point
            p2 = edge.Vertexes[-1].Point
            return [Part.LineSegment(p1, p2)]
        if isinstance(curve, Part.Circle):
            return [Part.ArcOfCircle(curve, edge.FirstParameter, edge.LastParameter)]
    except Exception:
        pass
    pts = edge.discretize(8)
    return [Part.LineSegment(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _build_hex_sketch(source, wires, placement):
    """Create a Sketcher sketch filled with *wires* (local-coord contours).

    The new sketch inherits the source's attachment and, if the source lives in
    a Body, is added to that Body so it can be used with PartDesign Pad / Pocket.
    """
    doc = App.ActiveDocument
    sketch = doc.addObject("Sketcher::SketchObject", "HexGrid")

    inherited = False
    for prop in ("AttachmentSupport", "Support", "MapMode", "AttachmentOffset",
                 "MapReversed", "MapPathParameter"):
        if hasattr(source, prop) and hasattr(sketch, prop):
            try:
                setattr(sketch, prop, getattr(source, prop))
                if prop in ("AttachmentSupport", "Support"):
                    inherited = True
            except Exception:
                pass

    if not inherited or getattr(sketch, "MapMode", "Deactivated") == "Deactivated":
        sketch.Placement = App.Placement(placement)

    for wire in wires:
        for edge in wire.Edges:
            for geom in _edge_to_geometry(edge):
                try:
                    sketch.addGeometry(geom, False)
                except Exception as exc:
                    App.Console.PrintWarning("HexFill: skipped an edge (%s)\n" % exc)

    try:
        body = source.getParentGeoFeatureGroup()
        if body is not None and body.isDerivedFrom("PartDesign::Body"):
            body.addObject(sketch)
    except Exception:
        pass

    return sketch


class CmdHexFillCreate:
    """Command: create a hexagonal-grid sketch from the selected sketch."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(
                os.path.dirname(__file__), "Resources", "icons", "HexFill.svg"
            ),
            "MenuText": "Create HexFill grid",
            "ToolTip": (
                "Fill a selected sketch with a hexagonal honeycomb pattern, "
                "producing a new sketch ready for Pad / Pocket."
            ),
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        return len(Gui.Selection.getSelection()) > 0

    def Activated(self):
        from HexFillCore import get_boundary_face, get_source_placement

        sel = Gui.Selection.getSelection()
        if not sel:
            App.Console.PrintError("HexFill: nothing selected. Select a sketch.\n")
            return

        source = sel[0]
        if not source.isDerivedFrom("Sketcher::SketchObject"):
            App.Console.PrintWarning(
                "HexFill: selected object is not a Sketch — trying to use its "
                "shape as a boundary anyway.\n"
            )

        face = get_boundary_face(source)
        if face is None:
            return  # error already printed

        placement = get_source_placement(source, face)
        panel = HexFillTaskPanel(source, face, placement)
        try:
            Gui.Control.showDialog(panel)
        except Exception:
            # A task dialog is probably already open.
            App.Console.PrintError(
                "HexFill: close the current task panel first, then retry.\n")


Gui.addCommand("HexFill_Create", CmdHexFillCreate())
