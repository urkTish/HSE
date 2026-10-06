"use client";
import { ProjectGate } from "@/components/common/project-gate";
import { MeetingList } from "@/components/meetings/meetings";

export function MeetingListPage() {
  return <ProjectGate>{(p) => <MeetingList project={p} />}</ProjectGate>;
}
