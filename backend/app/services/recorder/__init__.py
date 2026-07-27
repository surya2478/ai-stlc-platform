"""UI-019 Live Recorder services.

`context` is the only module that reads the database for evaluation purposes;
`steps`, `summary` and `ir_emitter` are pure functions over what it loaded.
The write-side modules (`mapping`, `checkpoints`, `segments`, `bindings`,
`notes`) each own one contract section, and `lifecycle` orchestrates stop
finalization and IR emission across them.
"""
