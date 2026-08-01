"""Evidence resolution, masking and integrity (Wave 3 / P0-06, AUT-014).

`views.py` documented a "masked download endpoint" that did not exist: the
command center returned evidence metadata and the viewer linked to nothing. This
module is that endpoint's service half.

Three responsibilities, deliberately together:

**Integrity.** A stored path proves a file existed once, not that the file
served later is the one the run produced. Size and SHA-256 are recorded at
capture and re-verified at serve time; a mismatch is reported rather than
streamed, because silently serving altered evidence is worse than serving none.

**Masking.** Console and network captures are the artifacts most likely to carry
a bearer token or a customer identifier, and they are also the only ones a text
pass can do anything about. They go through `mask_text`/`mask_payload` and are
marked `masked`.

**Policy.** Screenshots, video and traces cannot be masked by any text pass.
Pretending otherwise would be the same defect the review found elsewhere — a
label standing in for the thing it names. They are marked `not_maskable` and
serving them is a configuration decision, defaulting to permitted outside
production, exactly like the runner policy in `automation_runner/policy.py`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.models.execution_command_center import ExecutionRunEvidence

# Artifacts a text pass can rewrite. Everything else is binary.
_MASKABLE_TYPES = frozenset({"console", "network", "api", "log", "database", "event"})

_CONTENT_TYPE_BY_EVIDENCE = {
    "screenshot": "image/png",
    "video": "video/webm",
    "trace": "application/zip",
    "log": "text/plain; charset=utf-8",
    "console": "application/json",
    "network": "application/json",
    "api": "application/json",
    "database": "application/json",
    "dom": "text/html; charset=utf-8",
    "accessibility": "application/json",
    "event": "application/json",
}

REDACTED = "«redacted»"

# Regex masking is a floor, not a guarantee — the review says so and it is worth
# repeating here, because the risk is that a passing mask reads as proof of
# safety. These catch the shapes that actually recur in Playwright console and
# network captures. Ordering matters: the specific key=value forms run before
# the bare-token rules so a matched secret is not partly consumed first.
_MASK_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer <token> / Basic <blob>
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}"), r"\1 " + REDACTED),
    # token=..., api_key: "...", "password":"..." — query strings, headers, JSON
    (
        re.compile(
            r"(?i)\b(token|api[_-]?key|apikey|secret|password|passwd|pwd|authorization|"
            r"auth|session[_-]?id|access[_-]?token|refresh[_-]?token|client[_-]?secret)"
            r"(\"?\s*[:=]\s*\"?)([^\"&\s,}]{4,})"
        ),
        lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}",
    ),
    # JWTs anywhere, including inside URLs
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+"), REDACTED),
    # Email addresses — customer identifiers in a telecom regression
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), REDACTED),
    # 13-19 digit runs: PAN/IMEI/ICCID shapes. Deliberately not 10-12, which
    # would swallow ordinary order ids and timestamps.
    (re.compile(r"\b\d{13,19}\b"), REDACTED),
)


def mask_text(value: str) -> tuple[str, int]:
    """Apply every rule. Returns the masked text and how many rules matched."""
    hits = 0
    for pattern, replacement in _MASK_RULES:
        value, count = pattern.subn(replacement, value)
        hits += count
    return value, hits


def mask_payload(payload: Any) -> tuple[Any, int]:
    """Walk a JSON structure masking every string leaf.

    Keys are left alone: a key is a field name, and rewriting it would corrupt
    the structure without protecting anything.
    """
    hits = 0
    if isinstance(payload, str):
        return mask_text(payload)
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            out[key], n = mask_payload(value)
            hits += n
        return out, hits
    if isinstance(payload, list):
        out_list = []
        for value in payload:
            masked, n = mask_payload(value)
            out_list.append(masked)
            hits += n
        return out_list, hits
    return payload, 0


def content_type_for(evidence_type: str) -> str:
    return _CONTENT_TYPE_BY_EVIDENCE.get(evidence_type, "application/octet-stream")


def is_maskable(evidence_type: str) -> bool:
    return evidence_type in _MASKABLE_TYPES


def unmasked_serving_permitted(settings: Settings | None = None) -> bool:
    """Whether binary evidence may be downloaded at all.

    Same shape as the runner policy: an explicit setting wins, otherwise
    production refuses. A trace or screenshot can contain anything that was on
    screen, and there is no pass that makes it safe.
    """
    cfg = settings or get_settings()
    if cfg.automation_evidence_allow_unmasked is not None:
        return cfg.automation_evidence_allow_unmasked
    return cfg.app_env != "production"


def record_artifact_facts(row: ExecutionRunEvidence) -> None:
    """Stamp size, checksum, content type and redaction state at capture time.

    Called while the run is still executing, which is the only moment the bytes
    are known to be the bytes the run produced.
    """
    row.content_type = content_type_for(row.evidence_type)

    if row.file_path:
        try:
            path = Path(row.file_path)
            row.size_bytes = path.stat().st_size
            digest = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            row.checksum_sha256 = digest.hexdigest()
        except OSError:
            # The artifact vanished between the runner writing it and this call.
            # Leaving the facts NULL is honest; the download endpoint reports a
            # missing artifact rather than serving something unverified.
            row.size_bytes = None
            row.checksum_sha256 = None
    elif row.payload is not None:
        encoded = json.dumps(row.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        row.size_bytes = len(encoded)
        row.checksum_sha256 = hashlib.sha256(encoded).hexdigest()

    # Masking happens on the way out, not on the way in: the stored artifact
    # stays byte-identical to what the run produced, so the checksum keeps
    # meaning something.
    row.redaction_state = "pending" if is_maskable(row.evidence_type) else "not_maskable"
    row.sanitized = False


class EvidenceError(Exception):
    """Resolution failed in a way the endpoint should report, not raise 500 on."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True)
