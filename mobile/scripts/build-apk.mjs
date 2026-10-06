import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const variant = process.argv[2];
if (!["release", "debug"].includes(variant)) throw new Error("需要指定 release 或 debug");
const task = variant === "release" ? ":app:assembleRelease" : ":app:assembleDebug";
const windows = process.platform === "win32";
const result = spawnSync(windows ? `gradlew.bat ${task}` : "./gradlew", windows ? [] : [task], {
  cwd: fileURLToPath(new URL("../android/", import.meta.url)),
  shell: windows,
  stdio: "inherit",
});
if (result.error) throw result.error;
if (result.signal) throw new Error(`Gradle 被信号 ${result.signal} 终止`);
process.exit(result.status);
