# Kayfabe → Production: Windows GPU Acceleration Roadmap

**Document purpose:** starting point for development work in Claude Code. Turns
[`kayfabe`](https://github.com/reindertpelsma/kayfabe) — a research-stage GPU-emulation
project that currently proves CUDA compute forwarding on a Linux guest — into a
production-ready system that gives Windows VMs on QEMU/KVM hardware-accelerated,
multi-tenant, migratable GPU access via a **stock, unmodified NVIDIA driver**.

**Sources this plan reconciles:**
- `windows-guest-gpu-accel-architecture{,-v2,-v3}.md` — the target *outcomes* (Windows
  D3D9/11/12 acceleration, multi-tenant sharing, live migration, hot-plug, cluster
  integration, production-grade signing/distribution), originally scoped around a
  paravirtual Venus/DXVK stack.
- The `kayfabe` repository as of **2026-09-11** (`master` @ `ee50148d` /
  `docs/STATUS_DETAIL.md` snapshot 2026-09-06) — the chosen *implementation strategy*
  (GPU device emulation + real-driver protocol forwarding), which replaces the
  paravirtual-driver strategy but must still hit the same outcomes.

This document does **not** re-derive the outcomes — see the gap analysis this roadmap
was produced from for the full reasoning. It exists so that each phase below can be
handed to Claude Code as a self-contained unit of work, with an explicit Definition of
Done, without needing the full history re-explained each time.

---

## 0. How to use this document

1. **One phase ≈ one or more Claude Code sessions.** Phases are ordered by hard
   dependency, not by priority — do not start a phase before its prerequisites' exit
   criteria are checked off. Within a phase, workstream items are written to be
   assignable independently (different crates, different sessions, different people).
2. **Every workstream item should become a ticket** with: the acceptance criteria
   copied verbatim from this doc, the crate(s) it touches, and a link to the relevant
   `docs/design/*.md` file if one already exists in the repo. Use the task template in
   §7.
3. **Preserve the repository's existing engineering discipline** (§3) — it is a real
   asset, not overhead. A production-ready claim in this codebase means "measured, on
   real hardware, with a dated result in `docs/reference/`," not "looks right." Do not
   let velocity erode this.
4. **Land risky work behind flags**, following the existing pattern
   (`host-isolates` build feature + `KAYFABE_ISOLATES=real` runtime switch). New phases
   should get their own feature flags so `master` never depends on unfinished work to
   build or boot.
5. **Update `docs/STATUS_DETAIL.md`-style status, don't rewrite it.** When a phase's
   exit criteria are met, append a dated, measured entry. When an earlier claim turns
   out wrong, correct it in place with a visible strikethrough/correction, the way the
   existing docs already do. This is how the project keeps "believe the dated
   measurement" enforceable.
6. **Every phase ends with a hardware-measured gate**, not a code-complete claim.
   Simulator/mock-only results (`kayfabe-mocks`) unlock the *next phase's design work*,
   not the phase's own exit criteria.

---

## 1. North-star goals (technology-agnostic, restated from the source docs)

| # | Goal | Restated from source docs |
|---|---|---|
| G1 | Hardware-accelerated D3D9/11/12 in Windows 10/11 guests on QEMU/KVM | Core thesis, all iterations |
| G2 | Near-native performance (~85%+ GPU-bound) | v1 §B.3 Phase-1 exit criteria |
| G3 | Safe sharing of one physical GPU across many VM tenants | v2/v3 broker + DRA architecture |
| G4 | Host kernel/process protected from a hostile or buggy guest | v1 §1.6 item 8; v3 Part C isolation drills |
| G5 | Live migration of a VM mid-workload, tiered fallback | v3 Part B, migration tiers T1–T4 |
| G6 | Hot-add/remove of the virtual GPU without guest crash | v3 Part D |
| G7 | Cluster scheduling / orchestration integration | v3 Workstream C (KubeVirt-shaped) |
| G8 | Driver distribution acceptable to real users (no test-signing forever) | v1 §1.6 item 7, §B.4 |
| G9 | Coverage across NVIDIA GPU generations and driver versions | v1 §1.5; kayfabe's decoupled-version design goal |

**Kayfabe's structural head start on G8 and part of G4/G9:** because the guest loads
NVIDIA's own signed driver unmodified, there is no custom KMD to certify or sign, and
the `DriverAbi`/`Arch` seams are explicitly designed for decoupled guest/host driver
versions. This roadmap preserves that advantage — nothing below should require
patching or shimming the in-guest driver binary.

---

## 2. Baseline as of 2026-09-11 — what's already proven, what's explicitly deferred

Read `docs/STATUS_DETAIL.md` and `ARCHITECTURE.md` in the repo before starting any
phase; this is a summary, not a replacement.

**Proven on real hardware (GA106, driver 580.159.04):**
- Stock NVIDIA driver boots against the emulated device + faked GSP; real RM ioctls
  land on `/dev/nvidiactl`.
- `cup3` (context create/launch) and `cup8` (matmul, N up to 3072) pass with
  bit-exact results.
- Host forwarding process runs fully unprivileged (empty capability set, `NoNewPrivs`,
  non-root).
- The same QEMU overlay builds and boots on QEMU 9.2.0 and 10.2.4.
- Concurrent and sequential multi-process CUDA — **branch only**, not on `master`; the
  4th sequential process fails, and the real ceiling found is *device opens*, not
  *processes*.

**Explicitly not built (confirmed in-repo, not inferred):**
- L3 graphics pipeline: "deliberately absent"; only a typed `Present`/`SurfaceHandle`
  seam exists.
- Any Windows guest run — every measured result is against a Linux (Ubuntu) guest.
- Any tenant/VM identity concept — no `VmId`/`TenantId`/`GuestId` anywhere in `crates/`.
- Migration, hot-plug, and cluster integration — no code, no design docs beyond seam
  placeholders.
- The GSP↔core bridge (`RpcCommand → RmEvent`) — `kayfabe-gsp` is built (S0–S5) but has
  **zero production consumers**.
- The GMMU walker (`kayfabe-mmu::walker`) — trait shape only, no walk loop.
- Performance is 22–81× off native for large kernels.
- 9 of ~2958 tests fail on `master`, and per the project's own accounting at least 6
  are real functional/safety defects **deliberately left red pending a design ruling**,
  not bugs that slipped through. The dominant one: ring-content forwarding was scoped
  off passthrough channels, which makes `HostCe`/`await_semaphore` unreachable on the
  channel kind that needs them. **This blocks real compute-channel forwarding and must
  be resolved before Phase 1.**

---

## 3. Engineering principles to preserve throughout

These are already load-bearing in the codebase. Every phase below inherits them; they
are not repeated per-phase.

- **Hexagonal core, ports at the edges.** New capability = new port method or new
  adapter crate, not new logic threaded through `kayfabe-core`/`-mmu`/`-fwd`/`-completion`
  directly. Those four crates stay OS/hypervisor/GPU-generation-agnostic.
- **`forbid(unsafe_code)` everywhere except the two audited raw crates**
  (`kayfabe-linux-raw`, `kayfabe-qemu-raw`). Any new OS/FFI surface either lives in one
  of those two or becomes a new audited `*_unsafe.rs`-convention crate — never inline
  unsafe in a logic crate.
- **MISS = FAULT / DEFER, never a heuristic guess.** The two-way split (not-yet-knowable
  → DEFER, never-knowable → FAULT) is a proven invariant; new event types must be
  classified into one of these at design time, not left ambiguous.
- **Transactional apply, rollback on derivation fault.** Any new event class flowing
  through `Gpu::apply` must fail atomically, never leave partial state.
- **No completion forgery.** The project treats this as the one invariant it rules out
  by name (see the adjudicated P0 blocker in §2). Any new completion/fence path must be
  provably unable to signal `Served` without a real host-side completion.
- **Capacity-bounded, never OOM; loudly, not silently.** New guest-growable tables need
  an explicit cap and a `CapacityExceeded`-style refusal, plus a complexity check — the
  project has one open, *measured* O(n²) DoS gap (I4) that any new per-event-cost table
  should learn from, not repeat.
- **Believe the dated measurement over the prose summary.** When a phase's status is
  written up, date it and cite the revision/commit. When something is found stale,
  correct in place rather than silently editing history.
- **`scripts/run_full_suite.sh` on real hardware is authoritative; GitHub CI is
  convenience.** Every phase's exit criteria must be demonstrated by the former.

---

## 4. Phase plan

### Phase summary

| Phase | Theme | Primary crates touched | Gate |
|---|---|---|---|
| P0 | Close the foundation | `kayfabe-fwd`, `-gsp`, `-mmu`, `-rt`, CI/mutation gate | All tests green (`--no-fail-fast`), or every red test has a signed-off design ruling |
| P1 | Graphics engine & present pipeline | new `kayfabe-gfx` (or extend `-fwd`/`-arch`), `-vmm` `Present` impl | Linux guest renders a real frame end-to-end |
| P2 | Windows guest bring-up | `-abi` (Windows wire tables), `-gsp` (display RPCs), `-arch` | Windows 10/11 boots, WARP-differential D3D11 correctness |
| P3 | Performance & data-plane redesign | `-fwd`, `-completion`, `-vmm-kvm`/`-qemu-raw` | Native-relative performance target hit and measured |
| P4 | Multi-tenant isolation | `-core` (tenant axis), `-isolate`, `-isolate-host` | Two real concurrent VM tenants, budget-enforced, crash-contained |
| P5 | Live migration | new `kayfabe-snap` | Kill→restore pixel/compute-correct on one host; tiered fallback designed |
| P6 | Hot-plug | `-vmm-qemu`, `-qemu-raw`, guest-behavior catalogue | 100-cycle add/remove clean on target Windows builds |
| P7 | Cluster/orchestration integration | new `kayfabe-noded`, scheduler plugin | N-VM density on a real cluster-shaped topology |
| P8 | Hardening & production certification | cross-cutting | Full production gate (§6) passes |

Phases P1–P2 and P4 can begin design/mocked work in parallel with the tail of P0, but
**no phase's hardware-measured exit criteria may be claimed before P0's is.**

---

### Phase 0 — Close the foundation

**Why it gates everything:** the compute-only path isn't actually complete yet. The
adjudicated ring-forwarding blocker means the exact channel kind that graphics and
real workloads need (`HostCe`, semaphore-await) is currently *structurally
unreachable*, not just untested. Building graphics or multi-tenancy on top of this
foundation would mean building on a known hole.

**Workstream items:**
- [ ] **Design ruling on the passthrough-channel severance.** Read
  `docs/design/w329_wiring_the_release.md` and the w296/w287 history. Produce a signed
  design decision: either (a) re-scope which channel kinds may be host-backed so
  `HostCe`/`await_semaphore` become reachable again, or (b) formally accept the
  restriction and redesign the affected 4 tests' expectations. This is a prerequisite
  for Phase 1's graphics workload, which will need exactly this path.
- [ ] Resolve or formally accept-and-document the remaining adjudicated red tests
  (`a_wired_device_refuses_a_framebuffer_page_nothing_ever_wrote`,
  `a_device_with_no_fb_source_refuses_the_vidmem_ring`,
  `the_logic_crates_carry_no_unnamed_guest_os_assumption`,
  `every_unranked_lock_a_vcpu_thread_can_hold_is_classified`,
  `the_audited_crate_list_matches_the_tree_and_is_used_by_all_three_sub_gates`). Each
  needs an owner ruling, not a code edit to force green.
- [ ] Land the ledger-only failure (control `0x83de030c`) per
  `docs/design/w329_wiring_the_release.md`.
- [ ] Build the **GMMU walker** (`kayfabe-mmu::walker`): implement `FbRead` +
  `WalkResult` loop. Required by Phase 1 (graphics needs real page-table walks, not
  just forward-populated blob mappings) and by Phase 5 (migration needs to read live
  guest-visible mappings without guest cooperation).
- [ ] Wire the **`RpcCommand → RmEvent` bridge** in `kayfabe-gsp` — currently built but
  with zero production consumers. This is the on-ramp for every future GSP-mediated
  feature (display RPCs in P2, power/reset in P6).
- [ ] Complete **L1-M2**: real reactor, `kayfabe-linux-raw` full surface, `Vmm` memory
  plane, reclamation lifecycle trigger (Law 8 is currently "half a law" — deferral is
  unbounded until something arms it).
- [ ] Fix or explicitly re-scope the **O(n²) control-plane DoS** (I4) — two candidate
  fixes are already named in `docs/design/core_security_threat_model.md`; pick one and
  land it before any multi-tenant work (Phase 4) makes this guest-reachable at scale
  matter more.
- [ ] Re-run and re-baseline: mutation gate (scope changed to every production crate,
  threshold pending re-derivation), TSan campaign (last "0 races" result predates
  several changes), and promote the two-guest-process branch work
  (`w337-gpu-name-seam`) to `master` once its own suite is clean, *or* explicitly
  document why it stays on a branch.

**Testing:** `cargo test --workspace --no-fail-fast` clean, or every remaining red test
has a linked, dated design ruling in `docs/design/`. `scripts/run_full_suite.sh` run on
real hardware with zero unacknowledged skips. TSan campaign re-run and its result dated.

**Exit criteria (Gate P0):**
- [ ] Zero tests fail without an explicit, linked design ruling.
- [ ] `HostCe`/semaphore-await path is reachable by construction (ruling resolved).
- [ ] GMMU walker passes a real page-table-walk conformance suite.
- [ ] `RpcCommand → RmEvent` bridge has at least one real caller.
- [ ] Mutation score re-quoted with a current, dated number against the new scope.
- [ ] O(n²) DoS gap closed or explicitly deferred with a guest-reachability risk
  acceptance signed off.

**Non-goals:** no new user-facing capability ships in this phase. This is entirely
foundation repair.

---

### Phase 1 — Graphics engine & present pipeline

**Goal:** a Linux guest, using the **real NVIDIA driver's own graphics stack**
(EGL/GLX or Vulkan against the fabricated GPU), renders a real frame and gets it onto a
host-visible surface. This is the single largest reverse-engineering lift in the whole
plan — treat it as its own multi-milestone workstream, not one ticket.

**Preconditions:** Phase 0 gate passed (GMMU walker real, `HostCe` path reachable).

**Workstream items:**
- [ ] **Milestone 1a — 3D/graphics engine RM classes.** Extend the intent-recovery
  layer (`kayfabe-fwd::parse_pushbuffer` and friends) to cover the graphics-engine
  pushbuffer methods the real driver emits for a minimal 3D workload (a clear + a
  single triangle draw), not just the compute/copy-engine subset already handled.
  Build this against the existing `Arch`/`PushbufferAbi` seam so it's per-generation
  from day one.
- [ ] **Milestone 1b — surface & framebuffer object lifecycle.** Extend the
  Creation-Record-equivalent tracking (kayfabe's `RmGraph`) to cover renderable
  surfaces/framebuffer objects, and route their backing memory through the same
  arena/publish path already used for compute buffers.
- [ ] **Milestone 1c — `Present` port real implementation.** The typed `Present`/
  `SurfaceHandle` seam already exists (`kayfabe-vmm`); implement it for real against
  QEMU's display path (e.g., handing a completed frame to QEMU's GTK/dbus display or a
  DMABUF-style scanout) — build on `kayfabe-vmm-qemu`/`kayfabe-qemu-raw`.
- [ ] **Milestone 1d — fence/sync correctness for graphics.** Graphics workloads have
  different completion-timing characteristics than compute (per-frame, tighter
  latency budget). Extend `kayfabe-completion`'s `FenceArms`/`CompletionQueue` and
  validate the `#12 MAX_FENCE_JUMP` guard still holds under a render loop, not just a
  compute kernel loop.
- [ ] **Milestone 1e — correctness oracle.** Build a differential test: same workload
  run bare-metal (real GPU, no kayfabe) vs. through kayfabe, compared frame-by-frame
  (SSIM or exact hash for deterministic clears/triangles). This becomes the reusable
  harness for all later graphics work, including Phase 2's Windows validation.

**Testing:** conformance suite extended with a graphics-specific `Scenario` DSL branch;
adversarial fuzz corpus extended to graphics-engine pushbuffer methods (this is new
attack surface — treat it with the same suspicion as the existing compute surface, per
`core_security_threat_model.md`). Isolation drills (kill a graphics context mid-frame)
re-run against the existing "kill a render-server worker" pattern.

**Exit criteria (Gate P1):**
- [ ] A real Linux guest app (start with something as simple as `glxgears`-class,
  then a real Vulkan/GL sample) renders and its output is pixel-correct against the
  bare-metal oracle.
- [ ] Present path delivers frames to a host-visible surface with bounded, measured
  per-frame latency.
- [ ] Graphics-engine pushbuffer parsing has fuzz coverage, not just the demo-path
  happy case.
- [ ] Isolation drill: a hostile/malformed graphics submission is refused, not
  forwarded, and does not affect other contexts.

**Non-goals:** Windows, D3D, multiple concurrent tenants, migration, or performance
tuning. Correctness first, on Linux, single workload at a time.

---

### Phase 2 — Windows guest bring-up

**Goal:** the goal your source docs actually named (G1) — a **real, unmodified Windows
NVIDIA driver** boots against the fabricated device and runs D3D-accelerated
workloads. This has never been attempted in the project to date; treat it as
genuinely unproven, not "the same thing as Linux, ported."

**Preconditions:** Phase 1 gate passed (graphics engine + present pipeline proven on
Linux — Windows bring-up should reuse that RM-class coverage, not duplicate it).

**Workstream items:**
- [ ] **Spike: Windows RM transport surface.** Characterize how Windows' NVIDIA driver
  communicates with the GPU compared to Linux's `/dev/nvidiactl` ioctl surface — it is
  routed through the WDDM kernel model (`DxgkDdi*` entry points, `D3DKMTEscape`), not a
  character device. Determine how much of the already-implemented RM/pushbuffer/GSP
  wire protocol is shared vs. how much new surface (VidPN, display-mode RM classes,
  DXGK-specific escapes) is exposed only through this path. **Do this spike before
  committing to a Phase-2 estimate** — it is the single biggest unknown in this
  roadmap, structurally equivalent to the source docs' "D3D11 DDI bridge" unknown.
- [ ] **Guest boot rig.** Windows 10 22H2 / Windows 11 23H2+24H2 guests, driver
  package pre-staged, against the fabricated device. Instrument with ETW
  (`Microsoft-Windows-Kernel-PnP`, `DxgKrnl`) and Driver Verifier, mirroring the rig
  style already used for the Linux bench.
- [ ] **Display/VidPN RM & GSP RPC surface.** Extend `kayfabe-gsp`'s RPC decode and the
  new `RpcCommand → RmEvent` bridge (from Phase 0) to cover the display-mode-setting
  and scanout RPCs a WDDM boot actually exercises, which a headless Linux CUDA/compute
  workload never touches.
- [ ] **DXGI/D3D correctness oracle.** Reuse Phase 1e's differential harness with
  **WARP as the reference oracle** (matching the source docs' own approach) for D3D11
  first, then D3D12/D3D9 as coverage allows.
- [ ] **Windows-specific driver-ABI wire tables.** Extend `kayfabe-abi`'s codegen to
  cover the Windows driver package's version(s), alongside the existing Linux tables —
  this is exactly what the `DriverAbi`/Axis-A seam was built to make cheap.

**Testing:** Driver Verifier clean (standard + special pool) across the boot +
first-triangle + teardown cycle; WARP-differential D3D11 test matrix; ETW trace review
for PnP/DxgKrnl sequencing sanity even before hot-plug (Phase 6) is in scope.

**Exit criteria (Gate P2):**
- [ ] Stock Windows 10 and Windows 11 NVIDIA driver boots against the fabricated
  device with Driver Verifier clean.
- [ ] A real D3D11 workload (start with a WARP-comparable smoke test, grow from there)
  produces correct output.
- [ ] `nvidia-smi`-equivalent and DXGI adapter enumeration report sane state from
  inside the guest.
- [ ] No guest bugcheck across a scripted boot/run/teardown soak (target: 100 cycles,
  matching the rigor of the source docs' own hot-plug gate even though hot-plug itself
  is Phase 6).

**Non-goals:** D3D12, multi-monitor, hot-plug, migration, multiple tenants. Single
static device, single workload class, correctness over completeness.

---

### Phase 3 — Performance & data-plane redesign

**Goal:** close the 22–81× gap. This is scoped as its own phase because the fix is
architectural (the data plane, not the correctness logic), and because chasing
performance before Phases 1–2 are correct would mean optimizing the wrong thing.

**Preconditions:** Phases 1–2 correctness gates passed (don't optimize an unproven
path).

**Workstream items:**
- [ ] **Profile and attribute the current overhead.** The repo already knows small
  kernels are dominated by kayfabe's own doorbell handler; get a proper breakdown
  (host round-trip latency vs. memory-copy vs. synchronization stalls) before
  redesigning anything.
- [ ] **Reduce trap-per-doorbell overhead.** Investigate batching, poll-mode
  completion delivery (the existing `CompletionQueue` is already poll-driven —
  extend that pattern to the doorbell-ring path itself), or coalescing adjacent
  submissions.
- [ ] **Zero-copy data plane for large transfers.** Get guest buffers mapped directly
  into the real GPU's address space where the isolation model allows it, instead of
  staging through host memory copies, for the memory-bound workloads currently paying
  the worst multiplier.
- [ ] **Re-run the perf suite continuously**, not just at the end — track the ratio to
  native on every change, the way the project already tracks correctness.

**Testing:** the existing `cup8` matmul benchmark plus the Phase 1/2 graphics
workloads, benchmarked end-to-end against bare-metal, at multiple problem sizes
(kernel-launch-bound and bandwidth-bound both need to be represented).

**Exit criteria (Gate P3):**
- [ ] Large-kernel / bandwidth-bound workloads within a defined, measured target of
  native (set the number from Phase-3's own profiling data — do not import the source
  docs' "85% GPU-bound" figure without re-deriving it against this architecture's
  actual ceiling).
- [ ] Small-kernel / launch-bound overhead reduced by a measured, order-of-magnitude
  step from the 22–81× baseline, with the remaining gap attributed and understood
  (not just "still slow, unclear why").
- [ ] No correctness regression versus Phase 1/2 oracles as a result of the
  performance changes (re-run those differential suites, don't just trust the perf
  numbers).

---

### Phase 4 — Multi-tenant isolation

**Goal:** turn "multi-tenancy is the thesis, not a result" into a result. This is
scoped as its own phase, after graphics/Windows/perf, because isolation policy is much
easier to validate against a system whose correctness and performance envelope are
already understood.

**Preconditions:** Phase 0's O(n²) DoS fix landed (a shared-resource DoS matters far
more once multiple tenants share the host). Phases 1–3 not strictly required by
dependency, but validating isolation against an incomplete feature set risks false
confidence — recommend running this after at least Phase 2.

**Workstream items:**
- [ ] **Introduce the tenant axis.** Add `TenantId`/`VmId` as a first-class identity
  in `kayfabe-core`'s `RmGraph`/`Proc` model — currently absent entirely. This is a
  core-crate change; do it carefully, preserving the existing per-`Proc` isolation
  invariant (#14, I1) rather than bolting tenancy on top of it.
- [ ] **VRAM/resource budget enforcement per tenant**, at the `kayfabe-isolate`/host
  daemon layer — cap allocations, refuse loudly (per the project's existing
  `CapacityExceeded` pattern) rather than degrade silently.
- [ ] **Real two-VM run.** The project has never attempted this. Start here, not with
  a simulated multi-tenant test: boot two real guest VMs against two isolates on one
  host GPU and validate basic coexistence before layering policy on top.
- [ ] **Crash/fault containment drills**, following the "kill a render-server worker →
  only that context lost" pattern already validated for single-tenant isolates: kill
  one tenant's isolate mid-workload and confirm the other tenant's VM and workload are
  unaffected.
- [ ] **Cross-tenant data-leak testing.** Explicitly test that one tenant cannot read
  another's GPU memory, fences, or command state — extend
  `core_security_threat_model.md` with a tenant-boundary threat model, not just the
  existing single-guest-vs-host one.
- [ ] **Promote the branch-only multi-process work** (`w337-gpu-name-seam`) to
  `master` if Phase 0 cleared it, and extend its scenario (staggered concurrent
  `cuCtxCreate`, sequential process churn) to run across tenant boundaries, not just
  within one guest.

**Testing:** two-VM (and beyond — target the source docs' 8-VM density figure as an
aspirational stretch goal once 2-VM is solid) density soak with per-tenant budget
enforcement; fault-injection drills; a dedicated cross-tenant fuzz/adversarial pass.

**Exit criteria (Gate P4):**
- [ ] Two real, concurrent guest VMs run workloads against one physical GPU with
  enforced VRAM budgets.
- [ ] A crash or hostile submission in one tenant's isolate provably does not affect
  another tenant (demonstrated, not just architecturally argued).
- [ ] No cross-tenant data leak in adversarial testing.
- [ ] Density soak (start at 2, target 8+ per source docs) runs without leak or budget
  violation over an extended (24h-class) window.

---

### Phase 5 — Live migration

**Goal:** kill→restore a live GPU-forwarded context with correct continuation, then
build toward the source docs' tiered model (always-available detach/reattach fallback
→ live snapshot/restore → dirty-tracking live migration).

**Preconditions:** Phases 1–4 gates passed. Migration of an unproven or single-tenant
system isn't meaningful to validate.

**Workstream items:**
- [ ] **State-capture feasibility spike**, structured like the source docs' own `S1`:
  because kayfabe operates below any spec-level capture-replay primitive (there is no
  Vulkan-style `*CaptureReplay*` API at this layer), this spike has to establish
  *what* of the real driver/GPU's internal state (RM object graph, GMMU mappings, GSP
  session state, channel/pushbuffer state) is sufficient to serialize and replay
  faithfully, purely from the protocol kayfabe already observes. This is likely harder
  than the source docs' Venus-based S1, precisely because there's no spec to lean on —
  budget it as a research spike with a real go/no-go gate, not a scoped feature.
