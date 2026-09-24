# kayfabe-loop

A starting-point orchestrator that works through `kayfabe-production-roadmap.md`
using Claude on Vertex AI (billed to your GCP credits), testing
GPU-dependent phases against a GKE cluster with NVIDIA L4 nodes.

## What this is, and isn't

**Is:** a working scaffold — model routing, a Vertex client with caching
support, a real token/cost ledger, a Kubernetes GPU-job runner, and a loop
driver — structured around the roadmap's phases and gates.

**Isn't:** a system that autonomously ships production kernel-level code
unsupervised. `main.py` deliberately refuses to auto-merge to `base_branch`
and refuses to self-certify a phase gate — both roadmap.md and this repo's
own engineering discipline (see roadmap.md §3) treat those as human
checkpoints, not steps to automate away. The `apply_patch`/`run_tests` core
of the loop (`main.py`'s `NotImplementedError`) is also left for you to wire
up against your actual repo layout rather than faked — that's the one part
that's genuinely specific to how you want changes proposed and validated,
and pretending to have solved it generically would be worse than leaving it
explicit.

## Layout

```
kayfabe-production-roadmap.md   # the phase plan this loop works through
orchestrator/
  config.yaml          # GCP/Vertex settings + model routing rules
  task_graph.yaml       # phases, dependencies, gates, planning-level cost buckets
  pricing.py             # single source of truth for Claude-on-Vertex pricing
  vertex_client.py        # AnthropicVertex wrapper w/ prompt caching + retries
  model_router.py          # task -> model tier, with failure-based escalation
  token_ledger.py           # SQLite ledger of REAL usage/spend (authoritative)
  git_ops.py                 # branch-per-task, never auto-merges
  k8s_gpu_runner.py           # dispatches GPU test jobs to the GKE L4 pool
  estimate_cost.py             # planning-level cost projection (see docs/cost_estimate.md)
  main.py                       # the loop driver (run / gate-report / status)
docs/
  gcp_setup.md           # Vertex Model Garden access, GKE L4 node pool, IAM, budgets
  cost_estimate.md        # token/cost projection output + methodology
```

## Quick start

```bash
cd orchestrator
pip install -r requirements.txt
cp config.yaml config.local.yaml   # fill in gcp.project_id etc.

# 1. See the cost projection before spending anything
python estimate_cost.py
python estimate_cost.py --cache-hit 0.4

# 2. Follow docs/gcp_setup.md: Vertex Model Garden access, GKE L4 node pool, IAM, budget alert

# 3. Create real tasks for Phase 0 (roadmap.md §7 template), add them under
#    task_graph.yaml's `tasks:` list, then wire up main.py's context-builder
#    + patch-apply step for your repo (see the NotImplementedError comment).

# 4. Run it
python main.py status
python main.py run --phase P0
python main.py gate-report --phase P0   # human checklist, not an auto-pass
```

## Cost

See `docs/cost_estimate.md` for the full breakdown. Headline numbers as of
2026-09-11 pricing:

- **Tokens, full P0–P8 roadmap, no caching:** ~$683 (Opus 5 $376 / Sonnet 5
  $283.50 / Haiku 4.5 $23.40 across ~157M input + 16.6M output tokens)
- **Tokens, with 40% prompt-cache hit rate:** ~$525
- **GKE L4 test infrastructure:** ~$1,309 (≈1,870 GPU-hours @ $0.70/hr on-demand)
- **Grand total planning range:** roughly **$1,200 – $4,000**, dominated by
  how many iterations the reverse-engineering-heavy phases (P1, P2, P5)
  actually take — run Phase 0 first and recalibrate from real numbers.

## Installed Components (GKE Cluster)
- **KubeVirt:** v1.9.0 (Patched for GKE Standard node affinity)
- **CDI:** v1.66.1
- **GPU Operator:** v26.7.1 (Driver/Toolkit disabled as per requirements)

## Current Task: Windows 2025 Provisioning
- **ISO:** Windows Server 2025 Datacenter (Desktop Experience)
- **Upload Status:** In progress to DataVolume \`windows-2025-iso\`

## Windows 2025 Test VM
A VirtualMachine definition has been created in \`windows-2025-vm.yaml\`. This VM is configured with:
- **CPU:** 4 Cores
- **Memory:** 16Gi
- **Disk:** 100Gi (Persistent DataVolume)
- **Boot:** EFI mode
- **GPU:** NVIDIA L4 passthrough
- **Installation:** Booting from the uploaded \`windows-2025-iso\`

To start the VM once the upload is complete:
\`\`\`bash
kubectl apply -f windows-2025-vm.yaml
virtctl start windows-2025-test
\`\`\`
