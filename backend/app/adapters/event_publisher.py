"""
Event Publisher Adapter.
Enables services to publish real-time notifications strictly AFTER database transactions commit.
Provides an integration hook for the backend lead's WebSocket manager in main.py.
"""
import logging
from typing import Callable, List, Dict, Any

logger = logging.getLogger("smart_recycling.event_publisher")

# Registered listeners (e.g. WebSocket broadcast handlers)
_listeners: List[Callable[[str, Dict[str, Any]], Any]] = []


def register_event_listener(listener: Callable[[str, Dict[str, Any]], Any]) -> None:
    """
    Registers a listener to be called when events are published.
    Example:
        register_event_listener(lambda event_type, payload: websocket_manager.broadcast(...))
    """
    if listener not in _listeners:
        _listeners.append(listener)
        logger.info(f"Registered new event listener: {listener}")


def unregister_event_listener(listener: Callable[[str, Dict[str, Any]], Any]) -> None:
    if listener in _listeners:
        _listeners.remove(listener)


def clear_event_listeners() -> None:
    """Clears all listeners (useful in testing)."""
    _listeners.clear()


def publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Publishes an event to all registered listeners.
    Must be called AFTER database transaction has successfully committed.
    Exceptions in individual listeners are logged and suppressed so failure to broadcast
    never disrupts application logic or client responses.
    """
    logger.info(f"Publishing event [{event_type}] with payload keys: {list(payload.keys())}")
    for listener in _listeners:
        try:
            listener(event_type, payload)
        except Exception as e:
            logger.warning(f"Error in event listener {listener}: {e}", exc_info=False)