- [ ] **New `kayfabe-snap` crate**: creation-record-style object journal (kayfabe's
  `RmGraph` already gives a natural starting point, since it's already a refcounted
  source of truth), quiesce/drain state machine analogous to the source docs' `DRAINING
  → IDLE → SNAPSHOT`, and a versioned on-disk/on-wire snapshot format.
- [ ] **Tier 1 (always-available fallback) first**: detach → migrate the VM without
  the GPU → reattach on the target, accepting a visible GPU-context reset. Ship this
  before attempting live snapshot/restore — it's the source docs' own sequencing and
  it gives a safety net for everything after.
- [ ] **Tier 2 (stop-and-copy via snapshot)** once the feasibility spike passes its
  gate.
- [ ] **Tier 3 (dirty-tracking hybrid)** only after Tier 2 is solid in production —
  explicitly out of scope for this phase's exit criteria; design only.

**Testing:** kill→restore correctness (reuse the Phase 1/2 differential oracles —
frame-sequence or compute-result correctness across the restore boundary); restore
latency and snapshot-size instrumentation; fuzzing of the restore path specifically
(it parses serialized state that, in the live-migration future, crosses a network
boundary — treat it as untrusted input from day one, per the source docs' own framing
of this exact risk).

**Exit criteria (Gate P5):**
- [ ] Tier 1 (detach/reattach) works end-to-end for both a compute and a graphics
  workload.
- [ ] Feasibility spike delivers a go/no-go verdict on live snapshot/restore, with
  measured constants (restore latency, snapshot size, correctness pass rate) — not a
  qualitative opinion.
- [ ] If go: Tier 2 kill→restore is pixel/compute-correct across repeated runs on one
  host.
- [ ] Restore path is fuzzed as untrusted input, with zero crashes/UB in the audited
  unsafe surface.

---

### Phase 6 — Hot-plug

**Goal:** hot-add/remove the virtual GPU device without crashing the guest. Framed
differently from the source docs' version of this phase: there, the team owns the
guest KMD and can harden its PnP handling directly. Here, the guest driver is
NVIDIA's own binary, so this phase is primarily an **empirical characterization**
of how the real driver reacts to hot-plug of hardware that doesn't perfectly match
what it expects — closer to compatibility testing than feature development.

**Preconditions:** Phase 2 gate passed (static Windows boot already correct).

**Workstream items:**
- [ ] **QEMU-side hot-plug support for the fabricated device** — extend
  `kayfabe-vmm-qemu`/the QOM overlay in `qemu/hw/misc/nvkvm/` to support add/remove of
  the device at runtime, not just at boot.
- [ ] **Behavior catalogue**, following the source docs' own S3 methodology directly
  (it's technology-agnostic and transfers cleanly): OS × operation (cold-boot,
  hot-add idle/under-load, orderly remove idle/under-load, surprise remove,
  add/remove churn) × display role, instrumented with ETW + Driver Verifier.
- [ ] **Identify what the real driver requires from the GSP/RM emulation during
  teardown/re-init** that a static boot never exercises (device reset RPCs, GSP
  session re-establishment) — this likely requires extending `kayfabe-gsp` further
  than Phase 2 did.
- [ ] **Surprise-removal safety.** Verify zero bugchecks with in-flight work when the
  emulated device is yanked — this is a property of kayfabe's device model and RM
  forwarding correctly reporting device-lost, not of driver code the project owns, so
  the fix (if needed) lives in the device-emulation layer, not a guest-side patch.

**Testing:** the full OS × operation × display-role matrix from the source docs' S3,
with Driver Verifier (standard + special pool) on throughout.

**Exit criteria (Gate P6):**
- [ ] 100 add/remove cycles per target Windows build: no bugcheck, no leak (verifier
  clean).
- [ ] Surprise removal under active load is safe (no bugcheck) on all target Windows
  builds.
- [ ] Documented, measured behavior catalogue — including any findings that hot-plug
  compatibility with the real driver has hard limits the project cannot fix, since
  those limits directly bound what Phase 7's orchestration layer can promise.

**Non-goals:** if the real driver's PnP handling turns out to have fundamental gaps
against fabricated hardware, this phase's job is to *document that precisely*, not to
force a fix that isn't available (the project doesn't own the guest binary).

---

### Phase 7 — Cluster / orchestration integration

**Goal:** the deployment-shape outcomes from the source docs' KubeVirt-oriented plan,
built technology-agnostically — a node-level daemon owning the GPU, tenant-aware
scheduling metadata, and a device-allocation integration point, without assuming any
particular orchestrator up front.

**Preconditions:** Phase 4 gate passed (multi-tenant isolation proven) and Phase 6
gate passed (hot-plug behavior characterized, since orchestrators depend on it for
node draining/detach).

**Workstream items:**
- [ ] **New `kayfabe-noded`**: per-node daemon that owns the physical GPU(s), spawns
  and tracks per-tenant isolates (building directly on Phase 4's tenant axis),
  enforces budgets, and exposes health/metrics.
- [ ] **Migration-class / capability metadata publishing** — expose what Phase 5/6
  proved (which migration tier is available, hot-plug support status) as queryable
  node metadata, so a scheduler can make placement decisions on it.
- [ ] **Device-allocation integration point.** Pick a concrete target (Kubernetes
  Dynamic Resource Allocation is the closest technology-agnostic equivalent of the
  source docs' DRA-driver plan) and implement the allocation handshake against
  `kayfabe-noded`.
- [ ] **Reconnect/recovery drill at the daemon level**: kill and restart `kayfabe-noded`
  itself and confirm running tenant VMs survive (this is the node-level analogue of
  Phase 4's per-isolate crash containment — don't assume it transfers automatically).
- [ ] **Density validation on a real cluster-shaped topology**, not a single host.

**Testing:** node daemon restart drills; scheduler-integration end-to-end tests
(request → allocate → run → release); multi-node density soak.

**Exit criteria (Gate P7):**
- [ ] A scheduler can request a GPU-bearing VM, have it placed correctly based on
  published node capability, and have it actually run.
- [ ] Node daemon restart does not kill running tenant VMs.
- [ ] Density target met on a real multi-node topology (start at the source docs'
  8-VM-per-node figure as the initial target).

---

### Phase 8 — Hardening & production certification

**Goal:** everything above, minus known critical defects, with the coverage breadth
and assurance evidence a production deployment needs. This phase is mostly
cross-cutting closeout, not new features.

**Workstream items:**
- [ ] **GPU-generation coverage expansion.** Today only GA106/Ampere is validated on
  hardware; use the `Arch` seam (already designed for exactly this) to bring up and
  validate additional generations relevant to your target fleet.
- [ ] **Driver-version coverage expansion**, using the `DriverAbi`/Axis-A codegen
  seam, across the NVIDIA driver versions your deployment needs to support —
  validate the decoupled-version design goal actually holds across real version
  skew, not just in theory.
- [ ] **Full security review**, extending `core_security_threat_model.md` to cover
  everything added since Phase 0 (graphics attack surface, tenant boundaries,
  migration's untrusted-input restore path, node-daemon attack surface).
- [ ] **Fuzzing budget across every new decode/parse surface** added in Phases 1–7
  (graphics pushbuffer methods, Windows-specific GSP RPCs, snapshot restore,
  node-daemon RPC), matching the rigor already applied to the compute path.
- [ ] **Full mutation-gate and TSan re-baseline** against the final crate set, with a
  quotable, dated score (not "pending re-derivation").
- [ ] **Legal/robustness review of the driver-forwarding approach.** Confirm the
  project's stance on running NVIDIA's driver against fabricated hardware remains
  sound against current driver versions — flag if newer driver releases add
  integrity/attestation checks that affect the approach (this was identified as a
  standing risk, not a solved problem).
- [ ] **Documentation pass**: an operator-facing deployment guide, a
  troubleshooting/behavior-catalogue reference (building on Phase 6's findings), and
  an upgrade/compatibility matrix (GPU generation × driver version × Windows build).
- [ ] **Packaging & distribution.** Define how `kayfabe-noded` and the QEMU overlay
  ship to real hosts (package format, versioning, upgrade path) — there is currently
  no install path at all.

**Testing:** the complete `scripts/run_full_suite.sh` run, on every supported GPU
generation, with zero unacknowledged skips; a full multi-tenant, multi-node,
migration-and-hot-plug-exercising soak test lasting at least 72 hours; independent
security review sign-off.

**Exit criteria (Gate P8 / final production gate):** see §6.

---

## 5. Cross-phase workstreams (run continuously, not phase-gated)

- **CI & test discipline:** keep `cargo test --workspace --no-fail-fast` as the number
  of record; never let a red test get silently edited to pass — every fix or
  acceptance needs the dated, linked ruling this codebase already practices.
- **Claim ledger:** every "measured" claim added by this roadmap's work must go
  through `scripts/claim_ledger.py` discipline — measured vs. read-from-source vs.
  neither, tracked, not asserted.
- **Docs hygiene:** `docs/reference/` stays measurements-only; `docs/design/` stays
  design + contact logs (where the design was found wrong); status pages get dated
  corrections in place, matching the existing convention.
- **Security threat model:** update incrementally per phase (noted above), not as a
  single Phase-8 catch-up — a threat model written after the fact tends to rationalize
  the existing design rather than challenge it.

---

## 6. Definition of "Production Ready" (final gate)

All of the following must be true simultaneously, each with a dated, hardware-measured
result — not a design claim:

- [ ] **G1** D3D9/11/12 workloads run correctly in Windows 10/11 guests (Phase 2).
- [ ] **G2** Performance target met and measured against native, for both
  launch-bound and bandwidth-bound workload classes (Phase 3).
- [ ] **G3** Multi-tenant density target met with enforced budgets and zero
  cross-tenant leaks under adversarial testing (Phase 4, validated at scale in
  Phase 7).
- [ ] **G4** Host isolation holds under fault injection at every layer (isolate,
  tenant, node daemon) with zero privilege escalation findings from the Phase 8
  security review.
- [ ] **G5** Live migration Tier 1 always available; Tier 2 (or higher) working and
  measured where the Phase 5 feasibility gate said go.
- [ ] **G6** Hot-plug behavior catalogue complete for all target Windows builds, with
  the 100-cycle clean bar met on every one that isn't documented as a hard vendor-driver
  limitation.
- [ ] **G7** A real scheduler can place, run, and release GPU-bearing VMs against
  `kayfabe-noded` on a real multi-node cluster.
- [ ] **G8** No custom guest driver to sign — reconfirm this advantage still holds
  (i.e., nothing in Phases 1–7 quietly introduced a guest-side patch or shim).
- [ ] **G9** GPU-generation and driver-version coverage matrix published and validated
  for the target fleet.
- [ ] `cargo test --workspace` and `scripts/run_full_suite.sh` both clean, zero
  unacknowledged skips, on every supported GPU generation.
- [ ] Mutation score and TSan results current, dated, and above their agreed floors.
- [ ] Full fuzz corpus across every decode/parse surface added, run to a defined time
  budget with zero crashes/UB.
- [ ] 72-hour multi-tenant, multi-node soak, exercising migration and hot-plug, clean.
- [ ] Independent security review sign-off.
- [ ] Operator documentation, troubleshooting guide, and packaging/install path
  complete.

Only when every box above is checked, with a citation to the measurement that proved
it, should this be called production ready.

---

## 7. Task template (for turning workstream items into Claude Code tickets)

```
Title: [Phase] – [Workstream item, verbatim from this doc]

