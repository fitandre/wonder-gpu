#!/usr/bin/env python3
"""
Planning-level token/cost estimate for the whole roadmap, read from
task_graph.yaml. This is NOT the authoritative spend -- once the loop is
running, token_ledger.py records real usage from Vertex's response objects
and that ledger is the source of truth. Re-run this script after editing
task_graph.yaml's assumptions (e.g. after Phase 0 gives you real numbers to
calibrate the rest against).

Usage:
    python estimate_cost.py                  # no caching assumed
    python estimate_cost.py --cache-hit 0.4  # assume 40% of input tokens are cache hits
"""
import argparse
import yaml
from pricing import PRICING, call_cost, GKE_G2_STANDARD_4_ON_DEMAND_PER_HOUR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-hit", type=float, default=0.0,
                     help="assumed fraction of input tokens served from prompt cache")
    ap.add_argument("--graph", default="task_graph.yaml")
    args = ap.parse_args()

    with open(args.graph) as f:
        graph = yaml.safe_load(f)

    totals = {m: {"calls": 0, "in_tok": 0, "out_tok": 0, "cost": 0.0} for m in PRICING}
    per_phase_rows = []
    total_gpu_hours = 0

    for phase in graph["phases"]:
        phase_cost = 0.0
        phase_in = phase_out = 0
        for model, b in phase["model_buckets"].items():
            calls = b["calls"]
            in_tok = calls * b["avg_input_tokens"]
            out_tok = calls * b["avg_output_tokens"]
            cost = call_cost(model, in_tok, out_tok, cached_input_fraction=args.cache_hit)

            totals[model]["calls"] += calls
            totals[model]["in_tok"] += in_tok
            totals[model]["out_tok"] += out_tok
            totals[model]["cost"] += cost

            phase_cost += cost
            phase_in += in_tok
            phase_out += out_tok

        total_gpu_hours += phase.get("est_gpu_hours", 0)
        per_phase_rows.append((phase["id"], phase["title"], phase_in, phase_out, phase_cost))

    cache_note = f" (cache-hit={args.cache_hit:.0%})" if args.cache_hit else " (no caching)"
    print(f"\n=== Per-phase token/cost estimate{cache_note} ===")
    print(f"{'Phase':<5}{'Title':<38}{'Input tok':>12}{'Output tok':>12}{'Cost (USD)':>13}")
    grand_cost = 0.0
    grand_in = grand_out = 0
    for pid, title, in_tok, out_tok, cost in per_phase_rows:
        print(f"{pid:<5}{title:<38}{in_tok:>12,}{out_tok:>12,}{cost:>13,.2f}")
        grand_cost += cost
        grand_in += in_tok
        grand_out += out_tok
    print("-" * 80)
    print(f"{'TOTAL':<5}{'':<38}{grand_in:>12,}{grand_out:>12,}{grand_cost:>13,.2f}")

    print(f"\n=== Per-model totals{cache_note} ===")
    print(f"{'Model':<12}{'Calls':>8}{'Input tok':>14}{'Output tok':>14}{'Cost (USD)':>13}")
    for model, t in totals.items():
        print(f"{model:<12}{t['calls']:>8,}{t['in_tok']:>14,}{t['out_tok']:>14,}{t['cost']:>13,.2f}")
    print("-" * 61)
    print(f"{'TOTAL':<12}{sum(t['calls'] for t in totals.values()):>8,}"
          f"{sum(t['in_tok'] for t in totals.values()):>14,}"
          f"{sum(t['out_tok'] for t in totals.values()):>14,}"
          f"{sum(t['cost'] for t in totals.values()):>13,.2f}")

    gpu_cost = total_gpu_hours * GKE_G2_STANDARD_4_ON_DEMAND_PER_HOUR
    print(f"\n=== GKE L4 (g2-standard-4) test infra estimate ===")
    print(f"Estimated GPU-hours across all phases: {total_gpu_hours:,}")
    print(f"On-demand cost @ ${GKE_G2_STANDARD_4_ON_DEMAND_PER_HOUR}/hr: ${gpu_cost:,.2f}")
    print(f"(spot/preemptible for non-soak jobs could cut this materially -- see docs/gcp_setup.md)")

    print(f"\nGRAND TOTAL (tokens + GPU infra, no caching if --cache-hit not passed): "
          f"${grand_cost + gpu_cost:,.2f}\n")


if __name__ == "__main__":
    main()
