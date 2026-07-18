import { apiFetch } from "@/lib/api-client";
import type {
  HelpAudioStatus,
  HelpTopicDetail,
  HelpTopicSummary,
} from "@/types/api";

export function getHelpTopics() {
  return apiFetch<HelpTopicSummary[]>("/help/topics");
}

export function getHelpTopic(topicId: string) {
  return apiFetch<HelpTopicDetail>(`/help/topics/${topicId}`);
}

/** Read current narration state (does not start generation). */
export function getHelpAudio(topicId: string) {
  return apiFetch<HelpAudioStatus>(`/help/topics/${topicId}/audio`);
}

/** Kick off generate-on-first-play; returns cached audio if already present. */
export function startHelpAudio(topicId: string) {
  return apiFetch<HelpAudioStatus>(`/help/topics/${topicId}/audio`, {
    method: "POST",
  });
}
