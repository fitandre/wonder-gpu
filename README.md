# Wonder GPU: Production-Grade Windows GPU Acceleration

This project orchestrates the transformation of the **Kayfabe** research project into a production-ready GPU virtualization solution for Wonder Cloud.

## Objective
Enable hardware-accelerated D3D9/11/12 in Windows guests on KubeVirt/QEMU using unmodified NVIDIA drivers, bypassing proprietary licensing servers.

## Infrastructure Setup
The testing environment is a GKE Standard cluster on Google Cloud Platform.

### GKE Cluster Command (Standard with Nested Virt + vGPU)
The following command is used to provision the test cluster `testg2` in `us-east4-a` with NVIDIA L4 GPUs and nested virtualization enabled for KubeVirt Windows 2025 guests:

```bash
gcloud container clusters create testg2 \
    --project=thewonder-ai \
    --zone=us-east4-a \
    --machine-type=g2-standard-24 \
    --num-nodes=2 \
    --image-type=UBUNTU_CONTAINERD \
    --enable-nested-virtualization \
    --accelerator=type=nvidia-l4,count=2 \
    --node-labels=nvidia.com/gpu.workload.config=vm-vgpu \
    --local-nvme-ssd-block=count=2 \
    --enable-ip-alias \
    --cluster-ipv4-cidr=10.100.0.0/16 \
    --services-ipv4-cidr=10.101.0.0/20 \
    --disk-size=100
```

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
