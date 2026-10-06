import { initRequestLocale } from "@/i18n/server";
import { InvestigationPage } from "@/components/incidents/investigation-page";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <InvestigationPage id={p.id} />;
}
