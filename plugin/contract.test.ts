// Drives the plugin the way opencode drives it: same hook names, same argument
// shapes, same expectation that a throw in tool.execute.before aborts the call.
// The only thing missing is a language model, which is not what this proves.
//
//   node --experimental-strip-types plugin/contract.test.ts <repo>
//
// Requires `python -m injunct serve` to be running.

import { Injunct } from "./injunct.ts"

const repo = process.argv[2]
if (!repo) {
  console.error("usage: contract.test.ts <repo path>")
  process.exit(2)
}

let failures = 0
const check = (name: string, ok: boolean, detail = "") => {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`)
  if (!ok) failures++
}

const hooks: any = await Injunct({ directory: repo, worktree: repo })

// 1. a write the ledger has no opinion about goes straight through
let threw: Error | null = null
try {
  await hooks["tool.execute.before"]({ tool: "edit" }, { args: { filePath: "static/index.html" } })
} catch (e) { threw = e as Error }
check("an unrelated edit is not blocked", threw === null, threw?.message?.slice(0, 60) ?? "")

// 2. the write that failed here before is refused BEFORE it lands
threw = null
try {
  await hooks["tool.execute.before"]({ tool: "edit" }, { args: { filePath: "models/patient.py" } })
} catch (e) { threw = e as Error }
check("the edit that failed before is blocked", threw !== null)
check("the card names the precedent", !!threw?.message?.includes("Holding No"))
check("the card names what is missing", !!threw?.message?.includes("migrations"))
check("the card shows it was tested", !!threw?.message?.includes("fire"))

// 3. a non-writing tool is never even asked about
threw = null
try {
  await hooks["tool.execute.before"]({ tool: "read" }, { args: { filePath: "models/patient.py" } })
} catch (e) { threw = e as Error }
check("a read is not gated", threw === null)

// 4. persuasive authority reaches the prompt, binding authority does not need to
const output = { system: [] as string[] }
await hooks["chat.message"]({ parts: [{ type: "text", text: "add a field to the patient model" }] }, {})
await hooks["experimental.chat.system.transform"]({}, output)
check("system transform runs without throwing", true, `${output.system.length} addenda`)

// ---- the three arms -----------------------------------------------------
// Arm B has silently been a no-op before. These assert the arms are genuinely
// different things, without needing a model to find out.
for (const mode of ["off", "advise", "enforce"]) {
  process.env.INJUNCT_MODE = mode
  const mod: any = await import(`./injunct.ts?m=${mode}`)
  const h: any = await mod.Injunct({ directory: repo, worktree: repo })

  const sys = { system: [] as string[] }
  await h["chat.message"]({ parts: [{ type: "text", text: "add an email field" }] }, {})
  await h["experimental.chat.system.transform"]({}, sys)

  let blocked = false
  try {
    await h["tool.execute.before"]({ tool: "edit" }, { args: { filePath: "models/patient.py" } })
  } catch { blocked = true }

  const spoke = sys.system.join("").length
  if (mode === "off") check("off: silent, does not block", spoke === 0 && !blocked)
  if (mode === "advise") check("advise: speaks, does not block", spoke > 0 && !blocked,
                               `${spoke} chars of prose`)
  if (mode === "enforce") check("enforce: blocks", blocked)
}

if (threw === null && failures === 0) console.log("\n  the plugin refuses. all checks passed.")
else if (failures) console.log(`\n  ${failures} check(s) failed.`)
process.exit(failures ? 1 : 0)
