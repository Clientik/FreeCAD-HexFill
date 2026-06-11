"""GUI init: attach the HexFill command to the Sketcher workbench."""

import FreeCADGui as Gui

import HexFillCommands  # noqa: F401  (registers HexFill_Create)


class HexFillManipulator:
    """Adds HexFill to the Sketcher workbench toolbar and menu.

    Manipulators run per workbench, so the entries are only emitted while
    Sketcher is being set up (or when the workbench can't be identified, so the
    command is never lost). Names are resolved inside the methods because
    InitGui.py runs with separate globals/locals.
    """

    TARGET_WB = "SketcherWorkbench"

    def _wanted(self):
        import FreeCADGui as Gui
        name = ""
        try:
            active = Gui.activeWorkbench()
            for wb_name, wb in Gui.listWorkbenches().items():
                if wb is active:
                    name = wb_name
                    break
        except Exception:
            pass
        return name in (self.TARGET_WB, "")

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

# Re-apply to the workbench that was already active at startup.
try:
    Gui.activeWorkbench().reloadActive()
except Exception:
    pass
