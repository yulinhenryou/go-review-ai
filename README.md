# go-review-ai

A CLI MVP for analyzing Go SGF files with KataGo and generating human-readable review reports.

## Goal

Input one SGF file, analyze it with KataGo, find key mistakes, and generate a plain-text review report.

## Phase 1

- CLI only
- one SGF file at a time
- plain-text output
- no web frontend
- no database

## Files

- src/sgf_parser.py
- src/katago_client.py
- src/analyzer.py
- src/classifier.py
- src/report_writer.py
- src/main.py
