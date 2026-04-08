import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const projectRoot = process.cwd();
const configPath = path.join(projectRoot, "config", "downloaders.json");

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--provider") parsed.provider = argv[++index];
    else if (token === "--post-login-ready") parsed.postLoginReady = argv[++index];
    else if (token === "--date-from-input") parsed.dateFromInput = argv[++index];
    else if (token === "--date-to-input") parsed.dateToInput = argv[++index];
    else if (token === "--download-trigger") parsed.downloadTrigger = argv[++index];
  }
  return parsed;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.provider) {
    throw new Error("Expected --provider.");
  }

  const raw = fs.readFileSync(configPath, "utf8");
  const config = JSON.parse(raw);
  const provider = config.providers?.[args.provider];
  if (!provider) {
    throw new Error(`Unknown provider '${args.provider}'.`);
  }

  if (args.postLoginReady) provider.selectors.post_login_ready = args.postLoginReady;
  if (args.dateFromInput) provider.selectors.date_from_input = args.dateFromInput;
  if (args.dateToInput) provider.selectors.date_to_input = args.dateToInput;
  if (args.downloadTrigger) provider.selectors.download_trigger = args.downloadTrigger;

  fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  process.stdout.write(`${configPath}\n`);
}

main();

