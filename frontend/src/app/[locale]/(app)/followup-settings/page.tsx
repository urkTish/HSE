import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FollowupSettingsPage } from "@/components/followup/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FollowupSettingsPage />;
}
