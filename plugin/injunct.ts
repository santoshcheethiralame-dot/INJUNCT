// INJUNCT — an opencode plugin that refuses.
//
// Written against the same opencode hook surface as balebbae/autopsy, whose
// plugin is the reference for this API. One deliberate difference, and it is
// the whole point:
//
//   Autopsy's tool.execute.before is advisory by design — its own comment says
//   it "never blocks a tool call, even if the service returns block=true".
//   This one throws. A throw in tool.execute.before aborts the call, and the
//   halt card goes back to the model as the tool's error.
//
// Every decision is made by `python -m injunct serve`. This file is plumbing:
// bounded timeouts, fail-open, and never a reason the agent stalls.

const URL_BASE = process.env.INJUNCT_URL ?? "http://127.0.0.1:4000"
const TIMEOUT_MS = Number(process.env.INJUNCT_TIMEOUT_MS ?? 900)
const CHECK = process.env.INJUNCT_CHECK ?? "python oracle.py"

// off      nothing happens; the agent is untouched
// advise   past failures are injected as prose, and nothing is ever blocked.
//          This is Autopsy's design, and it is arm B of the benchmark.
// enforce  binding precedent stops the call. Default.
const MODE = (process.env.INJUNCT_MODE ?? "enforce").toLowerCase()

// Tools that put bytes on disk. Anything else is not a change we can judge.
const WRITERS = new Set(["write", "edit", "patch", "multiedit"])

type Verdict = {
  n: number
  next?: string
  says: string
  rule: string
  reason: string
  cited: number
  empanel?: Record<string, unknown>
  when: string
}

const post = async (path: string, body: unknown): Promise<any | null> => {
  // Fail open, always. A memory layer that can stop the agent by being down
  // is worse than no memory layer.
  try {
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS)
    const r = await fetch(`${URL_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctl.signal,
    })
    clearTimeout(timer)
    return r.ok ? await r.json() : null
  } catch {
    return null
  }
}

const pendingPaths = (tool: string, args: Record<string, unknown>): string[] => {
  if (!WRITERS.has(tool)) return []
  const out: string[] = []
  for (const key of ["filePath", "path", "file"]) {
    const v = args?.[key]
    if (typeof v === "string" && v.trim()) out.push(v)
  }
  const edits = args?.["edits"]
  if (Array.isArray(edits)) {
    for (const e of edits) {
      const v = (e as Record<string, unknown>)?.["filePath"]
      if (typeof v === "string") out.push(v)
    }
  }
  return out
}

// The halt card, as the model will read it. Short, cited, and it names the
// thing that is missing — a warning the agent cannot skim past, because it
// arrives as the failure of the call it just tried to make.
const card = (verdicts: Verdict[]): string => {
  // ASCII on purpose: the same card goes to stderr from the Claude Code hook,
  // and an em dash there dies on a cp1252 console - which would fail the write
  // OPEN rather than blocking it. render.agent_card must stay byte-identical.
  const lines = ["BLOCKED BY INJUNCT - this exact change failed here before."]
  for (const v of verdicts) {
    lines.push("")
    lines.push(`  Holding No ${v.n}, established ${v.when}. ${v.says}`)
    lines.push(`  Rule:   ${v.rule}`)
    lines.push(`  Reason: ${v.reason}`)
    // Three provenances, and they must not read as one. A rule replayed against
    // history has earned something a rule you typed has not.
    const e = (v.empanel ?? {}) as Record<string, string>
    if (e.tested) lines.push(`  Tested: ${e.fire} fire, ${e["false"]} false positives.`)
    else if (e.taught) lines.push("  Tested: not empanelled - you wrote this rule yourself.")
    else if (e.mined) lines.push("  Tested: mined from this repo's history, not empanelled.")
    if (e.documented) lines.push(`  From:   ${e.documented}`)
    // A verdict tells the agent it is wrong; an instruction tells it what to do.
    // Without this a small model retries the same edit and stalls.
    if (v.next) lines.push(`  DO THIS NEXT: ${v.next}`)
  }
  lines.push("")
  lines.push("Do the work named above in the same change, then try again.")
  return lines.join("\n")
}

const Injunct = async (ctx: {
  project?: { id?: string }
  directory?: string
  worktree?: string
}) => {
  const repo = ctx.worktree ?? ctx.directory
  let lastTask = ""

  return {
    // The agent said what it wants. Keep it for retrieval.
    "chat.message": async (input: any, _output: any) => {
      const text = input?.parts
        ?.filter((p: any) => p?.type === "text" && p?.text)
        ?.map((p: any) => p.text)
        ?.join("\n")
      if (typeof text === "string" && text.trim()) lastTask = text.trim()
    },

    // Persuasive authority only. Binding precedent does not need words.
    "experimental.chat.system.transform": async (_input: any, output: { system: string[] }) => {
      if (!repo || MODE === "off") return
      // In advise mode the binding rules are spoken rather than enforced, so the
      // two arms differ only in whether the agent may ignore what it is told.
      const r = await post("/v1/advise", { repo, task: lastTask, everything: MODE === "advise" })
      if (r?.text) output.system.push(r.text)
    },

    // Enforcement. This is the line Autopsy declined to write.
    "tool.execute.before": async (input: { tool: string }, output: { args: Record<string, unknown> }) => {
      if (!repo || MODE !== "enforce") return
      const pending = pendingPaths(input.tool, output.args)
      if (!pending.length) return
      const r = await post("/v1/gate", { repo, pending })
      if (r?.block && Array.isArray(r.verdicts) && r.verdicts.length) {
        throw new Error(card(r.verdicts as Verdict[]))
      }
    },

    // The agent has gone quiet. Run the repo's own check; a failure is a case.
    event: async (input: { event: { type: string } }) => {
      if (input?.event?.type !== "session.idle" || !repo || MODE === "off") return
      await post("/v1/postflight", { repo, cmd: CHECK })
    },
  }
}

export default { id: "injunct", server: Injunct }
export { Injunct }
