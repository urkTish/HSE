import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MeetingListPage } from "@/components/meetings/meeting-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MeetingListPage />;
}
