"""
Thin wrapper around Google's Vertex AI SDK (google-cloud-aiplatform).

Install: pip install "google-cloud-aiplatform>=1.70"

Auth: uses Application Default Credentials. On a GCE/GKE workload identity
this is automatic; locally run `gcloud auth application-default login` first.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel, Part, SafetySetting, FinishReason
from pricing import PRICING


@dataclass
class CallResult:
    text: str
    model_key: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    latency_s: float
    stop_reason: str


class VertexGeminiClient:
    def __init__(self, project_id: str, region: str = "us-central1"):
        self.project_id = project_id
        self.region = region
        vertexai.init(project=project_id, location=region)

    def call(
        self,
        model_key: str,
        system: str,
        user_content: str,
        max_tokens: int = 8192,
        cache_system: bool = True,  # Placeholder: Gemini caching is out-of-band
        max_retries: int = 5,
    ) -> CallResult:
        """
        model_key: one of pricing.PRICING's keys ("gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash").
        """
        if model_key not in PRICING:
            raise ValueError(f"unknown model_key {model_key!r}, expected one of {list(PRICING)}")
        vertex_model_id = PRICING[model_key].vertex_model_id

        model = GenerativeModel(
            vertex_model_id,
            system_instruction=[system]
        )

        last_err = None
        for attempt in range(max_retries):
            t0 = time.time()
            try:
                # Synchronous call
                resp = model.generate_content(
                    user_content,
                    generation_config={"max_output_tokens": max_tokens}
                )
                break
            except Exception as e:
                last_err = e
                if attempt == max_retries - 1:
                    raise
                time.sleep(min(2 ** attempt, 30))
        else:
            raise last_err

        latency = time.time() - t0
        text = resp.text
        
        # Gemini usage metadata
        usage = resp.usage_metadata
        return CallResult(
            text=text,
            model_key=model_key,
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
            cache_creation_input_tokens=0, # Simplified
            cache_read_input_tokens=usage.cached_content_token_count if hasattr(usage, 'cached_content_token_count') else 0,
            latency_s=latency,
            stop_reason=str(resp.candidates[0].finish_reason),
        )
