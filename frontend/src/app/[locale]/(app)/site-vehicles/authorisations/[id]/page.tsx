import { initRequestLocale } from "@/i18n/server";
import { AuthorisationDetailPage } from "@/components/site-vehicles/authorisations";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AuthorisationDetailPage id={p.id} />;
}
