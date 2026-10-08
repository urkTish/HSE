import { initRequestLocale } from "@/i18n/server";
import { DeploymentDetail } from "@/components/cert/deployments";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <DeploymentDetail id={p.id} />;
}
