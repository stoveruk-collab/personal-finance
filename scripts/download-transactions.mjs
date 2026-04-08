import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const projectRoot = process.cwd();

function parseArgs(argv) {
  const parsed = {
    headed: false,
    interactiveLogin: false,
    keepOpen: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--provider") parsed.provider = argv[++i];
    else if (token === "--from") parsed.from = argv[++i];
    else if (token === "--to") parsed.to = argv[++i];
    else if (token === "--out-dir") parsed.outDir = argv[++i];
    else if (token === "--headed") parsed.headed = true;
    else if (token === "--interactive-login") parsed.interactiveLogin = true;
    else if (token === "--keep-open") parsed.keepOpen = true;
  }

  if (!parsed.provider || !parsed.from || !parsed.to || !parsed.outDir) {
    throw new Error("Expected --provider, --from, --to, and --out-dir.");
  }
  return parsed;
}

function loadConfig() {
  const raw = fs.readFileSync(path.join(projectRoot, "config", "downloaders.json"), "utf8");
  return JSON.parse(raw);
}

function requireSelector(value, provider, field) {
  if (!value) {
    throw new Error(
      `Missing selector '${field}' for provider '${provider}'. Update config/downloaders.json after capturing the portal flow with Playwright codegen.`
    );
  }
}

async function pause(message) {
  process.stdout.write(`${message}\n`);
  await new Promise((resolve) => process.stdin.once("data", resolve));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const config = loadConfig();
  const provider = config.providers[args.provider];
  if (!provider) {
    throw new Error(`Unknown provider '${args.provider}'.`);
  }

  const storagePath = path.join(projectRoot, provider.storage_state);
  const storageDir = path.dirname(storagePath);
  fs.mkdirSync(storageDir, { recursive: true });
  fs.mkdirSync(args.outDir, { recursive: true });

  const launchOptions = {
    headless: !args.headed,
  };

  const browser = await chromium.launch(launchOptions);
  const context = await browser.newContext({
    acceptDownloads: true,
    storageState: fs.existsSync(storagePath) ? storagePath : undefined,
  });
  const page = await context.newPage();

  await page.goto(provider.start_url, { waitUntil: "domcontentloaded" });

  if (args.interactiveLogin) {
    await pause(
      [
        `Interactive login mode for ${provider.label}.`,
        "Complete login in the opened browser window.",
        "If the export page needs MFA, finish that too.",
        "Press Enter here once the account landing page is ready.",
      ].join("\n")
    );
    await context.storageState({ path: storagePath });
  }

  requireSelector(provider.selectors.post_login_ready, args.provider, "post_login_ready");
  requireSelector(provider.selectors.date_from_input, args.provider, "date_from_input");
  requireSelector(provider.selectors.date_to_input, args.provider, "date_to_input");
  requireSelector(provider.selectors.download_trigger, args.provider, "download_trigger");

  await page.waitForSelector(provider.selectors.post_login_ready, { timeout: 30000 });
  await page.fill(provider.selectors.date_from_input, args.from);
  await page.fill(provider.selectors.date_to_input, args.to);

  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 60000 }),
    page.click(provider.selectors.download_trigger),
  ]);

  const suggested = download.suggestedFilename();
  const extension = path.extname(suggested) || ".dat";
  const outputPath = path.join(
    args.outDir,
    `${provider.download_filename_prefix}_${args.from}_to_${args.to}${extension}`
  );
  await download.saveAs(outputPath);
  process.stdout.write(`${outputPath}\n`);

  await context.storageState({ path: storagePath });

  if (args.keepOpen) {
    await pause("Download complete. Press Enter to close the browser.");
  }

  await browser.close();
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});

