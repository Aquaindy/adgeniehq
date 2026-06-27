import { ProviderCredentialsCard } from "@/features/settings/ProviderCredentialsCard";
import { useWorkspaceStore } from "@/stores/workspace-store";

/**
 * BYOK page — workspace-scoped provider credentials (OpenAI, Anthropic,
 * Google AI). AdGenieHQ uses these on the workspace's behalf for LLM-backed
 * agents and skills.
 */
export function ProviderCredentialsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  if (!workspaceId) {
    return <div className="text-sm text-slate-500">Select a workspace first.</div>;
  }
  return (
    <div className="flex flex-col gap-6">
      <ProviderCredentialsCard workspaceId={workspaceId} />
    </div>
  );
}
