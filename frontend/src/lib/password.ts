/** Client-side mirror of spec rule 2 (server is authoritative, including the breached-password list). */
export function meetsPasswordPolicy(pw: string): boolean {
  if (pw.length < 12) return false;
  const classes = [/[A-Z]/, /[a-z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  return classes >= 3;
}
