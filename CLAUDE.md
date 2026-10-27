@AGENTS.md

## Claude-only notes

- Use Superpowers skills where they help. Din's request or an approved plan is the go-ahead. Phase task plans go in `docs/PLAN.md` section 8 at the start of each phase, never in `docs/superpowers/`.
- Throwaway checks (version probes, timing runs) go in the session scratchpad, never the repo, and get deleted afterwards. Record what they showed in the ledger.
- Permission rules and hooks live in `.claude/settings.json` (F5). They back up the "never" rules above; if one blocks you, ask Din instead of working around it. Deny rules and `.claude/hooks/guard.py` hold in every mode, while ask rules did not prompt in a desktop session in bypass mode, so commands only Din runs are denied: give Din the exact command to run.
