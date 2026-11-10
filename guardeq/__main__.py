"""Command line: python -m guardeq <command> [--profile smoke|reduced|full] [--judge local|groq]"""
from __future__ import annotations

import argparse
import sys
import time

from . import llm
from .config import PROFILES, load_config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="guardeq", description="Equilibrium guardrail placement for LLM agents.")
    parser.add_argument("command", choices=["all", "payoffs", "eval", "robust", "analyze", "demo", "report",
                                            "doctor", "status"],
                        help="all = run every step, then build figures, demo data and the report")
    parser.add_argument("--profile", choices=sorted(PROFILES), default=None, help="run size (default: smoke)")
    parser.add_argument("--judge", choices=["local", "groq"], default=None, help="where the LLM judge runs")
    parser.add_argument("--agent", default=None, help="agent model spec, e.g. ollama:gemma4")
    parser.add_argument("--attacker-info", choices=["full", "policy"], default=None,
                        help="what the LLM attacker is told besides the policy")
    args = parser.parse_args(argv)
    cfg = load_config(args.profile, judge_backend=args.judge, agent_model=args.agent,
                      attacker_info=args.attacker_info)

    from . import analysis, demo, doctor, experiments, report

    start = time.time()
    try:
        if args.command == "doctor":
            return doctor.run(cfg)
        if args.command == "status":
            return doctor.status(cfg)
        if args.command in ("all", "payoffs", "eval", "robust"):
            steps = {"all": ("payoffs", "solve", "eval", "robust"), "payoffs": ("payoffs", "solve"),
                     "eval": ("solve", "eval"), "robust": ("solve", "robust")}[args.command]
            experiments.run_all(cfg, steps)
        if args.command in ("all", "analyze", "payoffs", "eval", "robust"):
            made = analysis.make_figures(cfg)
            print(f"figures: {len(made)} written to {cfg.results_dir / 'figures'}")
        if args.command in ("all", "demo"):
            print(f"demo data: {demo.build(cfg)}")
        if args.command in ("all", "report"):
            print(f"report: {report.build(cfg)}")
    except llm.LLMError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Finished trials are saved; run the same command again to resume.")
        return 130
    print(f"done in {(time.time() - start) / 60:.1f} min  "
          f"({llm.stats['cached']}/{llm.stats['calls']} model calls served from cache)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
