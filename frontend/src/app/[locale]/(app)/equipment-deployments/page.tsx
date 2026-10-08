import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DeploymentListPage } from "@/components/cert/deployments";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DeploymentListPage />;
}
