"""Run and normalized-ledger index API payload builders."""

from __future__ import annotations

from typing import Any, Dict, Optional


def runs_payload(context: Any) -> Dict[str, Any]:
    items = context.harness.store.runs()
    counts = {
        item.get("run_id", ""): context.harness.store.normalized_index_counts(
            item.get("run_id")
        )
        for item in items
    }
    return {
        "current_run_id": context.run_id,
        "count": len(items),
        "items": [
            {
                **item,
                "is_current": item.get("run_id") == context.run_id,
                "index_counts": counts.get(item.get("run_id", ""), {}),
            }
            for item in items
        ],
    }


def ledger_index_payload(
    context: Any,
    index_name: str,
    run_id: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    resolved_run_id = run_id or context.run_id
    items = context.harness.store.normalized_index_rows(
        index_name,
        run_id=resolved_run_id,
        limit=limit,
    )
    return {
        "index_name": index_name,
        "run_id": resolved_run_id,
        "count": len(items),
        "items": items,
    }
