import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const encoded = process.env.PILOG_ANDROID_KEYSTORE_BASE64;
const destination = process.env.PILOG_ANDROID_KEYSTORE;
if (!encoded) throw new Error("缺少 PILOG_ANDROID_KEYSTORE_BASE64 secret");
if (!destination) throw new Error("缺少 PILOG_ANDROID_KEYSTORE 路径");

mkdirSync(dirname(destination), { recursive: true });
writeFileSync(destination, Buffer.from(encoded, "base64"), { mode: 0o600, flag: "wx" });
