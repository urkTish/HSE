// Requests outside any locale (rare: the proxy prefixes every path) fall back to a minimal page.
export default function GlobalNotFound() {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", padding: "2rem" }}>
        <h1>404</h1>
      </body>
    </html>
  );
}
