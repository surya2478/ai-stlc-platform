"""062 - Delete project_llm_settings rows for de-registered LLM providers

The selectable provider list in app/services/llm_provider_registry.py was
narrowed to openrouter / ollama / ai_gateway. OpenRouter already fronts 400+
models (Llama, Qwen, Mistral, Gemini, GPT), so the rest were redundant as
separate providers.

This deletes their saved rows, and it is a correctness fix rather than tidying:
resolve_project_llm_routes reads project_llm_settings directly and never
consults the registry, while _build_llm still has a branch for every provider.
A row left behind for a de-registered provider would therefore keep routing
traffic at run time while appearing nowhere in the UI — invisible state that
nobody could diagnose from the screen.

Every deleted row is first copied into project_setting_audit_logs, so the
change stays traceable per the platform's provenance rules. The audit rows are
written with source='migration_062'.

At the time of writing, all rows for these providers in the development
database were is_enabled=false, so nothing in active use was removed. That is
NOT guaranteed in other environments: if staging or production has one of these
providers enabled and primary, deleting its row moves that project to the
system default (DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL). The audit log names
exactly which projects were affected — check it after upgrading.

Idempotent — safe to re-run.

Revision ID: 062
Revises: 061
"""
from alembic import op
import sqlalchemy as sa

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None

DEREGISTERED = ("groq", "together", "cerebras", "mistral", "google_gemini", "huggingface", "openai")


def upgrade() -> None:
    bind = op.get_bind()
    keys = sa.bindparam("keys", expanding=True)

    # Snapshot into the audit log before deleting, so the removal is traceable
    # to the same place every other settings change is recorded.
    bind.execute(
        sa.text(
            """
            INSERT INTO project_setting_audit_logs
                (project_id, setting_type, old_value, new_value, changed_by, changed_at, source, change_reason)
            SELECT project_id,
                   'llm_provider_deregistered',
                   jsonb_build_object(
                       'provider_key', provider_key,
                       'provider_name', provider_name,
                       'model_name', model_name,
                       'llm_role', llm_role,
                       'is_enabled', is_enabled,
                       'is_primary', is_primary,
                       'is_fallback', is_fallback,
                       'fallback_priority', fallback_priority
                   ),
                   NULL,
                   NULL,
                   now(),
                   'migration_062',
                   'Provider removed from the selectable registry; row deleted so it cannot route invisibly.'
              FROM project_llm_settings
             WHERE provider_key IN :keys
            """
        ).bindparams(keys),
        {"keys": list(DEREGISTERED)},
    )

    bind.execute(
        sa.text("DELETE FROM project_llm_settings WHERE provider_key IN :keys").bindparams(keys),
        {"keys": list(DEREGISTERED)},
    )


def downgrade() -> None:
    # Deliberately not restoring the deleted rows. Re-adding a provider to the
    # registry does not imply any project wants it selected again, and the
    # audit log written above holds everything needed to recreate a row by
    # hand if that is genuinely wanted.
    pass
