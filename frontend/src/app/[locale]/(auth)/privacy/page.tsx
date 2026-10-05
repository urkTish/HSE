import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PrivacyAck } from "@/components/auth/privacy-ack";

export default async function PrivacyPage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PrivacyAck />;
}
