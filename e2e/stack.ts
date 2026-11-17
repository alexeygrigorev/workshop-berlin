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
