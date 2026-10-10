import { initRequestLocale } from "@/i18n/server";
import { LessonPage } from "@/components/followup/lessons";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <LessonPage id={p.id} />;
}