Context:
  - Link to this roadmap section
  - Link to relevant docs/design/*.md if one exists
  - Crate(s) touched:

Acceptance criteria:
  - [ ] (copied from this doc's exit criteria for the relevant item)
  - [ ] cargo test --workspace --no-fail-fast clean, or new failures carry a linked ruling
  - [ ] No unsafe added outside kayfabe-linux-raw / kayfabe-qemu-raw
  - [ ] New event/table classes are capacity-bounded and MISS/DEFER-classified
  - [ ] docs/reference/ updated with any new hardware measurement, dated

Out of scope:
  - (copy the phase's Non-goals section)
```

---

## 8. Open risks carried into this plan

- **Windows RM transport is the single largest unvalidated assumption** (Phase 2). If
  the WDDM escape surface diverges heavily from the Linux ioctl surface already
  reverse-engineered, Phase 2's effort could be closer to "start over" than "extend."
  Budget the Phase 2 spike accordingly and get its verdict before committing further
  phases' schedules.
- **Live migration (Phase 5) has no spec to lean on**, unlike a Venus-based approach.
  Treat the feasibility spike's go/no-go as real — a "no" should trigger falling back
  to Tier-1-only migration as a permanent, not temporary, position.
- **Hot-plug (Phase 6) may hit a hard ceiling** set by the real driver's own PnP
  assumptions, which this project cannot patch. Document limits precisely rather than
  treating them as bugs to fix.
- **Driver-integrity checks are a standing external risk** (Phase 8): a future NVIDIA
  driver update could add checks that break the fabricated-hardware approach entirely.
  This isn't fixable in-project; it's a monitoring and contingency-planning item.
