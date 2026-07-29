from typing import Any
from . import services


class ManualImportParser:
    def __init__(self, workbook: Any):
        self.workbook = workbook

    def parse(self):
        return {}
