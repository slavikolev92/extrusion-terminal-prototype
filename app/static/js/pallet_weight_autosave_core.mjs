export function parsePalletWeightDraft(rawValue) {
  const trimmed = String(rawValue ?? "").trim();
  if (!trimmed) return { kind: "blank" };
  const match = trimmed.match(/^(-?)([0-9]+)(?:[.,]([0-9]{1,2}))?$/);
  if (!match) {
    return { kind: "invalid", reason: "format" };
  }
  const [, sign, whole, fraction = "0"] = match;
  if (sign) return { kind: "invalid", reason: "minimum" };
  const significantWhole = whole.replace(/^0+/, "") || "0";
  if (significantWhole.length > 3) {
    return { kind: "invalid", reason: "maximum" };
  }
  const wholeNumber = Number(significantWhole);
  const fractionHundredths = Number(fraction.padEnd(2, "0"));
  const rawHundredths = wholeNumber * 100 + fractionHundredths;
  if (rawHundredths > 10000) return { kind: "invalid", reason: "maximum" };
  if (rawHundredths < 1) return { kind: "invalid", reason: "minimum" };
  return { kind: "valid", hundredths: rawHundredths };
}


export function createSerializedTaskQueue() {
  let tail = Promise.resolve();
  let pending = 0;
  return {
    enqueue(task) {
      pending += 1;
      const current = tail.catch(() => undefined).then(task);
      tail = current.finally(() => { pending -= 1; });
      return current;
    },
    whenIdle() {
      return tail.catch(() => undefined);
    },
    pendingCount() {
      return pending;
    },
  };
}
