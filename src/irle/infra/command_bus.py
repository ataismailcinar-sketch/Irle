# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / COMMAND BUS — Typed Command Yönlendiricisi
=============================================================================
Her typed Command nesnesi için kayıtlı handler'ı bulur ve çağırır.

Kullanım:
    bus = CommandBus(event_bus)
    bus.register(ShutdownComputer, system_handler.handle_shutdown)
    bus.dispatch(ShutdownComputer(delay_seconds=60))
=============================================================================
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from irle.domain.events import CommandCompleted, CommandFailed, Notification

logger = logging.getLogger("irle.infra.command_bus")


class CommandBus:
    """
    Typed Command → Handler yönlendirici.

    Thread-safe. Dispatch işlemi caller thread'inde senkron çalışır;
    handler'ın kendisi async/thread davranışını yönetmekten sorumludur.
    """

    def __init__(self, event_bus: Any) -> None:
        """
        Args:
            event_bus: TypedEventBus örneği — CommandCompleted/CommandFailed
                       eventlerini yayınlamak için kullanılır.
        """
        self._event_bus = event_bus
        self._handlers: dict[type, Callable] = {}

    # ------------------------------------------------------------------
    # Kayıt
    # ------------------------------------------------------------------

    def register(self, command_type: type, handler: Callable) -> None:
        """
        Bir Command tipi için handler kaydeder.

        Args:
            command_type: Command alt sınıfı (ör. ShutdownComputer)
            handler:      Tek argüman alan callable (command_instance)
        """
        if command_type in self._handlers:
            logger.warning(
                "Handler yeniden kaydediliyor: %s → %s",
                command_type.__name__,
                handler,
            )
        self._handlers[command_type] = handler
        logger.debug("Handler kayıt: %s → %s", command_type.__name__, handler)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, command: Any) -> Any:
        """
        Command nesnesini ilgili handler'a iletir.

        Kayıtlı handler yoksa veya handler exception fırlatırsa:
        - Hata loglanır
        - CommandFailed eventi yayınlanır (sistem çökmez)

        Returns:
            Handler'ın dönüş değeri (genellikle None).
        """
        command_type = type(command)
        handler = self._handlers.get(command_type)

        if handler is None:
            logger.warning(
                "Kayıtlı handler bulunamadı: %s — komut yoksayıldı.",
                command_type.__name__,
            )
            try:
                self._event_bus.publish(
                    CommandFailed(
                        command_type=command_type.__name__,
                        error=f"Handler kayıtlı değil: {command_type.__name__}",
                    )
                )
            except Exception:
                pass
            return None

        try:
            logger.debug("Dispatch: %s", command_type.__name__)
            result = handler(command)
            try:
                self._event_bus.publish(
                    CommandCompleted(command_type=command_type.__name__)
                )
            except Exception:
                pass
            return result

        except Exception as exc:
            # Beklenen kullanıcı-seviyesi hatalar (bulunamadı, geçersiz değer, eksik kütüphane)
            # için traceback basma; gerçek hatalarda bas.
            beklenen = isinstance(exc, (ValueError, FileNotFoundError, PermissionError, RuntimeError))
            logger.error(
                "Handler hatası [%s]: %s",
                command_type.__name__,
                exc,
                exc_info=not beklenen,
            )
            try:
                self._event_bus.publish(
                    CommandFailed(
                        command_type=command_type.__name__,
                        error=str(exc),
                    )
                )
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # İntrospeksiyon
    # ------------------------------------------------------------------

    def registered_commands(self) -> list[str]:
        """Kayıtlı tüm command tiplerinin adlarını döndürür."""
        return [t.__name__ for t in self._handlers]