class ResolvedEvidence:
    content: bytes
    content_type: str
    filename: str
    masked: bool
    mask_hits: int
    checksum_sha256: str | None
    integrity_verified: bool


def _within_storage_root(path: Path, settings: Settings) -> bool:
    root = os.path.realpath(settings.file_storage_path)
    real = os.path.realpath(str(path))
    return real == root or real.startswith(root + os.sep)


def resolve(
    row: ExecutionRunEvidence, *, settings: Settings | None = None
) -> ResolvedEvidence:
    """Produce the bytes to serve, or raise EvidenceError explaining why not.

    Mutates `row` to record the masking outcome; the caller commits.
    """
    cfg = settings or get_settings()

    if row.status != "captured":
        raise EvidenceError(
            409,
            row.unavailable_reason
            or f"This evidence is '{row.status}', so there is no content to download.",
        )

    # ── JSON payload evidence ────────────────────────────────────────────────
    if row.payload is not None:
        masked_payload, hits = mask_payload(row.payload)
        row.redaction_state = "masked"
        row.sanitized = True
        return ResolvedEvidence(
            content=json.dumps(masked_payload, indent=2).encode("utf-8"),
            content_type="application/json",
            filename=f"{row.evidence_type}-{row.id}.json",
            masked=True,
            mask_hits=hits,
            checksum_sha256=row.checksum_sha256,
            # The checksum covers the stored bytes; what is served here is the
            # masked rendering, so it deliberately does not match and is not
            # claimed to.
            integrity_verified=False,
        )

    if not row.file_path:
        raise EvidenceError(410, "This evidence row records no artifact to download.")

    path = Path(row.file_path)
    if not _within_storage_root(path, cfg):
        # Defence in depth: a path that escaped the storage root is a bug or an
        # attack, and either way must not be streamed.
        raise EvidenceError(403, "This artifact path is outside the storage root.")
    if not path.exists():
        raise EvidenceError(410, "This artifact is no longer available on disk.")

    raw = path.read_bytes()

    integrity_verified = False
    if row.checksum_sha256:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != row.checksum_sha256:
            raise EvidenceError(
                409,
                "This artifact no longer matches the checksum recorded when the run "
                "captured it, so it cannot be served as evidence.",
            )
        integrity_verified = True

    if is_maskable(row.evidence_type):
        text = raw.decode("utf-8", errors="replace")
        masked_text, hits = mask_text(text)
        row.redaction_state = "masked"
        row.sanitized = True
        return ResolvedEvidence(
            content=masked_text.encode("utf-8"),
            content_type=content_type_for(row.evidence_type),
            filename=path.name,
            masked=True,
            mask_hits=hits,
            checksum_sha256=row.checksum_sha256,
            integrity_verified=integrity_verified,
        )

    # ── Binary: no text pass applies ─────────────────────────────────────────
    row.redaction_state = "not_maskable"
    row.sanitized = False
    if not unmasked_serving_permitted(cfg):
        raise EvidenceError(
            403,
            f"{row.evidence_type} evidence cannot be masked and this deployment "
            f"(app_env='{cfg.app_env}') does not permit downloading unmasked "
            "artifacts. Set AUTOMATION_EVIDENCE_ALLOW_UNMASKED=true to accept "
            "that a screenshot, video or trace may contain customer data.",
        )
    return ResolvedEvidence(
        content=raw,
        content_type=content_type_for(row.evidence_type),
        filename=path.name,
        masked=False,
        mask_hits=0,
        checksum_sha256=row.checksum_sha256,
        integrity_verified=integrity_verified,
    )
