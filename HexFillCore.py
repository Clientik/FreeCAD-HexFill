"""Geometry helpers for HexFill (no GUI dependencies)."""

import math
import FreeCAD as App
import Part

TOL = 1e-6


def get_boundary_face(obj):
    """Build a planar face from obj: existing face, closed wire(s) or a circle.

    With several wires the largest one is the outer boundary and the rest are
    treated as holes. Returns None (and logs) when there is no closed contour.
    """
    shape = getattr(obj, "Shape", None)
    if shape is None:
        App.Console.PrintError("HexFill: '%s' has no Shape.\n" % obj.Label)
        return None

    if shape.Faces:
        return shape.Faces[0]

    wires = [w for w in shape.Wires if w.isClosed()]
    if not wires and shape.Edges:
        wires = [Part.Wire(e) for e in shape.Edges if e.isClosed()]

    if not wires:
        App.Console.PrintError("HexFill: '%s' has no closed contour.\n" % obj.Label)
        return None

    try:
        if len(wires) == 1:
            return Part.Face(wires[0])
        wires.sort(key=lambda w: w.BoundBox.DiagonalLength, reverse=True)
        return Part.Face(wires)
    except Exception as exc:
        App.Console.PrintError("HexFill: cannot build face (%s).\n" % exc)
        return None


def _planar_placement(face):
    """Placement mapping local XY onto the plane of a (planar) face."""
    surf = getattr(face, "Surface", None)
    pos = getattr(surf, "Position", None) or face.CenterOfMass
    axis = getattr(surf, "Axis", None)
    if axis is None:
        try:
            axis = face.normalAt(0, 0)
        except Exception:
            axis = App.Vector(0, 0, 1)
    pl = App.Placement()
    pl.Base = App.Vector(pos)
    pl.Rotation = App.Rotation(App.Vector(0, 0, 1), App.Vector(axis))
    return pl


def get_source_placement(obj, face):
    """Local->global placement for the grid.

    A sketch keeps its own placement so the result lines up with it; everything
    else falls back to the face plane.
    """
    if obj is not None and obj.isDerivedFrom("Sketcher::SketchObject"):
        return App.Placement(obj.Placement)
    return _planar_placement(face)


def _flatten(face, placement):
    """Copy of face mapped into the local Z=0 plane."""
    flat = face.copy()
    flat.transformShape(placement.inverse().toMatrix(), True)
    return flat


def auto_parameters(face, placement):
    """Pick a diameter/gap for a stiff but light honeycomb.

    Targets roughly 10 cells across the shorter side with walls about 20% of
    the cell - small cells with substantial walls give good stiffness per
    weight without turning into a solid plate.
    """
    bb = _flatten(face, placement).BoundBox
    min_dim = min(bb.XLength, bb.YLength)
    if min_dim <= 0:
        return 5.0, 1.0
    diameter = max(min_dim / 10.0, 1.0)
    gap = max(0.2 * diameter, 0.6)
    return diameter, gap


def _hex_vertices(cx, cy, r):
    return [App.Vector(cx + r * math.cos(math.radians(60 * i)),
                       cy + r * math.sin(math.radians(60 * i)), 0)
            for i in range(6)]


def _anchor_point(bb, anchor):
    h, v = anchor
    ax = {"left": bb.XMin, "right": bb.XMax}.get(h, (bb.XMin + bb.XMax) / 2.0)
    ay = {"bottom": bb.YMin, "top": bb.YMax}.get(v, (bb.YMin + bb.YMax) / 2.0)
    return ax, ay


def _grid(flat, diameter, gap, anchor):
    """Yield (cx, cy) cell centres covering the boundary's bounding box.

    A cell is pinned at the anchor point and the lattice (flat-top, offset
    columns) grows out from it, with a one-step margin for overhanging cells.
    """
    r = diameter / 2.0
    col_step = 1.5 * r + gap * (math.sqrt(3) / 2)
    row_step = math.sqrt(3) * r + gap
    bb = flat.BoundBox
    ax, ay = _anchor_point(bb, anchor)

    k_min = int(math.floor((bb.XMin - col_step - ax) / col_step))
    k_max = int(math.ceil((bb.XMax + col_step - ax) / col_step))
    m_min = int(math.floor((bb.YMin - row_step - ay) / row_step))
    m_max = int(math.ceil((bb.YMax + row_step - ay) / row_step))

    for k in range(k_min, k_max + 1):
        cx = ax + k * col_step
        y_off = row_step / 2.0 if k % 2 else 0.0
        for m in range(m_min, m_max + 1):
            yield cx, ay + m * row_step + y_off, r


def generate_hex_cells_local(face, placement, diameter, gap,
                             outfill=False, anchor=("center", "center")):
    """Return kept cells as lists of 6 local vertices (used for a fast count).

    outfill False keeps only fully-enclosed cells; True keeps every cell whose
    centre lies inside the boundary.
    """
    if diameter <= 0:
        return []
    flat = _flatten(face, placement)

    def inside(pt):
        try:
            return flat.isInside(pt, TOL, True)
        except Exception:
            return False

    cells = []
    for cx, cy, r in _grid(flat, diameter, gap, anchor):
        verts = _hex_vertices(cx, cy, r)
        keep = inside(App.Vector(cx, cy, 0)) if outfill else all(map(inside, verts))
        if keep:
            cells.append(verts)
    return cells


def generate_hex_wires_local(face, placement, diameter, gap,
                             outfill=False, anchor=("center", "center")):
    """Return local Part.Wire contours for the cells.

    In outfill mode boundary-crossing cells are clipped to the profile (their
    wires follow the outline); interior cells stay whole hexagons.
    """
    if diameter <= 0:
        return []
    flat = _flatten(face, placement)

    def inside(pt):
        try:
            return flat.isInside(pt, TOL, True)
        except Exception:
            return False

    def hex_wire(verts):
        return Part.Wire([Part.LineSegment(verts[i], verts[(i + 1) % 6]).toShape()
                          for i in range(6)])

    wires = []
    for cx, cy, r in _grid(flat, diameter, gap, anchor):
        verts = _hex_vertices(cx, cy, r)
        n_in = sum(inside(v) for v in verts)

        if n_in == 6:
            wires.append(hex_wire(verts))
            continue
        if not outfill:
            continue
        if n_in == 0 and not inside(App.Vector(cx, cy, 0)):
            continue
        try:
            clipped = flat.common(Part.Face(hex_wire(verts)))
        except Exception:
            continue
        wires.extend(f.OuterWire for f in clipped.Faces if f.Area > 1e-9)

    return wires
