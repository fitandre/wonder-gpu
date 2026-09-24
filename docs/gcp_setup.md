# GCP setup for the kayfabe loop

Verify every gcloud flag and console step below against current docs before
running against a real project — both Vertex Model Garden access and GKE's
GPU node-pool flags change over time and this file will drift.

## 1. Project & APIs

```bash
export PROJECT_ID=your-project-id
gcloud config set project "$PROJECT_ID"

gcloud services enable \
  aiplatform.googleapis.com \
  container.googleapis.com \
  compute.googleapis.com
```

## 2. Vertex AI Model Garden access to Claude

1. Console → Vertex AI → Model Garden → search "Claude".
2. Open Claude Opus 5 / Sonnet 5 / Haiku 4.5, accept the model terms **for
   this project** — API calls fail on a permissions error until this is
   done, even with a correct IAM role.
3. Note which regions each model is actually enabled in for your project
   (this varies) and set `gcp.vertex_region` in `config.yaml` accordingly.
4. Grant the identity the loop runs as the `roles/aiplatform.user` role:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:YOUR_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

5. Auth for local runs: `gcloud auth application-default login`.
   For in-cluster runs, prefer Workload Identity over a downloaded key.

## 3. GKE cluster with an L4 (g2) GPU node pool

```bash
# System node pool (no GPUs) for the loop's own pods / small services
gcloud container clusters create kayfabe-test-cluster \
  --zone us-central1-a \
  --num-nodes 1 \
  --machine-type e2-standard-4 \
  --workload-pool="$PROJECT_ID.svc.id.goog"

# GPU node pool -- g2-standard-4 = 1x NVIDIA L4, 4 vCPU, 16GB RAM.
# Scales to zero when idle so you're not paying for GPUs between test runs.
gcloud container node-pools create l4-pool \
  --cluster kayfabe-test-cluster \
  --zone us-central1-a \
  --machine-type g2-standard-4 \
  --accelerator type=nvidia-l4,count=1,gpu-driver-version=latest \
  --num-nodes 0 \
  --enable-autoscaling --min-nodes 0 --max-nodes 4 \
  --node-taints nvidia.com/gpu=present:NoSchedule
```

`gpu-driver-version=latest` has GKE install the NVIDIA driver automatically
on recent GKE versions — confirm this is still current behavior for your
GKE version before relying on it; older setups needed a manual device-plugin
DaemonSet.

```bash
gcloud container clusters get-credentials kayfabe-test-cluster --zone us-central1-a
kubectl get nodes -l cloud.google.com/gke-nodepool=l4-pool
```

## 4. Bare-metal-adjacent access for kayfabe's test workloads

Kayfabe's own test suite needs `/dev/kvm` and, per its README, an NVIDIA GPU
+ pinned host driver version on the host doing the testing. A standard GKE
pod is not a KVM host by default. Two options, pick based on what the loop
actually needs at each phase:

- **Nested virtualization on GCE nodes**: GKE node pools on GCE support
  nested KVM on supported machine types with the right node image; this is
  the more direct match for what `scripts/run_full_suite.sh` expects.
- **Bare-metal-equivalent instance outside the pod abstraction**: for the
  heaviest phases (P2 Windows bring-up, P8 soak), consider a dedicated
  `g2-standard-*` GCE VM (not a GKE pod) as the actual QEMU host, with the
  GKE cluster used for orchestration/scheduling metadata (Phase 7) rather
  than as the hypervisor host itself.

Pick this per-phase rather than forcing everything through one model — `k8s_gpu_runner.py`'s job image is where this decision actually gets made;
update its `image`/`command`/privileged settings to match whichever of the
two you choose for a given task.

## 5. Cost controls

```bash
gcloud billing budgets create \
  --billing-account=YOUR_BILLING_ACCOUNT_ID \
  --display-name="kayfabe-loop" \
  --budget-amount=500USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```

Set this before the first real run, not after Phase 1 — the planning
estimate in `docs/cost_estimate.md` has a wide uncertainty band, and a
budget alert is the cheap way to find out early if reality is tracking the
high end of it.
