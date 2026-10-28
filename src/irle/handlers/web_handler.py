# -*- coding: utf-8 -*-
"""
Web arama komutunu işler.
"""

from __future__ import annotations

import logging
import urllib.parse
import webbrowser
from typing import Any

from irle.domain.commands import SearchWeb

logger = logging.getLogger("irle.handlers.web")


class WebHandler:
    """SearchWeb komutunu işler."""

    def __init__(self, event_bus: Any) -> None:
        self._bus = event_bus

    def handle_search(self, cmd: SearchWeb) -> None:
        query = cmd.query
        logger.info("Web araması yapılıyor: %r", query)
        try:
            # Query'i url-encode et
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded_query}"
            webbrowser.open(url)
        except Exception as exc:
            logger.error("Web araması başarısız: %s", exc)
