/**
 * Mantel's approval gate.
 *
 * Pi deliberately ships no permission system: tools run with the user's own
 * privileges. This extension is where that responsibility lives. It hooks
 * `tool_call` — which runs *before* execution and can block — and asks the
 * client for a decision through `ctx.ui.select`. In RPC mode that becomes an
 * `extension_ui_request`, the client renders it as an approval card, and the
 * answer comes back as `extension_ui_response`.
 *
 * Choices match the ladder the client draws:
 *
 *   Allow once                    this call only
 *   Allow for this session        this tool + target, until Pi exits
 *   Always allow in this folder   this tool, in this working folder, persisted
 *   Deny                          block the call (the tool never runs)
 *
 * Failure is closed: no UI, an unanswered dialog, a read error or an
 * unexpected value all deny. Read-only tools are allowed without asking.
 *
 * Load with:  pi --extension pi-extensions/approvals.ts
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const ALLOW_ONCE = "Allow once";
const ALLOW_SESSION = "Allow for this session";
const ALLOW_FOLDER = "Always allow in this folder";
const DENY = "Deny";
const LADDER = [ALLOW_ONCE, ALLOW_SESSION, ALLOW_FOLDER, DENY];

/** Tools that only read. They never need permission. */
const READ_ONLY = new Set(["read", "grep", "find", "ls", "tool_search"]);

/** Dialog budget: long enough to notice, short enough not to wedge. */
const DIALOG_TIMEOUT_MS = 300_000;

interface Grant {
  folder: string;
  tool: string;
}

interface Store {
  grants: Grant[];
}

function storePath(): string {
  const base = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  return path.join(base, "mantel", "approvals.json");
}

function loadStore(): Store {
  try {
    const raw = fs.readFileSync(storePath(), "utf8");
    const parsed = JSON.parse(raw) as Store;
    if (!Array.isArray(parsed.grants)) return { grants: [] };
    return parsed;
  } catch {
    return { grants: [] };
  }
}

function saveStore(store: Store): void {
  try {
    const file = storePath();
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(store, null, 1));
  } catch {
    // A failed write only loses persistence; the in-memory grant still holds.
  }
}

function targetOf(toolName: string, input: unknown): string {
  if (!input || typeof input !== "object") return "";
  const record = input as Record<string, unknown>;
  for (const key of ["path", "file", "target", "command"]) {
    const value = record[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function describe(toolName: string, input: unknown): string {
  const target = targetOf(toolName, input);
  const shown = target.length > 90 ? `${target.slice(0, 90)}…` : target;
  return shown ? `${toolName}: ${shown}` : toolName;
}

export default function (pi: ExtensionAPI) {
  const sessionGrants = new Set<string>();

  pi.on("tool_call", async (event, ctx) => {
    const toolName = String(event.toolName || "");
    if (!toolName || READ_ONLY.has(toolName)) return undefined;

    const folder = ctx.cwd || process.cwd();
    const target = targetOf(toolName, event.input);
    const key = `${toolName}\u0000${target}`;
    const folderKey = `${folder}\u0000${toolName}`;

    if (sessionGrants.has(key)) return undefined;
    if (loadStore().grants.some((g) => `${g.folder}\u0000${g.tool}` === folderKey)) {
      sessionGrants.add(key);
      return undefined;
    }

    if (!ctx.hasUI) {
      return {
        block: true,
        reason: `Mantel: ${toolName} needs approval, but no client is attached`,
      };
    }

    let choice: string | undefined;
    try {
      choice = await ctx.ui.select(
        `Allow ${describe(toolName, event.input)}?`,
        LADDER,
        { timeout: DIALOG_TIMEOUT_MS },
      );
    } catch {
      choice = undefined;
    }

    switch (choice) {
      case ALLOW_ONCE:
        return undefined;
      case ALLOW_SESSION:
        sessionGrants.add(key);
        return undefined;
      case ALLOW_FOLDER: {
        sessionGrants.add(key);
        const store = loadStore();
        if (!store.grants.some((g) => `${g.folder}\u0000${g.tool}` === folderKey)) {
          store.grants.push({ folder, tool: toolName });
          saveStore(store);
        }
        return undefined;
      }
      default: {
        const why = choice ? `denied by the user (${choice})` : "no answer";
        return { block: true, reason: `Mantel: ${toolName} blocked — ${why}` };
      }
    }
  });
}
