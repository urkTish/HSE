"use client";
import { ErrorState, LoadingState } from "@/components/common/states";
import { EngagementForm } from "@/components/engagements/engagement-form";
import { useEngagement } from "@/lib/api/queries";

export function EngagementCreate({ projectId }: { projectId: string }) {
  return <EngagementForm projectId={projectId} />;
}

export function EngagementEdit({ projectId, engagementId }: { projectId: string; engagementId: string }) {
  const q = useEngagement(engagementId);
  if (q.isError) return <ErrorState error={q.error} />;
  if (!q.data) return <LoadingState />;
  return <EngagementForm projectId={projectId} engagement={q.data} />;
}
