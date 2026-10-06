import { initRequestLocale } from "@/i18n/server";
import { MeetingDetail } from "@/components/meetings/meetings";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MeetingDetail id={p.id} />;
}
