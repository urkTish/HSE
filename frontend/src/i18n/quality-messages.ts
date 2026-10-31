/** 8-quality §3.3a: deep merge of the Quality parts' message files under the `quality` namespace. */
export type MessageTree = { [key: string]: string | MessageTree };

function mergeInto(target: MessageTree, source: MessageTree, path: string): void {
  for (const [key, value] of Object.entries(source)) {
    const here = path ? `${path}.${key}` : key;
    const existing = target[key];
    if (existing === undefined) {
      target[key] = typeof value === "string" ? value : mergeCopy(value, here);
    } else if (typeof existing === "string" || typeof value === "string") {
      throw new Error(`Quality message key defined twice: quality.${here}`);
    } else {
      mergeInto(existing, value, here);
    }
  }
}

function mergeCopy(value: MessageTree, path: string): MessageTree {
  const out: MessageTree = {};
  mergeInto(out, value, path);
  return out;
}

export function mergeQuality(base: MessageTree, parts: MessageTree[]): MessageTree {
  const quality: MessageTree = {};
  for (const part of parts) mergeInto(quality, part, "");
  if (base.quality !== undefined) throw new Error("messages/<locale>.json must not define `quality`");
  return { ...base, quality };
}
