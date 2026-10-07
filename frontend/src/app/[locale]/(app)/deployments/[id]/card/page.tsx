import { initRequestLocale } from "@/i18n/server";
import { AccessCardPrint } from "@/components/access/workers";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AccessCardPrint deploymentId={p.id} />;
}
