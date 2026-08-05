#!/usr/bin/env node
/**
 * Onyx per-user credential setup.
 *
 * Merges ONYX_API_URL / ONYX_API_TOKEN / ONYX_PERSONA_ID into the `env` block
 * of the user's global Claude Code settings.json, without touching any other
 * key in that file. Invoked by the /onyx-setup slash command. Safe to run
 * more than once — updates the three keys in place rather than duplicating.
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

// Default persona is 5, "pauL (your go to Agent)" — parcelLab's general-purpose
// Onyx assistant. Override only if the user explicitly names a different persona id.
export function parseArgs(argv) {
  const args = { persona: '5' };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--url') args.url = argv[++i];
    else if (arg === '--token') args.token = argv[++i];
    else if (arg === '--persona') args.persona = argv[++i];
  }
  return args;
}

export function mergeOnyxEnv(settings, { url, token, persona }) {
  const next = { ...settings, env: { ...(settings.env || {}) } };
  next.env.ONYX_API_URL = url;
  next.env.ONYX_API_TOKEN = token;
  next.env.ONYX_PERSONA_ID = persona;
  return next;
}

export function readSettings(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const raw = fs.readFileSync(filePath, 'utf8').trim();
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(
      `${filePath} contains invalid JSON and was left untouched. ` +
        `Fix or back up that file, then run /onyx-setup again. (${err.message})`
    );
  }
}

export function writeSettings(filePath, settings) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(settings, null, 2) + '\n');
}

function main() {
  const { url, token, persona } = parseArgs(process.argv.slice(2));
  if (!url || !token) {
    console.error('Usage: setup-onyx.mjs --url <onyx-api-url> --token <onyx-token> [--persona <id>]');
    process.exit(1);
  }

  const settingsPath = path.join(os.homedir(), '.claude', 'settings.json');

  let settings;
  try {
    settings = readSettings(settingsPath);
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }

  const next = mergeOnyxEnv(settings, { url, token, persona });
  writeSettings(settingsPath, next);

  console.log(`Updated ${settingsPath}`);
  console.log(`  ONYX_API_URL     = ${url}`);
  console.log(`  ONYX_API_TOKEN   = (set, ${token.length} characters)`);
  console.log(`  ONYX_PERSONA_ID  = ${persona}`);
  console.log('\nRestart Claude Code (fully quit and reopen) for the new MCP server to pick this up.');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
