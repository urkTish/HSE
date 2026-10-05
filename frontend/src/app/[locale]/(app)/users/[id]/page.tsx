import { initRequestLocale } from "@/i18n/server";
import { UserDetail } from "@/components/users/user-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <UserDetail userId={p.id} />;
}
