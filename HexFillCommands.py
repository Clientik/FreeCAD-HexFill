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


class _SpinBox(QDoubleSpinBox):
    """Spin box that commits Enter without triggering the panel's OK button."""

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            event.accept()  # stop it bubbling up to the task dialog's accept()


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

    def mouseReleaseEvent(self, event):
        # Fire on a full click (release), not while the button is held down.
        # Passing self.rect() makes Qt hide the tip once the cursor leaves it.
        QtGui.QToolTip.showText(QtGui.QCursor.pos(), self._help, self, self.rect())

    def leaveEvent(self, event):
        QtGui.QToolTip.hideText()


def _warn_icon(size=16):
    """A drawn amber circle with a white "!" (works regardless of font)."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setBrush(QtGui.QColor("#c08020"))
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(0, 0, size - 1, size - 1)
    f = p.font()
    f.setBold(True)
    f.setPointSizeF(size * 0.6)
    p.setFont(f)
    p.setPen(QtGui.QColor("white"))
    p.drawText(pix.rect(), QtCore.Qt.AlignCenter, "!")
    p.end()
    return QtGui.QIcon(pix)


def _warn_badge(text):
    lbl = _HelpLabel(text)
    lbl.setPixmap(_warn_icon(16).pixmap(16, 16))
    return lbl


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


_PREVIEW_NODE_NAME = "HexFillPreview"


def _remove_stale_previews():
    """Remove any leftover preview nodes from the active view's scene graph.

    Matching by name means cleanup never depends on the panel closing cleanly,
    so a preview can't be orphaned in the 3D view.
    """
    if coin is None:
        return
    try:
        view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
        if view is None:
            return
        sg = view.getSceneGraph()
        for i in reversed(range(sg.getNumChildren())):
            child = sg.getChild(i)
            try:
                nm = child.getName()
                nm = nm.getString() if hasattr(nm, "getString") else str(nm)
                if nm == _PREVIEW_NODE_NAME:
                    sg.removeChild(child)
            except Exception:
                pass
    except Exception:
        pass


class HexFillTaskPanel:
    """Docked Task panel to configure and build the hexagonal grid."""

    def __init__(self, source, face, placement, host_face=None):
        self._source = source
        self._face = face                 # interior of the sketch contour
        self._active_face = face
        self._host_shape = host_face       # the host solid (may be None)
        self._active_sig = None
        self._placement = placement
        # Material cross-section of the part at the sketch plane: outer wire is
        # the physical edge, inner wires are the cutouts. Computed once.
        try:
            from HexFillCore import host_material_region
            self._host_region = host_material_region(host_face, placement)
        except Exception:
            self._host_region = None
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

        self.spin_diameter = _SpinBox()
        self.spin_diameter.setSuffix(" mm")
        self.spin_diameter.setDecimals(3)
        self.spin_diameter.setRange(0.001, 1e6)
        self.spin_diameter.setValue(5.0)
        self.spin_diameter.setKeyboardTracking(False)  # update on commit, not keystroke
        self.spin_diameter.setToolTip(
            "Circumscribed-circle diameter of one cell "
            "(vertex → center → vertex). Wrench size ≈ Diameter × √3/2.")
        mform.addRow("Diameter:", self.spin_diameter)

        self.spin_gap = _SpinBox()
        self.spin_gap.setSuffix(" mm")
        self.spin_gap.setDecimals(3)
        self.spin_gap.setRange(0.0, 1e6)
        self.spin_gap.setValue(1.0)
        self.spin_gap.setKeyboardTracking(False)
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

        self.combo_fill = QComboBox()
        self.combo_fill.addItems(["Outer", "Inner"])
        lform.addRow(
            "Fill:",
            _row_with_help(
                self.combo_fill,
                "Which area to fill:\n"
                "  Outer - the area around the inner shapes.\n"
                "  Inner - inside the inner closed shapes."))

        self.chk_outfill = QCheckBox("clip to contour")
        self.chk_outfill.setChecked(False)
        lform.addRow(
            "Outfill:",
            _row_with_help(
                self.chk_outfill,
                "Trim border cells exactly at the contour (outer outline and\n"
                "inner holes), filling right up to every edge.\n"
                "Off: keep only whole cells that fit fully inside."))

        # Existing cutouts on the attached face are always subtracted (no UI).

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

        # --- Experimental group: margin ---
        grp_exp = QGroupBox("Experimental")
        eform = QFormLayout(grp_exp)

        enable_row = QHBoxLayout()
        enable_row.setContentsMargins(0, 0, 0, 0)
        enable_row.setSpacing(4)
        self.chk_margin = QCheckBox("Margin")
        self.chk_margin.setChecked(False)
        enable_row.addWidget(self.chk_margin)
        enable_row.addWidget(_warn_badge(
            "Experimental: clearance via 2D offsets; can be slow or imperfect\n"
            "on very complex boolean geometry."))
        enable_row.addStretch(1)
        eform.addRow("Enable:", enable_row)

        self.combo_margin_mode = QComboBox()
        self.combo_margin_mode.addItems(
            ["From contour", "Contour + edge", "From edge"])
        eform.addRow(
            "Mode:",
            _row_with_help(
                self.combo_margin_mode,
                "Where to keep the clearance frame (cutouts are always kept clear):\n"
                "  From contour - fill stops short of the contour, reaches the edge.\n"
                "  From edge - fill stops short of the part edge, reaches the contour.\n"
                "  Contour + edge - both."))

        self.spin_margin = _SpinBox()
        self.spin_margin.setSuffix(" mm")
        self.spin_margin.setDecimals(3)
        self.spin_margin.setRange(0.0, 1e6)
        self.spin_margin.setValue(1.0)
        self.spin_margin.setKeyboardTracking(False)
        eform.addRow("Value:", self.spin_margin)
        root.addWidget(grp_exp)

        # Margin controls are available only when enabled.
        def _toggle_margin(on):
            self.combo_margin_mode.setEnabled(on)
            self.spin_margin.setEnabled(on)
        self.chk_margin.toggled.connect(_toggle_margin)
        _toggle_margin(False)

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
        self.combo_fill.currentIndexChanged.connect(self._refresh)
        self.chk_outfill.toggled.connect(self._refresh)
        self.chk_margin.toggled.connect(self._refresh)
        self.combo_margin_mode.currentIndexChanged.connect(self._refresh)
        self.spin_margin.valueChanged.connect(self._refresh)
        self.chk_autofit.toggled.connect(self._refresh)
        self.chk_preview.toggled.connect(self._refresh)
        self._anchor_group.buttonToggled.connect(self._refresh)

        # Remove the preview even if the panel is closed without OK/Cancel.
        try:
            self.form.destroyed.connect(self._clear_preview)
        except Exception:
            pass

        self._refresh()

    @property
    def is_auto(self):
        return self.combo_mode.currentIndex() == 1

    @property
    def outfill(self):
        return self.chk_outfill.isChecked()

    @property
    def inverse(self):
        return self.combo_fill.currentIndex() == 1

    @property
    def margin(self):
        return self.spin_margin.value() if self.chk_margin.isChecked() else 0.0

    @property
    def margin_mode(self):
        return ("contour", "both", "edge")[self.combo_margin_mode.currentIndex()]

    def _sync_active_face(self):
        """Region to fill from the Fill mode and Margin.

        The sketch contour splits the part: Inner fills inside it, Outer fills
        the part material outside it (up to the physical edge). Both stay clear
        of the part's existing cutouts. Margin keeps a ring around those cutouts
        only. Cached so the boolean work runs only when mode/margin change.
        """
        sig = (self.inverse, round(self.margin, 4), self.margin_mode)
        if sig == self._active_sig:
            return
        from HexFillCore import subtract_host_holes, apply_clearance

        contour = self._face
        region = self._host_region

        if region is None:
            # No host solid: fall back to the contour interior, minus any holes.
            base = subtract_host_holes(contour, self._host_shape)
        elif self.inverse:
            # Inner: part material inside the contour.
            try:
                base = region.common(contour)
                base = base if base.Faces else region
            except Exception:
                base = region
        else:
            # Outer: part material outside the contour (up to the edge).
            try:
                base = region.cut(contour)
                base = base if base.Faces else region
            except Exception:
                base = region

        if self.margin > 0:
            base = apply_clearance(base, region, self.margin, self.margin_mode)

        self._active_face = base
        self._active_sig = sig

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
            return auto_parameters(self._active_face, self._placement)
        return self.spin_diameter.value(), self.spin_gap.value()

    def _resolve_diameter(self, diameter, gap):
        """Apply manual auto-fit shrinking; return the diameter to use."""
        from HexFillCore import generate_hex_cells_local
        if self.is_auto or not self.chk_autofit.isChecked():
            return diameter
        if generate_hex_cells_local(self._active_face, self._placement,
                                    diameter, gap, self.outfill, self.anchor):
            return diameter
        d = diameter
        for _ in range(20):
            d *= 0.8
            if d < 0.05:
                break
            if generate_hex_cells_local(self._active_face, self._placement,
                                        d, gap, self.outfill, self.anchor):
                return d
        return diameter

    def _refresh(self, *args):
        from HexFillCore import generate_hex_cells_local, estimate_grid_positions, MAX_CELLS

        try:
            self._sync_active_face()
            auto = self.is_auto
            self.grp_manual.setVisible(not auto)
            self.grp_auto.setVisible(auto)

            diameter, gap = self._effective_params()
            if auto:
                self.lbl_auto.setText(
                    f"Picked automatically:\n"
                    f"  • Diameter ≈ {diameter:.2f} mm\n"
                    f"  • Gap ≈ {gap:.2f} mm  (wall ≈ 20%)")

            # Guard against a diameter so small it would make a huge grid.
            if estimate_grid_positions(self._active_face, self._placement,
                                       diameter, gap) > MAX_CELLS:
                self._clear_preview()
                self.lbl_status.setText(
                    "⚠ Cells are too small for this profile — increase Diameter.")
                self.lbl_status.setStyleSheet("color: #b07000;")
                return

            eff_d = self._resolve_diameter(diameter, gap)
            try:
                n = len(generate_hex_cells_local(
                    self._active_face, self._placement, eff_d, gap,
                    self.outfill, self.anchor))
            except Exception:
                n = 0

            if n > 0:
                self.lbl_status.setText(f"✓ About {n} cells will fit.")
                self.lbl_status.setStyleSheet("color: #3a8a3a;")
            else:
                self.lbl_status.setText(
                    "✗ Nothing fits. Reduce Diameter/Gap, try Outfill, "
                    "Auto or Auto-fit.")
                self.lbl_status.setStyleSheet("color: #b03030;")

            self._update_preview(eff_d, gap, n)
        except Exception as exc:
            # The panel must never crash FreeCAD on a stray value.
            App.Console.PrintWarning("HexFill: preview update failed (%s)\n" % exc)

    def _wires_to_polylines(self, wires, defl):
        """Discretise local wires and map them to global-view polylines."""
        out = []
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
                out.append(pts)
        return out

    @staticmethod
    def _line_node(polylines, rgb, width):
        """Build a Coin separator drawing *polylines* in colour *rgb*."""
        node = coin.SoSeparator()
        col = coin.SoBaseColor()
        col.rgb.setValue(*rgb)
        node.addChild(col)
        style = coin.SoDrawStyle()
        style.lineWidth = width
        node.addChild(style)
        coords = coin.SoCoordinate3()
        all_pts, counts = [], []
        for pl in polylines:
            for p in pl:
                all_pts.append((p.x, p.y, p.z))
            counts.append(len(pl))
        coords.point.setValues(0, len(all_pts), all_pts)
        node.addChild(coords)
        lineset = coin.SoLineSet()
        lineset.numVertices.setValues(0, len(counts), counts)
        node.addChild(lineset)
        return node

    def _update_preview(self, diameter, gap, n):
        """Draw the grid (orange) and the fill boundary (white) into the scene."""
        self._clear_preview()
        if coin is None or not self.chk_preview.isChecked():
            return
        defl = max(diameter * 0.03, 0.05)
        sep = coin.SoSeparator()
        sep.setName(_PREVIEW_NODE_NAME)

        # White outline of the actual fill region (after holes + margin).
        try:
            flat = self._active_face.copy()
            flat.transformShape(self._placement.inverse().toMatrix(), True)
            bnd = self._wires_to_polylines(flat.Wires, defl)
            if bnd:
                sep.addChild(self._line_node(bnd, (1.0, 1.0, 1.0), 1.5))
        except Exception:
            pass

        # Orange honeycomb cells.
        if n > 0:
            try:
                from HexFillCore import generate_hex_wires_local
                wires = generate_hex_wires_local(
                    self._active_face, self._placement, diameter, gap,
                    self.outfill, self.anchor)
                hexes = self._wires_to_polylines(wires, defl)
                if hexes:
                    sep.addChild(self._line_node(hexes, (0.95, 0.6, 0.1), 2.0))
            except Exception:
                pass

        if sep.getNumChildren() == 0:
            return
        view = Gui.ActiveDocument.ActiveView
        sg = view.getSceneGraph()
        sg.addChild(sep)
        self._preview_node = sep
        self._preview_sg = sg

    def _clear_preview(self, *args):
        self._preview_node = None
        self._preview_sg = None
        _remove_stale_previews()

    def getStandardButtons(self):
        buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        try:
            return int(buttons)
        except TypeError:
            return buttons.value  # PySide6 strict enums

    def reject(self):
        self._clear_preview()
        try:
            if App.ActiveDocument is not None:
                App.ActiveDocument.recompute()
        except Exception:
            pass
        Gui.Control.closeDialog()
        return True

    def accept(self):
        from HexFillCore import generate_hex_wires_local

        doc = App.ActiveDocument
        if doc is None or not getattr(self._source, "Name", None) \
                or doc.getObject(self._source.Name) is None:
            QMessageBox.warning(self.form, "HexFill",
                                "The source sketch is no longer available.")
            self._clear_preview()
            Gui.Control.closeDialog()
            return True

        self._sync_active_face()
        diameter, gap = self._effective_params()
        diameter = self._resolve_diameter(diameter, gap)
        try:
            wires = generate_hex_wires_local(
                self._active_face, self._placement, diameter, gap,
                self.outfill, self.anchor)
        except Exception as exc:
            App.Console.PrintError("HexFill: could not build the grid (%s)\n" % exc)
            wires = []
        if not wires:
            QMessageBox.information(
                self.form, "HexFill",
                "Nothing fits. Reduce Diameter/Gap, try Outfill, Auto or "
                "Auto-fit.")
            return False

        self._clear_preview()
        doc.openTransaction("HexFill grid")
        try:
            _build_hex_sketch(self._source, wires, self._placement)
            try:
                self._source.Visibility = False
            except Exception:
                pass
            doc.commitTransaction()
        except Exception as exc:
            doc.abortTransaction()
            App.Console.PrintError("HexFill: build failed, changes reverted (%s)\n" % exc)
            QMessageBox.critical(self.form, "HexFill",
                                 "Could not create the grid sketch. No changes were made.")
            return False
        doc.recompute()
        App.Console.PrintMessage("HexFill: created %d cells.\n" % len(wires))
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
            "ToolTip": "Creates a grid of honeycombs for any sketch template.",
        }

    @staticmethod
    def _usable(obj):
        """True only for a sketch that has at least one closed contour."""
        if obj is None or not obj.isDerivedFrom("Sketcher::SketchObject"):
            return False
        shape = getattr(obj, "Shape", None)
        if shape is None:
            return False
        try:
            return bool(shape.Faces) or any(w.isClosed() for w in shape.Wires)
        except Exception:
            return False

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        sel = Gui.Selection.getSelection()
        return bool(sel) and self._usable(sel[0])

    def Activated(self):
        from HexFillCore import get_boundary_face, get_source_placement, get_host_shape

        _remove_stale_previews()  # clear any preview orphaned by a previous run
        sel = Gui.Selection.getSelection()
        source = sel[0] if sel else None
        if not self._usable(source):
            QMessageBox.critical(
                Gui.getMainWindow() if hasattr(Gui, "getMainWindow") else None,
                "HexFill",
                "Please select a sketch with a closed contour first.")
            return

        face = get_boundary_face(source)
        if face is None:
            QMessageBox.critical(
                Gui.getMainWindow() if hasattr(Gui, "getMainWindow") else None,
                "HexFill",
                "The selected object has no closed contour to fill.")
            return

        placement = get_source_placement(source, face)
        host_shape = get_host_shape(source)
        panel = HexFillTaskPanel(source, face, placement, host_shape)
        try:
            Gui.Control.showDialog(panel)
        except Exception:
            # A task dialog is probably already open.
            App.Console.PrintError(
                "HexFill: close the current task panel first, then retry.\n")


Gui.addCommand("HexFill_Create", CmdHexFillCreate())
