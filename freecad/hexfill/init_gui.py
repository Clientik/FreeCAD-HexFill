"""GUI init: attach the HexFill command to the Sketcher workbench."""

import FreeCADGui as Gui

from freecad.hexfill import HexFillCommands  # noqa: F401  (registers HexFill_Create)


class HexFillManipulator:
    """Adds the HexFill command to the Sketcher workbench toolbar and menu.

    Manipulators run per workbench; the entries are emitted only when the
    workbench being set up is confirmed to be Sketcher.
    """

    TARGET_WB = "SketcherWorkbench"

    def _wanted(self):
        import FreeCADGui as Gui
        try:
            active = Gui.activeWorkbench()
            for name, wb in Gui.listWorkbenches().items():
                if wb is active:
                    return name == self.TARGET_WB
        except Exception:
            pass
        return False

    def modifyToolBars(self):
        if not self._wanted():
            return []
        return [{"append": "HexFill_Create", "toolBar": "Structure"}]

    def modifyMenuBar(self):
        if not self._wanted():
            return []
        return [{"insert": "HexFill_Create", "menuItem": "Std_DlgCustomize", "after": "1"}]


if getattr(Gui, "HexFillManipulator", None) is None:
    Gui.HexFillManipulator = HexFillManipulator()
    Gui.addWorkbenchManipulator(Gui.HexFillManipulator)
