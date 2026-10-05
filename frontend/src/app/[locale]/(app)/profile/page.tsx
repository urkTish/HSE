import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { Profile } from "@/components/profile/profile";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <Profile />;
}
