from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.storage.sqlite import SQLiteStore

PROMPT_REF_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class RenderedPrompts:
    system_content: str | None
    user_content: str | None


class PromptRenderer:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def render(
        self,
        role_id: str,
        user_input: str | None,
        render_time: str | None = None,
    ) -> RenderedPrompts:
        entries = self._entries_for_role(role_id)
        by_ref = {str(row["ref_name"]): row for row in entries}
        resolved_render_time = render_time or datetime.now().astimezone().isoformat(timespec="seconds")

        def render_ref(ref_name: str, stack: set[str]) -> str:
            if ref_name == "UserInput":
                return user_input or ""
            if ref_name == "time":
                return resolved_render_time
            entry = by_ref.get(ref_name)
            if entry is None:
                return "{" + ref_name + "}"
            if not entry["enabled"]:
                return ""
            if ref_name in stack:
                return ""
            return PROMPT_REF_RE.sub(
                lambda match: render_ref(match.group(1), {*stack, ref_name}),
                str(entry["content"]),
            )

        def render_entry(ref_name: str) -> str | None:
            entry = by_ref.get(ref_name)
            if entry is None or not entry["enabled"]:
                return None
            return PROMPT_REF_RE.sub(
                lambda match: render_ref(match.group(1), {ref_name}),
                str(entry["content"]),
            )

        system_content = render_entry("system")
        user_content = render_entry("UserInput") if user_input is not None else None
        return RenderedPrompts(
            system_content=system_content if system_content and system_content.strip() else None,
            user_content=user_content,
        )

    def _entries_for_role(self, role_id: str) -> list[dict[str, Any]]:
        entries = self.store.fetch_all(
            """
            SELECT ref_name, content, enabled
            FROM prompt_entries
            WHERE role_id = ?
            ORDER BY sort_order ASC
            """,
            (role_id,),
        )
        if entries or role_id == "default":
            return entries
        return self.store.fetch_all(
            """
            SELECT ref_name, content, enabled
            FROM prompt_entries
            WHERE role_id = 'default'
            ORDER BY sort_order ASC
            """
        )
