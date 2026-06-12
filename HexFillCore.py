"""Geometry helpers for HexFill (no GUI dependencies)."""

import math
import FreeCAD as App
import Part

TOL = 1e-6


def get_boundary_face(obj):
    """Build the planar boundary from obj.

    Returns a shape that may hold several faces - one per closed region in the
    sketch - with nested contours correctly turned into holes. Disjoint regions
    are each filled independently. Returns None (and logs) when there is no
    closed contour.
    """
    shape = getattr(obj, "Shape", None)
    if shape is None:
        App.Console.PrintError("HexFill: '%s' has no Shape.\n" % obj.Label)
        return None

    if shape.Faces:
        return shape if len(shape.Faces) > 1 else shape.Faces[0]

    wires = [w for w in shape.Wires if w.isClosed()]
    if not wires and shape.Edges:
        wires = [Part.Wire(e) for e in shape.Edges if e.isClosed()]

    if not wires:
        App.Console.PrintError("HexFill: '%s' has no closed contour.\n" % obj.Label)
        return None

    if len(wires) == 1:
        try:
            return Part.Face(wires[0])
        except Exception as exc:
            App.Console.PrintError("HexFill: cannot build face (%s).\n" % exc)
            return None

    # Several wires: let the Bullseye face maker sort out nesting (holes) and
    # separate regions on its own, instead of assuming one outer + holes.
    try:
        return Part.makeFace(wires, "Part::FaceMakerBullseye")
    except Exception:
        try:
            wires.sort(key=lambda w: w.BoundBox.DiagonalLength, reverse=True)
            return Part.Face(wires)
        except Exception as exc:
            App.Console.PrintError("HexFill: cannot build face (%s).\n" % exc)
            return None


def get_host_shape(source):
    """The solid the sketch sits on, used to subtract existing cutouts.

    Prefers the whole Body's final solid so every hole counts (including ones
    cut after the attached feature), then falls back to the attached object's
    solid. Returns None when nothing solid is found.
    """
    try:
        body = source.getParentGeoFeatureGroup()
        if body is not None:
            shape = getattr(body, "Shape", None)
            if shape is not None and shape.Solids:
                return shape
    except Exception:
        pass
    support = getattr(source, "AttachmentSupport", None) \
        or getattr(source, "Support", None)
    for obj, _subs in (support or ()):
        shape = getattr(obj, "Shape", None)
        if shape is not None and shape.Solids:
            return shape
    return None


def host_material_region(host_shape, placement):
    """Material cross-section of the host solid at the sketch plane.

    Returns a face whose outer wire is the part's physical edge and whose holes
    are every cutout/through-hole crossing the plane. None if unavailable.
    """
    if host_shape is None:
        return None
    try:
        size = host_shape.BoundBox.DiagonalLength + 10.0
        plane = Part.makePlane(2 * size, 2 * size, App.Vector(-size, -size, 0))
        plane.Placement = App.Placement(placement)
        region = plane.common(host_shape)
        if region.Faces:
            return region
    except Exception:
        pass
    return None


def subtract_host_holes(face, host_shape):
    """Intersect *face* with *host_shape* so existing cutouts become holes.

    Fallback for sketches not backed by host_material_region: any through-hole
    crossing the sketch plane is removed.
    """
    if face is None or host_shape is None:
        return face
    try:
        common = face.common(host_shape)
        if common.Faces:
            return common
    except Exception:
        pass
    return face


def _part_outline(host_region):
    """Solid face of the whole part outline (cutouts filled in)."""
    outlines = []
    for f in host_region.Faces:
        try:
            outlines.append(Part.Face(f.OuterWire))
        except Exception:
            pass
    if not outlines:
        return None
    panel = outlines[0]
    if len(outlines) > 1:
        panel = panel.fuse(outlines[1:])
    return panel


def _offset_out(faces, margin):
    """Grow each face outward by *margin*; robust to boolean-derived geometry."""
    grown = []
    for f in faces:
        try:
            grown.extend(f.makeOffset2D(abs(margin)).Faces)
        except Exception:
            try:
                grown.extend(f.removeSplitter().makeOffset2D(abs(margin)).Faces)
            except Exception:
                pass
    return grown


def apply_clearance(fill, host_region, margin, mode="contour"):
    """Keep the honeycomb *margin* away from the chosen boundaries.

    Cutouts always get a clearance ring. *mode* adds, in addition:
      "contour" - the dividing contour (fill stops short of it, reaches the edge)
      "edge"    - the part's physical edge (fill stops short of it, reaches the contour)
      "both"    - both the contour and the edge

    The relevant keep-out areas are grown outward by *margin* and cut from
    *fill*. Only outward offsets of solid faces are used, so it is robust on
    boolean geometry (circles included) - no per-hole special cases.
    """
    if fill is None or host_region is None or margin <= 0:
        return fill
    try:
        panel = _part_outline(host_region)
        if panel is None:
            return fill
        # Grow-based clearance: cutouts (always) and the opposite side of the
        # contour, cut from the fill.
        keepout = []
        try:
            keepout.extend(panel.cut(host_region).Faces)   # cutouts
        except Exception:
            pass
        if mode in ("contour", "both"):
            try:
                keepout.extend(host_region.cut(fill).Faces)  # other side
            except Exception:
                pass
        grown = _offset_out(keepout, margin)
        if grown:
            cut = fill.cut(Part.makeCompound(grown))
            if cut.Faces:
                fill = cut
        # Edge clearance: pull the fill in from the part's physical edge by
        # shrinking the part outline and intersecting.
        if mode in ("edge", "both"):
            try:
                shrunk = panel.makeOffset2D(-abs(margin))
                inset = fill.common(shrunk)
                if inset.Faces:
                    fill = inset
            except Exception:
                pass
        return fill
    except Exception as exc:
        App.Console.PrintWarning("HexFill: margin could not be applied (%s)\n" % exc)
    return fill


