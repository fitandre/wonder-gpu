"""
Thin wrapper around the modern Google GenAI SDK (google-genai).
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from google import genai
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
        self.client = genai.Client(
            vertexai=True,
            project=project_id,
            location=region
        )

    def call(
        self,
        model_key: str,
        system: str,
        user_content: str,
        max_tokens: int = 8192,
    ) -> CallResult:
        if model_key not in PRICING:
            raise ValueError(f"unknown model_key {model_key!r}")
        
        vertex_model_id = PRICING[model_key].vertex_model_id

        t0 = time.time()
        # Direct call using the new SDK
        # Note: system_instruction is passed in the config
        resp = self.client.models.generate_content(
            model=vertex_model_id,
            contents=user_content,
            config={
                "system_instruction": system,
                "max_output_tokens": max_tokens
            }
        )

        latency = time.time() - t0
        
        # New SDK response structure
        text = resp.text
        usage = resp.usage_metadata
        
        return CallResult(
            text=text,
            model_key=model_key,
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=usage.cached_content_token_count or 0,
            latency_s=latency,
            stop_reason=resp.candidates[0].finish_reason,
        )
