"""
Phase 4 — Test Enrichment.

Enriches CandidateTest objects with contextual information from
Application Knowledge Model, Unified Application Model, and evidence sources.
"""

from .service import TestEnricher, EnrichmentContext, EnrichmentResult, LegacyTestEnricher

__all__ = [
    "TestEnricher",
    "EnrichmentContext",
    "EnrichmentResult",
    "LegacyTestEnricher",
]