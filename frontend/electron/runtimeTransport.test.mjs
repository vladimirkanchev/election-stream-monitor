import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const mainPath = path.join(__dirname, "main.mjs");

describe("Electron runtime transport", () => {
  it("does not keep CLI transport helpers in normal runtime handlers", async () => {
    const source = await readFile(mainPath, "utf-8");

    expect(source).not.toContain("runJsonCommand(");
    expect(source).not.toContain("cliOperation:");
  });
});
