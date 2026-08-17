import { cpSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const src = join(process.cwd(), "node_modules", "@rdkit", "rdkit", "Code", "MinimalLib", "dist");
if (!existsSync(join(src, "RDKit_minimal.wasm"))) {
  throw new Error(`RDKit dist not found at ${src} — did npm install run?`);
}
mkdirSync("public/rdkit", { recursive: true });
cpSync(src, "public/rdkit", { recursive: true });
