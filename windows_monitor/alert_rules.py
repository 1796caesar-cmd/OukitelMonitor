"""Configurable battery-level notifications for Oukitel Monitor Windows.

Only real consecutive observations trigger an alert.  Settings are read by the
worker on each poll; no network calls or UI dependencies live in this module.
"""
from __future__ import annotations


def notification_messages(
    previous: int | None,
    current: int | None,
    *,
    low_enabled: bool = True,
    low_threshold: int = 5,
    high_enabled: bool = True,
    high_threshold: int = 100,
) -> list[str]:
    """Send a notification once when a configured boundary is crossed.

    Low threshold is crossed while discharging; high threshold while charging.
    Repeated identical readings never generate a duplicate notification.
    """
    if previous is None or current is None:
        return []
    if not (0 <= previous <= 100 and 0 <= current <= 100):
        return []
    messages = []
    if low_enabled and 1 <= low_threshold <= 100 and previous > low_threshold >= current:
        messages.append(f"Заряд станції знизився до {low_threshold}% або нижче")
    if high_enabled and 1 <= high_threshold <= 100 and previous < high_threshold <= current:
        if high_threshold == 100:
            messages.append("Станція повністю заряджена (100%)")
        else:
            messages.append(f"Заряд станції досяг {high_threshold}%")
    return messages
