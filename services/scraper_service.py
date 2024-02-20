import json
import os
import random
from pathlib import Path

from typing import Any
from nng_sdk.logger import get_logger


class ScraperService:
    logger = get_logger()

    name: str
    path: str

    def __init__(self, name: str):
        self.name = name

        self.path = f"scripts_results/{self.name}/"
        self._make_folders()

    def _make_folders(self):
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    @staticmethod
    def generate_session_name() -> str:
        symbols = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        return "".join(random.choice(symbols) for _ in range(30))

    def get_session_path(self, session_id: str) -> str:
        return self.path + session_id + ".json"

    def save_result(self, session_id: str, result: Any):
        with open(self.get_session_path(session_id), "w", encoding="utf8") as f:
            json.dump(result.to_dict(), f, indent=4, ensure_ascii=False)

    def cleanup(self, session_id: str):
        file = Path(self.get_session_path(session_id))
        if not file.exists():
            return

        file.unlink()
