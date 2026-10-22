/**
 * Throw-away licence signing key for the e2e run (D-297). Generated once, before the servers and workers
 * start (imported by playwright.config.ts, like clock.ts): the API gets the public half as LICENCE_PUBLIC_KEY,
 * the specs sign test keys with the private half. Never the vendor's real key, and nothing is written to disk.
 */
import { generateKeyPairSync } from "node:crypto";

if (!process.env.E2E_LICENCE_PRIVATE_KEY) {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  process.env.LICENCE_PUBLIC_KEY = publicKey.export({ type: "spki", format: "pem" }).toString();
  process.env.E2E_LICENCE_PRIVATE_KEY = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
}
