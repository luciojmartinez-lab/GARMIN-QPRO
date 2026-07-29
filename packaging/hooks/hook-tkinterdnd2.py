"""Bundle tkinterdnd2's Tcl/Tk resources with PyInstaller."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("tkinterdnd2")
hiddenimports = collect_submodules("tkinterdnd2")
