# MCP Functionality Needed for BrainDrive Library

This document summarizes the MCP capabilities required to satisfy the scope and user stories in `designs/library.md`. It focuses on MCP additions or enhancements needed beyond the current baseline.

**Assumptions**
- MCP is the authoritative file and git interface for the Library.
- The agent handles intent detection and approvals, but MCP must expose tools to execute approved actions safely and audibly.

## Core File and Directory Operations
- Create directories recursively (for new notes, transcripts, attachments, project scaffolds).
- Move or rename files and folders (e.g., archive projects, rename project slug).
- Copy files (e.g., templates, scaffolds, duplicate project structure).
- Read file metadata for any file type (size, modified time, git commit, mime type).
- List files and folders with filters by type and depth (markdown vs binary).
- Validate paths and prevent traversal outside the Library (already in place, keep strict).
- Preview diffs for any write/edit/delete operation (single file and multi-file).
- Apply multi-file changes as a single transaction with a single commit.
- Batch delete with explicit confirmation and an itemized list of paths.

## Project Management
- Project scaffolding with standard file set (AGENT.md, spec.md, decisions.md, notes.md, ideas.md, tasks.md or pulse tags).
- Project context bundle tool that returns key files and metadata in one call.
- Project rename and archive (move from `projects/active/` to `projects/archive/`).
- Project search by name or tag.

## Quick Capture (Notes, Decisions, Ideas)
- Append structured entries with timestamp, source, and optional tags to target markdown files.
- Insert entries into a specific section by heading (e.g., "## Decisions").
- Create target files automatically if missing (with approval).
- Maintain consistent entry format for later search and parsing.

## Task System (Pulse)
- Create task with ID assignment, owner, priority, tags, status, due date.
- Update task fields (priority, owner, status, tags, blocked reason).
- Complete task: move entry from `pulse/index.md` to `pulse/completed/YYYY-MM.md`.
- Reopen task: move from completed back to index.
- List tasks with filters (owner, priority, project tag, status, blocked).
- Search by task ID and return source location.

## Deep Work Project Context
- Load project context bundle: AGENT.md, spec.md, decisions.md, notes.md, recent transcripts, and tasks tagged for the project.
- Search within a project folder (files + transcripts + attachments).
- Provide diffs and staged changes for approval before applying edits.

## Transcript Processing
- Ingest transcript files (txt, vtt, md) into `transcripts/YYYY-MM/`.
- Update `transcripts/index.md` with new transcript metadata.
- Support batch apply of extracted decisions and tasks in one transaction.
- Provide a structured summary of changes proposed vs applied.

## Document Uploads and Attachments
- Upload and store binary files under `projects/active/<project>/docs/` or `attachments/`.
- Extract text from supported formats (PDF, image OCR) and store alongside file for search.
- Index attachments so search can return snippets and source references.
- Delete attachment with explicit confirmation and git commit.

## Search and Retrieval
- Global search across markdown and extracted attachment text.
- Project-scoped search with source path and line/snippet details.
- Return metadata for search hits (file path, section, timestamp if available).

## Daily Digest and Prioritization
- Read tasks and completed tasks with timestamps.
- List blocked tasks and blockers.
- Provide recent activity summary (today, yesterday) from task history and activity log.
- Optional: read calendar or deadlines file if configured (e.g., `me/deadlines.md`).

## Activity Log and Audit
- Append structured activity entries (tool, action, path, commit SHA, timestamp, user).
- Read recent activity by time range.
- Provide git history for a file or project.
- Support revert to a prior commit for a single file or a project subtree.

## Security and Trust Enhancements
- Risk classification for destructive or bulk changes (warn/confirm).
- Safe defaults for network access (no external calls from MCP by default).
- Strict allowlist of tool capabilities with explicit errors on unknown fields.

## Initial Interview and Setup Wizard
- Create initial Library structure with a batch tool (AGENT.md, me/, life/, pulse/, projects/active/...).
- Apply a structured interview summary into multiple files in one transaction.

## Extensibility Hooks
- Tool registry endpoint for plugins to add new MCP capabilities safely.
- Versioned tool schema and capability discovery for clients.

## Notes on Existing Tools
- Current MCP tools already cover core markdown read/write/edit/delete, project existence, list projects, list markdown files, and search. The items above focus on additional capabilities required to fully satisfy the user stories.
