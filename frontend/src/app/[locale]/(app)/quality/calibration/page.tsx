import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CalibrationPage } from "@/components/quality/q2/calibration";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CalibrationPage />;
}
