from datetime import datetime, timezone


def build_sentinel(
    fixture: dict,
    metric_scores: dict,
    failures: list[str],
    action: str | None,
) -> dict:
    return {
        "sentinel_version": "1.0",
        "id": fixture["id"],
        "family": fixture["family"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "metric_scores": metric_scores,
        "failures": failures,
        "action": action,
    }
