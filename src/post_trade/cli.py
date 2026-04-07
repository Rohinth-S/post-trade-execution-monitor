"""Import JSON order events and replay any ledger cutoff."""

import argparse
from datetime import datetime
import json
from pathlib import Path

from .artifacts import write_text_atomic

from . import __version__
from .artifacts import require_distinct_paths

from .events import AlertLimits, ExecutionBatch
from .execution import build_execution_report
from .fixtures import demo_batch
from .storage import LedgerStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile order and fill events and export an execution report")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="normalized order and fill JSON")
    source.add_argument("--seed-demo", action="store_true", help="insert the built-in dataset into the selected ledger")
    parser.add_argument("--db", type=Path, help="durable SQLite ledger")
    parser.add_argument("--as-of", type=datetime.fromisoformat, help="ISO-8601 replay cutoff with timezone")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--slippage-bps", type=float, default=40)
    parser.add_argument("--latency-ms", type=float, default=1_000)
    parser.add_argument("--missing-after-ms", type=float, default=5_000)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    try:
        require_distinct_paths(
            input_file=args.input,
            ledger=args.db,
            report=args.output,
        )
        batch = ExecutionBatch.model_validate_json(args.input.read_bytes()) if args.input else None
        if args.seed_demo or (args.db is None and batch is None):
            batch = demo_batch()
        if args.db:
            store = LedgerStore(args.db)
            if batch:
                store.ingest(batch)
            batch = store.snapshot(args.as_of)
        limits = AlertLimits(
            slippage_bps=args.slippage_bps, latency_ms=args.latency_ms, missing_after_ms=args.missing_after_ms,
        )
        report = build_execution_report(batch, as_of=args.as_of, limits=limits)
        report["producer"] = {"name": "post-trade-execution-monitor", "version": __version__, "format_version": 1}
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            write_text_atomic(args.output, payload)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(payload, end="")


if __name__ == "__main__":
    main()
