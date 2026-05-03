# Agent system

> **Status:** placeholder — implementation lands in Milestone 4.

The canonical specification of every agent and skill lives in [CLAUDE.md §4–§5](../CLAUDE.md). This doc will be filled in as the orchestrator and skill registry are built.

## Planned modules

```
apps/api/app/
├── agents/
│   ├── orchestrator.py          Master Growth Orchestrator
│   ├── base_agent.py            Common base class
│   ├── seo_geo_agent.py
│   ├── paid_ads_agent.py
│   ├── website_agent.py
│   ├── market_intelligence_agent.py
│   ├── icp_persona_agent.py
│   ├── creative_strategy_agent.py
│   ├── campaign_builder_agent.py
│   ├── tracking_attribution_agent.py
│   ├── budget_guardian_agent.py
│   └── reporting_agent.py
└── skills/
    ├── registry.py              Skill registry
    ├── base_skill.py
    └── ...                      individual skill modules
```

## Persistence

- `agent_runs` — one row per orchestrator/agent invocation (input, output, model, tokens, cost, status).
- `agent_tasks` — sub-tasks an orchestrator dispatched to specific skills.
- `skill_outputs` — structured outputs.
- `recommendations` — user-facing items derived from outputs; routed through `approvals`.
- `audit_logs` — every external action and approval transition.

## Safety

No agent may directly mutate an external platform without an `approvals` row in state `approved` (or an Autopilot rule whose limits cover the action). The orchestrator enforces this before dispatching any "execute" skill.
