"""Bundle garminconnect package metadata for frozen diagnostics."""

from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("garminconnect")
