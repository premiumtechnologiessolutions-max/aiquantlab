# No Risk FX integration | read-only Nova exporter

Date: 2026-10-30. Review-only integration from AI Quant Lab V4 to the
canonical No Risk FX XAUUSD research control plane (Draft PR #10).
No live/paper trading and no Oracle deployment.

## Scope
- Read one existing immutable Nova HypothesisRecord from private AQL
  institutional SQLite through SQLite URI read-only mode.
- Validate exact schema; refuse extra fields, duplicate JSON keys,
  nonfinite input, unlocked parameters, Forge/other agent and unknown IDs.
- Export exactly one JSON file in an existing private local folder using
  exclusive create with 0600 POSIX permissions. No overwrite, symlink
  traversal, database mutation, agent-runtime start, or MT5 call.
- Preserves original AQL strategy names and qualitative text. DOES NOT
  equate FX strategies to the canonical Gold backtest implementation.
- All source files remain private. Never commit their original content,
  broker account IDs, data scopes, secrets or market quotes to GitHub.

## Operator commands
From private AI Quant Lab checkout:

    python scripts/export_noriskfx_nova.py --research-db PRIVATE_AIQUANTLAB_SQLITE --hypothesis-id hypothesis_ID --out PRIVATE_DIR/nova_hypothesis.json

Then from the separately installed canonical backtest engine checkout:

    python scripts/import_aiquantlab_hypothesis.py --hypothesis PRIVATE_DIR/nova_hypothesis.json --context PRIVATE_VERIFIED_CONTEXT.json --queue-db PRIVATE_RESEARCH_QUEUE.sqlite3

The canonical consumer starts PAUSED and records only non-authoritative
hypothesis intent. Original dataset and Git commit hashes must be
independently checked by the operator, not hallucinated or guessed.
No strategy P/L, broker fills or future OOS claims are transferred.

## Release boundary
This exporter is a single read-only local operation, not an always-on
agent scheduler or a completed integrated research platform. The
owner's original private AIQuantLab SQLite should be separately tested
on the private machine. Canonical Python research worker and future
Terminal UI remain separate pending acceptance gates.
