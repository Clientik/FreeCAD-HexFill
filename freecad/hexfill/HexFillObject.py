"""Compatibility shim.

Older versions stored the result as a parametric Part::FeaturePython whose
proxy lived here. The current command builds a plain Sketch instead, but these
classes are kept so documents saved with the old version still open.
"""

import os
import FreeCAD as App

try:
    import Part
except Exception:
    Part = None


class HexFill:
    def __init__(self, obj):
        obj.Proxy = self
        props = obj.PropertiesList
        if "Source" not in props:
            obj.addProperty("App::PropertyXLink", "Source", "HexFill", "Source")
        if "Diameter" not in props:
            obj.addProperty("App::PropertyLength", "Diameter", "HexFill", "Diameter")
            obj.Diameter = 5.0
        if "Gap" not in props:
            obj.addProperty("App::PropertyLength", "Gap", "HexFill", "Gap")
            obj.Gap = 1.0

    def execute(self, obj):
        if Part is not None and not getattr(obj, "Shape", None):
            obj.Shape = Part.Shape()

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ViewProviderHexFill:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        root = os.path.join(os.path.dirname(__file__), "..", "..")
        return os.path.normpath(
            os.path.join(root, "Resources", "Icons", "HexFill.svg"))

    def attach(self, vobj):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None
