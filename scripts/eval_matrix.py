"""Headless matrix: run every built-in agent across every scenario seed.

Usage:
    PYTHONPATH=backend python scripts/eval_matrix.py [seed]
"""

from __future__ import annotations

import sys

from simworld.agents.base import AgentContext
from simworld.agents.builtins import AGENT_METADATA, make_builtin
from simworld.engine.actions import Action
from simworld.engine.scenarios import SCENARIOS, build_world


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    for scenario in SCENARIOS:
        for meta in AGENT_METADATA:
            if scenario["kind"] not in meta["environments"]:
                continue
            world = build_world(scenario["id"], seed, None)
            agent = make_builtin(meta["id"])
            for _ in range(400):
                observation = world.observation()
                decision = agent.decide(
                    observation, observation["legal_actions"], AgentContext("matrix", world.step)
                )
                world.apply(Action.parse(decision.action))
                if world.status != "running":
                    break
            metrics = world.metrics()
            if world.kind == "city_logistics":
                summary = (
                    f"del={metrics['packages_delivered']}/{metrics['packages_total']} "
                    f"ontime={metrics['packages_on_time']} inv={metrics['invalid_actions']} "
                    f"fuel={metrics['fuel_consumed_l']} steps={metrics['steps']}"
                )
            else:
                summary = (
                    f"throughput={metrics['throughput_rate']} wait={metrics['avg_wait_ticks']} "
                    f"violations={metrics['rule_violations']} steps={metrics['steps']}"
                )
            print(
                f"{scenario['id']:38s} {meta['id']:16s} {world.status:9s} "
                f"{world.terminal_reason or '-':16s} {summary}"
            )


if __name__ == "__main__":
    main()