def _planar_placement(face):
    """Placement mapping local XY onto the plane of a (planar) face."""
    if not getattr(face, "Surface", None) and face.Faces:
        face = face.Faces[0]  # a compound of regions: use the first one's plane
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


# Upper bound on grid positions, so a tiny diameter on a big sketch can never
# lock up FreeCAD. estimate_grid_positions() lets callers warn before running.
MAX_CELLS = 20000


def _grid_steps(diameter, gap):
    r = max(diameter, 1e-6) / 2.0
    col_step = 1.5 * r + gap * (math.sqrt(3) / 2)
    row_step = math.sqrt(3) * r + gap
    return r, max(col_step, 1e-6), max(row_step, 1e-6)


def estimate_grid_positions(face, placement, diameter, gap):
    """Rough number of lattice positions for the given settings (0 if invalid)."""
    if diameter <= 0:
        return 0
    try:
        bb = _flatten(face, placement).BoundBox
        _, col_step, row_step = _grid_steps(diameter, gap)
        nk = (bb.XLength + 2 * col_step) / col_step + 1
        nm = (bb.YLength + 2 * row_step) / row_step + 1
        return int(nk * nm)
    except Exception:
        return 0


def _grid(flat, diameter, gap, anchor):
    """Yield (cx, cy, r) cell centres covering the boundary's bounding box.

    A cell is pinned at the anchor point and the lattice (flat-top, offset
    columns) grows out from it, with a one-step margin for overhanging cells.
    Stops once MAX_CELLS positions are produced, as a safety valve.
    """
    r, col_step, row_step = _grid_steps(diameter, gap)
    bb = flat.BoundBox
    ax, ay = _anchor_point(bb, anchor)

    k_min = int(math.floor((bb.XMin - col_step - ax) / col_step))
    k_max = int(math.ceil((bb.XMax + col_step - ax) / col_step))
    m_min = int(math.floor((bb.YMin - row_step - ay) / row_step))
    m_max = int(math.ceil((bb.YMax + row_step - ay) / row_step))

    produced = 0
    for k in range(k_min, k_max + 1):
        cx = ax + k * col_step
        y_off = row_step / 2.0 if k % 2 else 0.0
        for m in range(m_min, m_max + 1):
            produced += 1
            if produced > MAX_CELLS:
                return
            yield cx, ay + m * row_step + y_off, r


def _make_inside_tests(flat):
    """Return (inside_any, fully_in_one) point tests for every region of flat.

    flat may hold several disjoint faces (one per closed region). A cell counts
    as fully enclosed only when all its vertices fall inside the *same* face, so
    a hexagon can never bridge the gap between two separate regions.
    """
    faces = flat.Faces

    def inside_any(pt):
        for f in faces:
            try:
                if f.isInside(pt, TOL, True):
                    return True
            except Exception:
                pass
        return False

    def fully_in_one(verts):
        for f in faces:
            try:
                if all(f.isInside(v, TOL, True) for v in verts):
                    return True
            except Exception:
                pass
        return False

    return inside_any, fully_in_one


def generate_hex_cells_local(face, placement, diameter, gap,
                             outfill=False, anchor=("center", "center")):
    """Return kept cells as lists of 6 local vertices (used for a fast count).

    outfill False keeps only fully-enclosed cells; True keeps every cell whose
    centre lies inside the boundary.
    """
    if diameter <= 0 or face is None:
        return []
    try:
        flat = _flatten(face, placement)
    except Exception:
        return []
    inside_any, fully_in_one = _make_inside_tests(flat)

    cells = []
    for cx, cy, r in _grid(flat, diameter, gap, anchor):
        verts = _hex_vertices(cx, cy, r)
        keep = inside_any(App.Vector(cx, cy, 0)) if outfill else fully_in_one(verts)
        if keep:
            cells.append(verts)
    return cells


def generate_hex_wires_local(face, placement, diameter, gap,
                             outfill=False, anchor=("center", "center")):
    """Return local Part.Wire contours for the cells.

    In outfill mode boundary-crossing cells are clipped to the profile (their
    wires follow the outline); interior cells stay whole hexagons.
    """
    if diameter <= 0 or face is None:
        return []
    try:
        flat = _flatten(face, placement)
    except Exception:
        return []
    inside_any, fully_in_one = _make_inside_tests(flat)

    def hex_wire(verts):
        return Part.Wire([Part.LineSegment(verts[i], verts[(i + 1) % 6]).toShape()
                          for i in range(6)])

    wires = []
    for cx, cy, r in _grid(flat, diameter, gap, anchor):
        verts = _hex_vertices(cx, cy, r)

        if fully_in_one(verts):
            wires.append(hex_wire(verts))
            continue
        if not outfill:
            continue
        touches = any(inside_any(v) for v in verts) or inside_any(App.Vector(cx, cy, 0))
        if not touches:
            continue
        try:
            clipped = flat.common(Part.Face(hex_wire(verts)))
        except Exception:
            continue
        wires.extend(f.OuterWire for f in clipped.Faces if f.Area > 1e-9)

    return wires
