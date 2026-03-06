# AGENTS.md

## Project goal
Build a Python CLI MVP that:
1. reads one SGF file
2. analyzes it with KataGo
3. finds the top mistakes
4. generates a human-readable review report

## Rules
- CLI only for phase 1
- Keep modules small and testable
- Separate parsing, engine integration, analysis, classification, and report generation
- Prefer deterministic templates over free-form explanation
- Do not invent Go explanations unsupported by engine output
- Add tests for important changes
