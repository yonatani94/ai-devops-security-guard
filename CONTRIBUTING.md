# Contributing

Use Python 3.12+ and uv. Run `uv sync --locked`, then `uv run pytest`,
`uv run ruff check .`, and `uv run ruff format --check .`.

Keep changes small and explain the supported resource shape, risk semantics, and
coverage limitations of every new rule. Add synthetic positive, negative, malformed,
and unknown-value cases. Findings need stable rule IDs and resolvable evidence paths.

Do not broaden a model capability to solve an inference problem. Adjust the data
contract, preserve application-owned permissions, and test the denied path. Do not
log arbitrary arguments, input values, provider messages, or exception contents.

For AI changes, retain deterministic fake inference in offline CI. Real-provider
evaluations must be opt-in and record the model, input digest, decision, and tool
audit. Do not silently substitute fake output when real inference fails.

Never commit reviewer private keys or real infrastructure input. Media and checked-in
demo evidence must come from the synthetic examples and be labeled as a replay.
