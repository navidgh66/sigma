# Tasks — axis token-economy report

Domain: ai-agent-engineering. Ordered; each maps to spec requirements + BDD scenarios.

- [x] T1 (ai-agent-engineering): add five Optional[bool] effect fields (logic_ok, advised, e2e_ok, simplified, test_written) to TrajectoryStep + lenient parsing in build_step [scenario: old trajectory without effect fields still reads]
- [x] T2 (ai-agent-engineering): populate the effect fields on each role="cycle" step in loop.record_cycle_steps from CycleOutcome
- [x] T3 (ai-agent-engineering): new pure module cli/axis_economy.py — AxisRow, AxisEconomy dataclasses + build_economy value model + flagging [scenario: economy report flags an idle expensive axis]
- [x] T4 (ai-agent-engineering): AxisEconomy.render() markdown report — earning vs review sections, unmeasured labeling, core never flagged [scenario: core axes are never flagged]
- [x] T5 (ai-agent-engineering): wire sigma trajectory --economy (+ --json) into cmd_trajectory + argparse [scenario: JSON output composes with economy]
- [x] T6 (ai-agent-engineering): tests/test_axis_economy.py covering all BDD scenarios + record_cycle_steps effect-field test [scenario: unmeasured axis is not estimated]
- [x] T7 (ai-agent-engineering): docs sync — CLAUDE.md gotcha + layout, README, version bump; full suite green + ruff clean [scenario: empty trajectory is safe]
