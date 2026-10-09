import { initRequestLocale } from "@/i18n/server";
import { StopWorkOrderPage } from "@/components/field/inspect";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <StopWorkOrderPage id={p.id} />;
}
