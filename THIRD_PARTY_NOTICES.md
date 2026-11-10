# Third-party notices

- `app/static/geometry.js` embeds polygon-clipping 0.15.7 (MIT), followed by this project's geometry helpers. The upstream distribution includes its bundled dependencies; preserve the complete [upstream license](third_party/polygon-clipping-LICENSE.md). Project: https://github.com/mfogel/polygon-clipping
- Python, Tcl/Tk, NumPy, Pillow, tifffile, and pycocotools are runtime dependencies under their respective licenses. Their files and notices collected by PyInstaller remain in the Windows package; do not remove `_internal`.
- PyInstaller is the build tool (GPL with a distribution exception for bundled applications). It does not change the license of this project's own code. See https://pyinstaller.org/en/stable/license.html

EarthMiss/EarthM3 names describe compatible directory conventions only. No original images, labels, or dataset license rights are bundled. The demonstration images are generated locally from geometric primitives by `examples/generate_demo.py` and are not genuine SAR observations.
