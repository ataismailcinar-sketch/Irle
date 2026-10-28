# -*- coding: utf-8 -*-
"""
Not (note) komut ve sorguları: oluştur, sil, listele.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from irle.domain.commands import CreateNote, DeleteNote
from irle.domain.events import Notification
from irle.domain.queries import ListNotes

logger = logging.getLogger("irle.handlers.notes")

_DEFAULT_NOTES_FILE = "data/notlar.json"


class NotesHandler:
    """CreateNote, DeleteNote komutlarını ve ListNotes sorgusunu işler."""

    def __init__(self, event_bus: Any, notes_file: str = _DEFAULT_NOTES_FILE) -> None:
        self._bus = event_bus
        self._file = notes_file
        os.makedirs(os.path.dirname(self._file) or ".", exist_ok=True)
        self._notes: list[dict] = self._load()

    # ------------------------------------------------------------------

    def handle_create(self, cmd: CreateNote) -> None:
        text = cmd.text.strip()
        if not text:
            return
        entry = {
            "zaman": datetime.now().isoformat(timespec="seconds"),
            "metin": text,
        }
        self._notes.append(entry)
        self._save()
        logger.info("Not kaydedildi: '%s'", text[:60])
        self._notify(f"Not alındı: {text}")

    def handle_delete(self, cmd: DeleteNote) -> None:
        if not self._notes:
            self._notify("Silinecek not yok.")
            return

        if cmd.mode == "last":
            silinen = self._notes.pop()
            self._save()
            logger.info("Son not silindi: '%s'", silinen.get("metin", "")[:60])
            self._notify("Son not silindi.")
        elif cmd.mode == "all":
            self._notes.clear()
            self._save()
            logger.info("Tüm notlar silindi.")
            self._notify("Tüm notlar silindi.")
        else:
            logger.warning("Bilinmeyen silme modu: %s", cmd.mode)

    def handle_list(self, query: ListNotes) -> list[dict]:
        limit = query.limit or len(self._notes)
        result = self._notes[-limit:]
        logger.debug("Notlar listelendi: %d kayıt.", len(result))

        if result:
            ozet = "; ".join(n["metin"][:40] for n in result[-3:])
            self._notify(f"Notlar: {ozet}")
        else:
            self._notify("Henüz not yok.")
        return result

    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            logger.error("Notlar yüklenemedi: %s", exc)
            return []

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._notes, f, ensure_ascii=False, indent=2)
        except IOError as exc:
            logger.error("Notlar kaydedilemedi: %s", exc)

    def _notify(self, message: str) -> None:
        try:
            self._bus.publish(Notification(title="Notlar", message=message))
        except Exception:
            pass
