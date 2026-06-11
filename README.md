# HexFill

A small FreeCAD add-on that fills a sketch profile with a hexagonal honeycomb
pattern and produces a new sketch you can Pad or Pocket.

![icon](Resources/icons/HexFill.svg)

## Features

- Works on any closed sketch profile (rectangle, circle, arbitrary contour).
- **Manual** mode (set cell diameter and wall gap) or **Auto** mode that sizes
  a stiff, light honeycomb from the profile.
- **Outfill** option to trim the border cells to the outline and fill to the edge.
- 3×3 **anchor** selector to control where the lattice starts.
- Live 3D preview while you tune the parameters.
- Output is a plain Sketch, ready for PartDesign **Pad** / **Pocket**.

## Installation

### Addon Manager (recommended once published)

`Tools → Addon manager → HexFill → Install`.

### Manual

Copy the `HexFill` folder into your FreeCAD `Mod` directory and restart:

| OS | Path |
|----|------|
| Windows | `%APPDATA%\FreeCAD\Mod\` |
| Linux | `~/.local/share/FreeCAD/Mod/` |
| macOS | `~/Library/Application Support/FreeCAD/Mod/` |

## Usage

1. Create and (optionally) Pad a sketch.
2. Select the sketch in the tree.
3. Run **HexFill** (Sketcher toolbar, or `Tools` menu).
4. Set the parameters in the task panel and press OK.
5. Select the generated `HexGrid` sketch and apply **Pocket** / **Pad**.

## Requirements

FreeCAD 0.21 or newer (Python 3, PySide2 or PySide6).

## License

MIT — see [LICENSE](LICENSE).
