"""
Selection Manager for LLM Consultant Advisor.

Manages the set of selected record IDs within a session.
Consultants can select/deselect individual records from the similarity results.
"""

from __future__ import annotations

import logging

from app.database import sessions_store
from app.models import ErrorCode

logger = logging.getLogger(__name__)


class SelectionManager:
    """Manages record selection state within a session."""

    def update_selections(
        self,
        session_id: str,
        add_ids: list[str] | None = None,
        remove_ids: list[str] | None = None,
    ) -> list[str]:
        """
        Add and/or remove record IDs from the session's selection.

        Args:
            session_id: Active session id.
            add_ids:    Record IDs to mark as selected.
            remove_ids: Record IDs to deselect.

        Returns:
            The updated list of selected_record_ids.

        Raises:
            ValueError if the session does not exist or is not active.
        """
        session = sessions_store.get(session_id)
        if session is None:
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found."
            )
        if session.status != "active":
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' is not active."
            )

        # Validate that requested IDs exist in similarity results
        valid_ids = {r.record.id for r in session.similarity_results}

        current = set(session.selected_record_ids)

        for rid in add_ids or []:
            if rid not in valid_ids:
                raise ValueError(
                    f"Record '{rid}' não encontrado nos resultados de similaridade da sessão."
                )
            current.add(rid)

        for rid in remove_ids or []:
            current.discard(rid)

        session.selected_record_ids = list(current)

        logger.info(
            "Selections updated | session_id=%s selected=%d",
            session_id,
            len(session.selected_record_ids),
        )
        return session.selected_record_ids

    def get_selections(self, session_id: str) -> list[str]:
        """Return the current list of selected record IDs for a session."""
        session = sessions_store.get(session_id)
        if session is None:
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found."
            )
        return list(session.selected_record_ids)
