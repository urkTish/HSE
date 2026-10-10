import { initRequestLocale } from "@/i18n/server";
import { ScorecardPage } from "@/components/scorecard/cards";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ScorecardPage id={p.id} />;
}
