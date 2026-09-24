# Email Draft — Reply to Darin (ASRock) / Intel Engineering Questions

**Subject:** Re: ASRock B70 Purchase — Intel engineering questions (KubeVirt / SR-IOV)

---

Hi Darin,

Thank you for pushing this to Intel's engineering team. Please find our answers to their six questions below, along with the specific technical evidence backing our two blocking requirements.

**1. Primary use cases planned for KubeVirt on B70:**
- **Cloud Desktop / VDI** — this is our primary and largest use case. Wonder is a cloud desktop platform (100% remote desktop, accessed from any device), and B70s would back the GPU-accelerated desktop sessions for our end users.
- **Gaming** — secondary use case, streamed from the same VDI sessions (cloud gaming on top of the same infrastructure, not a separate product).
- **3D Rendering** — supported as part of the VDI workload (professional/creative users running GPU-accelerated applications inside their cloud desktop).
- **AI / GPU Compute** — not a current priority; VDI and gaming are what drive our GPU sizing.

**2. Is KubeVirt already part of the current deployment architecture, or is it being evaluated for future deployment?**
KubeVirt (running on Kubernetes, KVM underneath) is **already our production architecture today** — we currently run this on NVIDIA GPUs with NVIDIA's vGPU licensing server for GPU partitioning. We are evaluating the B70 specifically as an **alternative to NVIDIA** to remove that licensing dependency, not as a future/experimental path. This is a live migration decision for our beta and production rollout, not a proof-of-concept.

**3. What level of support is expected from Intel?**
All four of the levels you listed apply, but in this priority order:
1. **New feature enhancements** — specifically, the two fixes below (slice configurability, KubeVirt SR-IOV passthrough) are new work, not existing features we're asking to be pointed to.
2. **Production support** — once the above is fixed, we need an ongoing support relationship, since this hardware will run our production customer base (see volume numbers below).
3. **Validated deployment configuration** — a reference architecture we can build our platform's automation against.
4. **Deployment guide / reference documentation** — helpful but secondary to the above.

**4. Regarding gaming workloads, are there specific games or applications that need to be supported or validated?**
No specific game titles need certification — Wonder is a general-purpose cloud desktop, so end users install and run whatever Windows applications and games they choose, the same way they would on a physical PC. What we need validated is **general driver stability and consistent GPU clock behavior under multi-VM concurrent load**, not any specific title. That said, the video referenced below used Unigine Heaven, 3DMark (Fire Strike, Time Spy), and Cyberpunk 2077 as its test workloads, and reproduced the exact instability we're concerned about (details in point 1 below).

**5. Specific requirements for KubeVirt deployment (VM migration, orchestration, monitoring, scaling, etc.):**
- **Scaling**: this is our biggest requirement — we need many concurrent VFs per card behaving predictably and simultaneously (see the slicing issue below).
- **Monitoring**: we need per-VF GPU utilization visibility from the host. The video below explicitly flags that **no tool currently exists to show per-VF utilization from the Proxmox/KVM host** — this is a real gap for us, since we need to monitor per-tenant GPU usage in production.
- **Orchestration**: standard Kubernetes/KubeVirt VM lifecycle (create, migrate, scale) — no unusual requirement beyond what KubeVirt already provides, assuming Intel GPU support behind it works.
- **VM migration**: standard live migration support is expected, not yet tested on our side pending the driver fix.

**6. What host OS / software environment is planned for deployment?**
**Kubernetes with KubeVirt** (KVM-based), most likely on **Ubuntu** as the host OS. We are open to RHEL/OpenShift if that is Intel's better-supported/validated path — happy to align with whatever environment Intel can commit engineering support to.

---

**Now, restating our two blocking requirements with the technical evidence, since these are preconditions before we place the order:**

**1) GPU slicing must be fully configurable (2GB / 4GB / 8GB / 16GB), and all slices must run at consistent, full performance simultaneously.**

Today, per the video (Craft Computing, "Cloud Gaming Server Endgame - Intel Arc Pro B70 SR-IOV Bifurcation," https://www.youtube.com/watch?v=rMgRZTMxh1I), the B70 only supports even-division slicing (2, 4, or 7 VFs on the ASRock Creator card — giving 16GB, 8GB, or an oddly-uneven 4.56GB per VF), not the flexible 2GB/4GB/8GB/16GB mixed sizing we require. More critically, the video documents real, reproducible driver instability once multiple VFs are active simultaneously — this is not a theoretical concern, it's a tested result:

- Running 4 VMs concurrently (Unigine Heaven) worked well (~80 FPS each), but 3DMark and Cyberpunk 2077 exposed a **GPU clock scheduling bug**: the GPU reports 100% utilization inside the VM, but the host shows the actual clock fluctuating between 800–1500 MHz instead of reaching its 2800 MHz boost — cutting real performance to a fraction of bare-metal (a single VM scored 5,100 in 3DMark Time Spy vs. 49,429 on bare metal, roughly a GTX 1660-class result instead of an RTX 5070-class one).
- Screen artifacting appeared during Time Spy and Cyberpunk under single-VM load, consistent with a driver/clock-scheduling defect, not thermal or hardware failure (card stayed at 63°C under active cooling).
- Cyberpunk 2077 **soft-locked and crashed to desktop within 60 seconds** in one of the tested VMs.
- The driver update that even got multiple VFs booting to desktop (rather than a black screen) only shipped **the day before the video's testing** — meaning multi-VF stability is extremely recent and, per the tester's own conclusion, "not in a workable state where they properly clock up the GPU core in response to GPU load inside of a VM."

This is exactly the instability we need Intel engineering to fix before we can commit to a production deployment: consistent clock behavior and performance across all active VFs simultaneously, at whatever slice size we configure, not just when few VFs are idle-adjacent to each other.

**2) KubeVirt SR-IOV support for the B70 needs to be actively re-established.**

You asked us to reference https://github.com/intel/kubevirt-gfx-sriov — we want to flag directly that **this repository is archived and has been discontinued by Intel since 2024** ("Intel has ceased development and contributions including, but not limited to, maintenance, bug fixes, new releases, or updates, to this project. Intel no longer accepts patches to this project."). Its own documentation targets **12th Generation Intel Core embedded processors**, not the Battlemage (BMG) architecture the B70 uses. In other words, the code we were pointed to as a starting reference was never built for this GPU generation and is no longer maintained by Intel at all — this needs new engineering work, not a pointer to existing documentation.

We understand from your note that "Intel GPU support exists in GPU DRA v0.11.0" — could you confirm whether that DRA (Dynamic Resource Allocation) driver path is the one Intel intends to support for B70 KubeVirt passthrough going forward, replacing the archived kubevirt-gfx-sriov project? That would help us understand which codebase to plan our integration against.

---

**On volume, since it's directly relevant to how much engineering priority this gets:** as shared in an earlier email, our beta targets 10,000 concurrent users on 500 bare-metal servers (4 GPUs each = ~2,000 GPUs), scaling in production to 1,000,000 concurrent users across 50,000 servers (~200,000 B70 GPUs). We're happy to have Intel's engineering team join a call directly if that helps them scope this faster — we can also share our own test logs and reproduction steps once we have review units in hand, if that's useful for their triage.

Kind regards,

Andre Meyer Pflug
CEO
(302) 257-6040
thewonder.cloud
