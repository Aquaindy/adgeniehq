import { apiFetch } from "@/lib/api-client";
import type {
  ContentDraftPublic,
  GenerateSocialPackRequest,
  SocialFormat,
  SocialPackResponse,
  SocialPlatformPublic,
  VideoScript,
} from "@/types/api";

export function listSocialPlatforms(
  workspaceId: string,
  format?: SocialFormat,
) {
  const qs = format ? `?format=${format}` : "";
  return apiFetch<SocialPlatformPublic[]>(
    `/workspaces/${workspaceId}/social/platforms${qs}`,
  );
}

export function generateSocialPack(
  workspaceId: string,
  payload: GenerateSocialPackRequest,
) {
  return apiFetch<SocialPackResponse>(
    `/workspaces/${workspaceId}/social/generate`,
    { method: "POST", body: payload },
  );
}

/** Pull the structured script off a `short_video_script` draft, if present.
 * Returns null for post drafts and for scripts the agent couldn't structure. */
export function readVideoScript(draft: ContentDraftPublic): VideoScript | null {
  if (draft.type !== "short_video_script") return null;
  const script = draft.seo_metadata?.script as VideoScript | undefined;
  if (!script || !Array.isArray(script.beats) || !script.hook) return null;
  return script;
}

/** The post exactly as it should be pasted: body followed by its hashtags. */
export function composeForClipboard(draft: ContentDraftPublic): string {
  const tags = draft.hashtags ?? [];
  if (tags.length === 0) return draft.body;
  return `${draft.body}\n\n${tags.join(" ")}`;
}
