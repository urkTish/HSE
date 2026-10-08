import { initRequestLocale } from "@/i18n/server";
import { AppointmentDetail } from "@/components/ptw/appointments";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AppointmentDetail id={p.id} />;
}
