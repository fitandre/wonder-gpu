# Wonder GPU: Production-Grade Windows GPU Acceleration

This project orchestrates the transformation of the **Kayfabe** research project into a production-ready GPU virtualization solution for Wonder Cloud.

## Objective
Enable hardware-accelerated D3D9/11/12 in Windows guests on KubeVirt/QEMU using unmodified NVIDIA drivers, bypassing proprietary licensing servers.

## Tech Stack
*   **Core Logic:** Rust (Kayfabe Hexagonal Architecture)
*   **Orchestrator:** Gemini 1.5 Pro via Google Vertex AI
*   **Testing Infrastructure:** Google Kubernetes Engine (GKE) with NVIDIA L4 nodes
*   **Hypervisor:** KubeVirt / QEMU / KVM

## Roadmap Status
Working through the \`kayfabe-production-roadmap.md\`:
*   **P0 (Foundation):** Bugfixes in compute-only paths and GMMU walker. [In Progress]
*   **P1 (Graphics):** Linux graphics engine and present pipeline.
*   **P2 (Windows):** Windows guest bring-up and WDDM transport surface.

## Engineering Principles
1.  **Pure Logic Core:** OS/Hypervisor agnostic.
2.  **Unmodified Drivers:** No custom in-guest kernel modules.
3.  **Measurable Verification:** Every gate requires hardware-measured results.
