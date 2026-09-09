import fs from "node:fs";
import path from "node:path";


let temporaryCounter = 0;


export function assertSafeGeneratedFileTarget(target, label = "generated file") {
  if (!fs.existsSync(target)) return;
  const metadata = fs.lstatSync(target);
  if (metadata.isSymbolicLink()) {
    throw new Error(`${label} must not be a symlink.`);
  }
  if (!metadata.isFile()) {
    throw new Error(`${label} must be a regular file.`);
  }
  if (metadata.nlink !== 1) {
    throw new Error(`${label} must not have multiple hard links.`);
  }
}


export function writeGeneratedFileAtomic(target, content, label = "generated file") {
  const parent = path.dirname(target);
  assertSafeGeneratedFileTarget(target, label);
  const temporary = path.join(
    parent,
    `.${path.basename(target)}.${process.pid}.${temporaryCounter += 1}.tmp`,
  );
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, content);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    assertSafeGeneratedFileTarget(target, label);
    fs.renameSync(temporary, target);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try {
      fs.unlinkSync(temporary);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
}
