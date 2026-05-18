"""Shared fixtures/setup for the ``tests/agent/`` subtree.

Ensures all eight tools are registered into ``TOOLS_REGISTRY`` before
any agent test runs. The six Phase 3 tools each live in a subpackage
with their ``@register_tool`` decorator in ``tool.py``; the two RAG
corpora wrappers live in :mod:`elh_rag.agent.tools_RAG_corpora`,
which is re-exported as a side-effect import by
:mod:`elh_rag.agent`.
"""

from __future__ import annotations

import elh_rag.agent
import elh_rag.tools.answer_policy_question.tool
import elh_rag.tools.compute_total_cost.tool
import elh_rag.tools.find_available_rooms.tool
import elh_rag.tools.find_rooms.tool
import elh_rag.tools.get_booking_stats.tool
import elh_rag.tools.get_property_details.tool  # noqa: F401
