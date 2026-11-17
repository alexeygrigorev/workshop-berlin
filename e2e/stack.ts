import { execFileSync } from "node:child_process";
import path from "node:path";

// Dedicated compose project, ports and volume so the e2e stack never touches the dev stack
// (project "wswe", ports 8000/5432, volume wswe_pgdata).
export const E2E_PORT = 18000;
export const E2E_DB_PORT = 15432;
export const E2E_PROJECT = "wswe-e2e";
export const E2E_VOLUME = "wswe_e2e_pgdata";

/** When set, tests run against that already-running stack and docker is not started or stopped. */
export const REUSE_URL = process.env.E2E_BASE_URL;
/** When set (e.g. "wswe:<sha>"), compose runs this already-built image instead of building one. */
export const PREBUILT_IMAGE = process.env.WSWE_IMAGE;
export const BASE_URL = REUSE_URL ?? `http://localhost:${E2E_PORT}`;

export const composeEnv = {
  ...process.env,
  WSWE_APP_PORT: String(E2E_PORT),
  WSWE_DB_PORT: String(E2E_DB_PORT),
  WSWE_PGDATA_VOLUME: E2E_VOLUME,
};

export function compose(args: string[]): void {
  execFileSync("docker", ["compose", "-p", E2E_PROJECT, ...args], {
    cwd: path.resolve(__dirname, ".."),
    env: composeEnv,
    stdio: "inherit",
  });
}

/** Optional expected image ID (sha256 config digest) of the prebuilt image, from the CI build-image job. */
export const EXPECTED_IMAGE_ID = process.env.WSWE_IMAGE_ID;

function docker(args: string[]): string {
  return execFileSync("docker", args, {
    cwd: path.resolve(__dirname, ".."),
    env: composeEnv,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
}

/** WSWE_IMAGE set: the image must already exist locally (never built, never pulled) and match WSWE_IMAGE_ID. */
export function assertPrebuiltImage(): string {
  if (!PREBUILT_IMAGE) throw new Error("assertPrebuiltImage called without WSWE_IMAGE");
  let id: string;
  try {
    id = docker(["image", "inspect", "--format", "{{.Id}}", PREBUILT_IMAGE]);
  } catch {
    throw new Error(`WSWE_IMAGE=${PREBUILT_IMAGE} is not present locally; refusing to build or pull it`);
  }
  if (EXPECTED_IMAGE_ID && id !== EXPECTED_IMAGE_ID) {
    throw new Error(`image ID mismatch for ${PREBUILT_IMAGE}: EXPECTED ${EXPECTED_IMAGE_ID} ACTUAL ${id}`);
  }
  return id;
}

/** After the stack is up: the running app container must be using exactly the expected image ID. */
export function assertRunningImage(expectedId: string): void {
  const cid = execFileSync("docker", ["compose", "-p", E2E_PROJECT, "ps", "-q", "app"], {
    cwd: path.resolve(__dirname, ".."),
    env: composeEnv,
    encoding: "utf8",
  }).trim();
  if (!cid) throw new Error("no running app container found in the e2e project");
  const actual = docker(["inspect", "--format", "{{.Image}}", cid]);
  console.log(`e2e image check: EXPECTED ${expectedId} ACTUAL ${actual}`);
  if (actual !== expectedId) {
    throw new Error(`app container runs the wrong image: EXPECTED ${expectedId} ACTUAL ${actual}`);
  }
}
