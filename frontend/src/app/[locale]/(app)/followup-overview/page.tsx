import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FollowupOverviewPage } from "@/components/followup/overview";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FollowupOverviewPage />;
}
