import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { listRecommendations } from "@/lib/agents";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { RecommendationPublic } from "@/types/api";

import { RiskPill } from "@/features/agents/AgentRunDetailPage";
import { ApprovalActions } from "@/features/recommendations/ApprovalActions";

export function RecommendationsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);

  const recs = useQuery({
    queryKey: ["recommendations", workspaceId],
    queryFn: () => listRecommendations(workspaceId!),
    enabled: !!workspaceId,
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Recommendations</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          What your agents found
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Approve, reject, or open a recommendation to edit it before applying. Role gating: low →
          Marketer+, medium → Admin+, high → Owner.
        </p>
      </header>

      {recs.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : recs.data && recs.data.length > 0 ? (
        <RiskGroups recommendations={recs.data} />
      ) : (
        <EmptyState
          title="No recommendations yet"
          description="Run an agent from the Agents dashboard to generate findings."
          action={
            <Link to="/agents">
              <Button>Go to agents</Button>
            </Link>
          }
        />
      )}
    </div>
  );
}

function RiskGroups({ recommendations }: { recommendations: RecommendationPublic[] }) {
  const high = recommendations.filter((r) => r.risk_level === "high");
  const medium = recommendations.filter((r) => r.risk_level === "medium");
  const low = recommendations.filter((r) => r.risk_level === "low");

  return (
    <div className="flex flex-col gap-6">
      {[
        { title: "High risk", items: high },
        { title: "Medium risk", items: medium },
        { title: "Low risk", items: low },
      ].map((group) =>
        group.items.length === 0 ? null : (
          <section key={group.title}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              {group.title} · {group.items.length}
            </h2>
            <ul className="flex flex-col gap-3">
              {group.items.map((rec) => (
                <li key={rec.id}>
                  <Card>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <CardHeader title={rec.title} subtitle={rec.summary} />
                        <dl className="mt-3 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
                          <div>
                            <dt className="text-slate-400">Expected impact</dt>
                            <dd className="mt-0.5 text-slate-700">{rec.expected_impact}</dd>
                          </div>
                          <div>
                            <dt className="text-slate-400">Suggested action</dt>
                            <dd className="mt-0.5 text-slate-700">{rec.suggested_action}</dd>
                          </div>
                          <div>
                            <dt className="text-slate-400">Source</dt>
                            <dd className="mt-0.5 flex items-center gap-3">
                              <Link
                                to={`/agents/runs/${rec.agent_run_id}`}
                                className="font-medium text-grape-700 hover:text-grape-800"
                              >
                                Agent run →
                              </Link>
                              <Link
                                to={`/recommendations/${rec.id}`}
                                className="font-medium text-grape-700 hover:text-grape-800"
                              >
                                Open detail →
                              </Link>
                            </dd>
                          </div>
                          <div>
                            <dt className="text-slate-400">Created</dt>
                            <dd className="mt-0.5 text-slate-700">
                              {new Date(rec.created_at).toLocaleString()}
                            </dd>
                          </div>
                        </dl>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <RiskPill level={rec.risk_level} />
                        <ApprovalActions rec={rec} />
                      </div>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        ),
      )}
    </div>
  );
}
