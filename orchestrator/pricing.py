"""
Pricing table for Google Gemini models on Vertex AI.

Source: Google Cloud Vertex AI Pricing page.
Verified 2026-09-24.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    vertex_model_id: str
    input_per_mtok: float       # USD per 1M input tokens
    output_per_mtok: float      # USD per 1M output tokens
    cache_read_per_mtok: float  # USD per 1M tokens, context cache hit (~0.1x input)
    context_window: int
    max_output: int


PRICING = {
    "gemini-1.5-pro": ModelPricing(
        vertex_model_id="gemini-1.5-pro",
        input_per_mtok=1.25,
        output_per_mtok=3.75,
        cache_read_per_mtok=0.125,
        context_window=2_000_000,
        max_output=8192,
    ),
    "gemini-1.5-flash": ModelPricing(
        vertex_model_id="gemini-1.5-flash",
        input_per_mtok=0.075,
        output_per_mtok=0.30,
        cache_read_per_mtok=0.0075,
        context_window=1_000_000,
        max_output=8192,
    ),
    "gemini-2.0-flash": ModelPricing(
        vertex_model_id="gemini-2.0-flash-exp",
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.01,
        context_window=1_000_000,
        max_output=8192,
    ),
}


REGIONAL_ENDPOINT_PREMIUM = 1.10

# GKE g2-standard-4 (1x NVIDIA L4, 4 vCPU, 16GB RAM), on-demand, us-central1.
GKE_G2_STANDARD_4_ON_DEMAND_PER_HOUR = 0.70
GKE_G2_STANDARD_4_SPOT_PER_HOUR = 0.21


def call_cost(model_key: str, input_tokens: int, output_tokens: int,
              cached_input_fraction: float = 0.0) -> float:
    p = PRICING[model_key]
    cached = input_tokens * cached_input_fraction
    uncached = input_tokens - cached
    cost = (
        uncached * p.input_per_mtok
        + cached * p.cache_read_per_mtok
        + output_tokens * p.output_per_mtok
    ) / 1_000_000
    return cost
