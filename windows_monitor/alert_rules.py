"""Battery alert rules for Oukitel Monitor Windows (offline, deterministic).

The previous one-low/one-high settings are migrated automatically. The user
can now save multiple enabled/disabled thresholds per direction.
"""
from __future__ import annotations

from typing import Any


def notification_messages(
    previous: int | None,
    current: int | None,
    *,
    low_enabled: bool = True,
    low_threshold: int = 5,
    high_enabled: bool = True,
    high_threshold: int = 100,
) -> list[str]:
    """Backwards-compatible helper for older versions/tests."""
    if previous is None or current is None:
        return []
    if not (0 <= previous <= 100 and 0 <= current <= 100):
        return []
    messages: list[str] = []
    if low_enabled and 1 <= low_threshold <= 100 and previous > low_threshold >= current:
        messages.append(f"Заряд станції знизився до {low_threshold}% або нижче")
    if high_enabled and 1 <= high_threshold <= 100 and previous < high_threshold <= current:
        messages.append("Станція повністю заряджена (100%)" if high_threshold == 100
                        else f"Заряд станції досяг {high_threshold}%")
    return messages


def load_threshold_rules(settings: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    """Read multiple rules, migrating legacy Windows 1.0/1.1 settings.

    An explicitly empty list means that the user removed every rule. Do not
    recreate a default rule in that case.
    """
    if direction not in ("low", "high"):
        raise ValueError("Unknown notification direction")
    raw = settings.get(f"{direction}_rules")
    if raw is None:
        previous = settings.get(f"{direction}_threshold", 5 if direction == "low" else 100)
        try:
            previous = int(previous)
        except (ValueError, TypeError, OverflowError):
            previous = 5 if direction == "low" else 100
        previous = max(1, min(100, previous))
        enabled = bool(settings.get(f"notify_{direction}", settings.get("alerts", True)))
        return [{"threshold": previous, "enabled": enabled}]
    if not isinstance(raw, list):
        return []
    result = []
    seen = set()
    for rule in raw:
        if not isinstance(rule, dict):
            continue
        try:
            threshold = int(rule.get("threshold"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not 1 <= threshold <= 100 or threshold in seen:
            continue
        seen.add(threshold)
        result.append({"threshold": threshold, "enabled": rule.get("enabled", True) is True})
    return result


def multi_notification_messages(
    previous: int | None,
    current: int | None,
    low_rules: list[dict[str, Any]],
    high_rules: list[dict[str, Any]],
) -> list[str]:
    """Notify for every crossed enabled threshold, including skipped levels.

    'Below 90%' means strictly below 90, e.g. 92->88 or 90->88.
    'Reached 95%' means at least 95, e.g. 88->97.
    No new measurement (or unchanged value) means no message. Initial sample
    has no previous reading, so it cannot produce an artificial alert.
    """
    if previous is None or current is None:
        return []
    if not (0 <= previous <= 100 and 0 <= current <= 100) or previous == current:
        return []
    if current < previous:
        rules = load_threshold_rules({"low_rules": low_rules}, "low")
        thresholds = sorted((r["threshold"] for r in rules if r["enabled"]), reverse=True)
        return [f"Заряд нижче {threshold}% — зараз {current}%"
                for threshold in thresholds if previous >= threshold > current]
    rules = load_threshold_rules({"high_rules": high_rules}, "high")
    thresholds = sorted(r["threshold"] for r in rules if r["enabled"])
    return [f"Заряд досяг {threshold}% — зараз {current}%"
            for threshold in thresholds if previous < threshold <= current]
