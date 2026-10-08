import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AppointmentListPage } from "@/components/ptw/appointments";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AppointmentListPage />;
}
