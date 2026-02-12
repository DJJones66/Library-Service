# Spec: BrainDrive Library Plugin

> **Save to:** `BrainDrive-Library/projects/active/braindrive-library/spec.md`
> Generated from strategy session on 2026-02-04
> Last Updated: 2026-02-05 (US-13: Initial Interview to solve cold start problem)

## Overview

### What We're Building
A BrainDrive plugin that creates an AI executive assistant ("Second Brain") that learns and remembers your projects, life, and goals so the more you use it the more helpful it becomes. Access it from any device — desktop or mobile — with the same unified experience.

**Magic moment:** "It remembers everything about my projects AND my life — my goals, my decisions, what I care about — and I can access it from my phone or laptop, anywhere. It's like having an expert executive assistant with all my context available to help me 24/7/365."

**Where it runs — your choice:**
- **Local:** On your home computer with secure remote access via tunneling (Cloudflare Tunnels, Tailscale)
- **Self-hosted:** On your own VPS for always-on access
- **Managed:** BrainDrive Managed hosting (coming soon) — we run it, you own and control it and can easily move to local or another host at anytime.

Your Second Brain is stored as markdown files — portable, human-readable, and always yours. Want complete privacy? Run locally on your own computer with offline models. Your data never leaves your machine, and you don't even need an internet connection.

Want to use the most powerful models from OpenAI and Anthropic with your BrainDrive powered Second Brain? You can do that too.

Prefer convenience? Use BrainDrive's managed hosting service where we handle the setup, infrastructure, and security for you — with no lock-in. Your files and data are yours, and you can move your BrainDrive to your local machine or another host at any time.

### Target User
- **Persona:** Privacy Focused Pat — tech-curious professional who values data sovereignty; not a developer but fearless with new tools
- **Technical Level:** Non-technical — user just chats; the system handles file storage, git versioning, and organization transparently
- **Context:** Daily life — capturing thoughts, managing projects AND personal goals, tracking tasks, making decisions, maintaining context across all areas of life

See [Privacy Focused Pat persona](../../../braindrive/brand/personas/privacy-focused-pat.md) for full details.

### Problem Statement
AI assistants are getting better at remembering you — they have a certain level of memory and you can feed them specific context via chat or projects. But nothing offers a comprehensive Second Brain that knows *everything* about your life. And the big tech companies are racing to build exactly this. The problem? When they get there, **they own your second brain, not you.**

Your second brain will contain your most personal context: your goals, your decisions, your fears, your finances, your health, your relationships. Do you want that living on someone else's servers, training their models, locked into their ecosystem?

Big Tech wants to lock you in to their systems. BrainDrive gives you the key.

### Why Own Your Second Brain?

| Big Tech Second Brain | Your Second Brain (BrainDrive) |
|-----------------------|-------------------------------|
| They own your most personal context | **You own it** — local files, your machine |
| Training their models with your life | **Private** — complete privacy if you want it, runs fully offline |
| Locked into their ecosystem | **Flexible** — not stuck with what they give you, make it your own |
| One-size-fits-all features | **Customizable** — tweak, extend, even monetize your setup |
| Subscription forever | **Yours forever** — no account required, export anytime |
| Different apps, different devices | **One brain, any device** — same experience on desktop and mobile |

BrainDrive gives you the power of a comprehensive AI second brain with the ownership, privacy, and flexibility that big tech can never offer.

---

## User Stories

<details>
<summary><strong>US-1: Quick Capture — Notes and Decisions</strong><br>As an Owner, I want to quickly capture a note or decision so that I don't lose important information and it's automatically filed in the right place.</summary>

**Steps:**
1. User opens BrainDrive Quick Capture (hotkey or click)
2. User speaks or types a note (work or personal):
   - "Note that we decided to use JWT for authentication" (work)
   - "My broker called — I need to sell the XYZ stock before Friday" (personal)
   - "Decided to focus on health this quarter — gym 3x/week" (life goal)
3. System detects intent (decision/note) and finds related context
4. System proposes where to file it: "I'll add this to your health goals. OK?"
5. User approves
6. System writes to file, commits to git
7. System confirms: "Done. Added to braindrive-core decisions."

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I have a project "braindrive-core" with a decisions.md file
When I say "Note that we decided to use JWT for authentication"
Then the system should identify this as a decision
And propose adding it to "projects/active/braindrive-core/decisions.md"
And wait for my approval before writing
```

```gherkin
Given I approve a proposed file change
When the system writes the change
Then the file should be updated with the new content
And a git commit should be created automatically
And I should see a confirmation message
```

```gherkin
Given I reject a proposed file change
When I say "No" or "Cancel"
Then no changes should be made to any files
And the system should ask where I'd like to file it instead
```

</details>

<details>
<summary><strong>US-2: Quick Capture — Tasks</strong><br>As an Owner, I want to quickly create a task so that I don't forget to-dos and they're tracked in my task system.</summary>

**Next Action Principle:**
Tasks must be *executable next actions*, not vague intentions. The system should convert intentions into concrete actions:
- **Input:** "Work on the website" → **Stored:** "Draft homepage hero section copy"
- **Input:** "Deal with the budget" → **Stored:** "Review Q1 expenses spreadsheet and flag anomalies"
- **Input:** "I need to schedule my annual physical" → **Stored:** "Call Dr. Smith's office to book annual physical"

**Steps:**
1. User opens Quick Capture
2. User says a task (work or personal):
   - "Add a task to review the API rate limiting, high priority" (work)
   - "Remind me to call mom this weekend" (personal)
   - "I need to schedule my annual physical" (health)
3. System detects intent (task creation) and determines context
4. System extracts/converts to a next action if input is vague
5. System proposes: "I'll create a task for your health: Call Dr. Smith's office to book annual physical. OK?"
6. User approves (or refines the action)
7. System adds to pulse/index.md, commits
8. System confirms: "Done. Task T-118 created."

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I am the current user "Dave W"
When I say "Add a task to review the API rate limiting, high priority"
Then the system should create a task with the next available ID
And assign me as the owner
And set priority to p1
And add it to pulse/index.md
```

```gherkin
Given I am in Deep Work mode for project "braindrive-library"
When I create a task without specifying a project
Then the task should be tagged with #braindrive-library
```

```gherkin
Given a task "T-118: Review API rate limiting" exists
When I say "Mark the rate limiting task done"
Then the system should find the matching task
And move it to pulse/completed/2026-02.md
And remove it from pulse/index.md
```

```gherkin
Given I say "I need to work on the website"
When the system processes this as a task
Then it should recognize this as a vague intention
And ask clarifying questions OR propose a concrete next action
And store the executable action, not the vague intention
Example: "Draft homepage hero copy" instead of "Work on website"
```

</details>

<details>
<summary><strong>US-3: Deep Work — Project Context</strong><br>As an Owner, I want to work on a specific project with full context loaded so that I don't have to re-explain my project every session.</summary>

As an Owner, I want to work on a specific project with full context loaded so that I don't have to re-explain my project every session.

**Steps:**
1. User navigates to Projects > braindrive-library
2. System loads project context (AGENT.md, spec.md, decisions.md, recent transcripts, project tasks)
3. System shows project dashboard with active tasks
4. User asks: "Update the spec based on what we discussed this morning"
5. System searches transcripts, finds relevant content
6. System proposes specific edits with diff preview
7. User approves/modifies
8. System makes edits, commits

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I navigate to project "braindrive-library"
When the project loads
Then the system should read AGENT.md, spec.md, decisions.md
And load recent transcripts mentioning this project
And display active tasks tagged #braindrive-library
And be ready to answer questions with full context
```

```gherkin
Given I am in Deep Work mode for "braindrive-library"
When I ask "What did we decide about authentication?"
Then the system should search decisions.md and transcripts
And return relevant decisions with sources
And not ask me to re-explain the project
```

```gherkin
Given the system proposes edits to spec.md
When I view the proposal
Then I should see a clear diff of what will change
And be able to approve, modify, or reject
And modifications should update the proposal before applying
```

</details>

<details>
<summary><strong>US-4: Task Prioritization</strong><br>As an Owner, I want to ask what I should work on next so that I can focus on the highest-priority work.</summary>

**Steps:**
1. User asks: "What should I work on next?"
2. System reads pulse/index.md
3. System filters by user's tasks, considers priority and blocked status
4. System suggests top tasks with rationale
5. User picks one or specifies different criteria

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I have tasks at p0, p1, and p2 priority
When I ask "What should I work on next?"
Then the system should suggest p0 tasks first
And exclude blocked tasks
And show only my tasks (not others' tasks)
```

```gherkin
Given I am in Deep Work mode for "braindrive-library"
When I ask "What should I work on next?"
Then the system should prioritize tasks tagged #braindrive-library
And still show other high-priority tasks as alternatives
```

```gherkin
Given a task is marked as blocked
When listing tasks to work on
Then blocked tasks should be excluded
And the blocker should be mentioned if I ask about it
```

</details>

<details>
<summary><strong>US-5: File Operations</strong><br>As an Owner, I want the AI to read, write, and edit files in my Library so that it can help me manage my knowledge base.</summary>

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I ask "What's in the braindrive-library spec?"
When the system reads the file
Then it should return the contents of projects/active/braindrive-library/spec.md
And not access files outside the Library folder
```

```gherkin
Given I ask to create a new file "notes/meeting-2026-02-04.md"
When I approve the creation
Then the file should be created with the proposed content
And parent directories should be created if needed
And a git commit should record the change
```

```gherkin
Given I ask to delete a file
When the system proposes deletion
Then it should require explicit confirmation
And show what will be deleted
And the deletion should be recoverable via git
```

```gherkin
Given I try to access "/etc/passwd" or "../../../secrets"
When the system validates the path
Then it should reject the request
And return an error about invalid path
And not access anything outside Library folder
```

</details>

<details>
<summary><strong>US-6: Voice Capture (v1.1)</strong><br>As an Owner on mobile, I want to capture notes by voice so that I can add to my Second Brain while driving or walking.</summary>

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I am on the mobile interface
When I tap the voice capture button and speak
Then my speech should be transcribed
And processed the same as typed Quick Capture
And filed appropriately with my approval
```

</details>

<details>
<summary><strong>US-7: Transcript Processing</strong><br>As an Owner, I want to drop a meeting transcript into Quick Capture so that decisions, tasks, and ideas are automatically extracted and applied to my Library.</summary>

**Steps:**
1. User opens Quick Capture
2. User pastes a transcript or attaches a VTT/text file (Zoom, Teams, etc.)
3. System detects it's a transcript and parses speaker turns
4. System extracts:
   - Decisions made → proposes adding to relevant decisions.md
   - Tasks discussed → proposes marking complete or updating context
   - New tasks assigned → proposes creating in pulse/index.md
   - Ideas/insights → proposes adding to relevant notes
5. System shows summary: "Found 3 decisions, 2 completed tasks, 4 new tasks. Apply?"
6. User reviews and approves (all or selectively)
7. System applies changes, commits to git
8. System saves transcript to `transcripts/YYYY-MM/` with index entry

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I paste a meeting transcript into Quick Capture
When the system parses the transcript
Then it should identify speaker turns and topic changes
And extract decisions, tasks, and ideas mentioned
And show a summary of proposed changes before applying
```

```gherkin
Given a transcript mentions "we decided to use PostgreSQL for the database"
When the system extracts decisions
Then it should propose adding to the relevant project's decisions.md
And include the context (who said it, when)
And wait for approval before writing
```

```gherkin
Given a transcript mentions "the API refactor is done"
And task T-042 "Refactor API endpoints" exists in pulse/index.md
When the system processes the transcript
Then it should propose marking T-042 as complete
And move it to pulse/completed/YYYY-MM.md upon approval
```

```gherkin
Given a transcript mentions "Dave needs to review the security audit by Friday"
When the system extracts new tasks
Then it should propose creating a task with Dave W as owner
And tag it with the relevant project if mentioned
And add context from the conversation
```

```gherkin
Given I approve transcript processing results
When the system applies changes
Then each change should be committed to git
And the transcript should be saved to transcripts/YYYY-MM/
And the transcripts/index.md should be updated with the new entry
```

</details>

<details>
<summary><strong>US-8: Security & Trust</strong><br>As an Owner, I want to know my Second Brain is secure and won't do anything dangerous without my explicit permission so that I can trust it with my personal information.</summary>

**Steps:**
1. All AI actions are visible and require approval before execution
2. The system clearly shows what it's about to do before doing it
3. Risky operations (delete, bulk changes, external access) have extra confirmation
4. The system explains risks when I ask it to do something potentially dangerous
5. I can see a log of everything the system has done
6. No data leaves my machine without my knowledge

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given the AI proposes to write or edit a file
When I view the proposal
Then I should see exactly what will change (diff view)
And the change should not execute until I explicitly approve
And I should be able to reject or modify before approving
```

```gherkin
Given I ask the AI to delete multiple files
When the system prepares the action
Then it should show a warning about the destructive operation
And list all files that will be deleted
And require explicit confirmation with the word "delete" or similar
```

```gherkin
Given I ask the AI to do something risky (e.g., "delete all my old projects")
When the system processes my request
Then it should explain the risk: "This will permanently delete X files"
And ask me to confirm I understand the consequences
And suggest safer alternatives if available (e.g., "archive instead?")
```

```gherkin
Given I want to verify what the AI has done
When I ask "What have you changed today?" or view the activity log
Then I should see a complete list of all actions taken
And each action should show what changed and when
And I should be able to undo any change via git
```

```gherkin
Given the system is running
When any operation attempts to access the network or external services
Then it should be blocked unless I have explicitly enabled it
And I should be notified of the attempt
And API calls to AI models should be the only network activity by default
```

</details>

<details>
<summary><strong>US-9: One-Click Installation</strong><br>As an Owner, I want to install BrainDrive with a single download and click — no terminal, no technical setup — so that I can start using my Second Brain immediately.</summary>

**Steps:**
1. User downloads installer from website (Mac .dmg, Windows .exe; Linux users use CLI)
2. User double-clicks to install like any other application
3. Installer handles all dependencies (Python, Node, etc.) invisibly
4. User opens BrainDrive and is guided through initial setup
5. System creates Library folder and connects to AI model
6. User is ready to capture their first note

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I am a non-technical user
When I download BrainDrive from the website
Then I should get a single installer file for my platform
And the download page should auto-detect my OS
And no terminal or command-line knowledge should be required
```

```gherkin
Given I have downloaded the installer
When I double-click it
Then it should install like any other desktop application
And handle all dependencies without showing technical output
And complete in under 2 minutes on typical hardware
```

```gherkin
Given I open BrainDrive for the first time
When the app starts
Then I should see a friendly welcome screen
And be guided to choose my AI model (Claude, GPT, or local)
And have my Library folder created automatically
And be ready to use Quick Capture within 60 seconds of first launch
```

```gherkin
Given I want to access BrainDrive remotely
When I enable remote access in settings
Then the system should guide me through Cloudflare Tunnel or Tailscale setup
And provide simple toggle options, not manual configuration
And test the connection and confirm it's working
```

</details>

<details>
<summary><strong>US-10: Extensibility & Freedom</strong><br>As an Owner, I want BrainDrive to be modular and extensible so that I'm not locked into one way of doing things — I can customize it, add plugins, connect other tools, and take my data anywhere.</summary>

**Why this matters:**
- Big tech gives you their vision, take it or leave it
- BrainDrive is plugin-based — you can make it whatever you want
- Starting with the Library, but designed to scale into any use case
- The foundation is built to grow with you and the market
- Your data is yours — use your Library with other tools if you wish

**Steps:**
1. User browses available plugins in Plugin Manager
2. User installs a plugin with one click (e.g., GitHub integration, calendar sync)
3. Plugin adds new capabilities without touching core
4. User can disable/remove plugins anytime
5. Advanced users can build their own plugins
6. User can export Library and use with any AI tool (Claude Code, Cursor, etc.)

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I want to add a new capability to BrainDrive
When I open the Plugin Manager
Then I should see available plugins I can install
And each plugin should show what it does and what access it needs
And I should be able to install with a single click
```

```gherkin
Given I have installed a plugin (e.g., GitHub Issues sync)
When I use the new capability
Then it should integrate seamlessly with my Library
And I should be able to disable or remove it anytime
And removing it should not affect my core Library data
```

```gherkin
Given I am a developer who wants to extend BrainDrive
When I want to build a custom plugin
Then I should have access to plugin documentation and APIs
And be able to add new endpoints, tools, and UI components
And my plugin should work alongside official plugins
```

```gherkin
Given I want to use my Library with another tool
When I point Claude Code, Cursor, or any AI tool at my Library folder
Then my files should be readable and usable (standard markdown)
And I should not be locked into BrainDrive-specific formats
And I can return to BrainDrive anytime without data migration
```

```gherkin
Given the AI/productivity market evolves
When new AI capabilities or integrations become available
Then BrainDrive's plugin architecture should accommodate them
And I should not have to wait for BrainDrive to build everything
And community or third-party plugins should be possible
```

</details>

<details>
<summary><strong>US-11: Project Document Upload</strong><br>As an Owner, I want to upload documents (PDFs, images, files) that are relevant to a specific project so that they appear on my project dashboard in Deep Work mode and the AI can reference them when helping me with that project.</summary>

**Why this matters:**
- Projects often have reference materials beyond text notes — research reports, PDFs, images, spreadsheets
- Personal threads (health, finances) need supporting documents — bloodwork results, doctor's notes, bank statements
- These documents should be visible and accessible when you're focused on that area
- The AI should be able to read and reference these when helping you work

**Steps:**
1. User is in Deep Work mode for a project (work or personal)
2. User uploads a document via drag-drop or file picker
3. System stores the document in the project's `/docs` or `/attachments` folder
4. System extracts text/metadata where possible (PDFs, images with OCR)
5. Document appears in the project dashboard under "Reference Documents"
6. When working on the project, AI can search and reference these documents
7. User can ask: "What did my bloodwork say about cholesterol?" and AI finds it

**Example scenarios:**
- **Work project:** Upload research reports, competitor analyses, design mockups to a project folder
- **Health thread:** Upload bloodwork PDFs, doctor's notes, prescription info to your health goals area
- **Finance thread:** Upload statements, tax documents, investment reports
- **Learning project:** Upload course materials, certificates, study notes

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I am in Deep Work mode for project "braindrive-library"
When I drag-and-drop a PDF file onto the interface
Then the file should be uploaded to "projects/active/braindrive-library/docs/"
And the system should extract text content where possible
And the file should appear in my project dashboard under "Reference Documents"
```

```gherkin
Given I have a personal thread "health-goals" with uploaded bloodwork PDFs
When I enter Deep Work mode for "health-goals"
Then I should see my uploaded documents (bloodwork, doctor's notes) in the dashboard
And be able to click to view them
And the AI should have access to their contents for reference
```

```gherkin
Given I have uploaded research reports to project "market-analysis"
When I ask "What did the Q4 report say about customer churn?"
Then the AI should search my uploaded documents
And return relevant information from the Q4 report PDF
And cite which document the information came from
```

```gherkin
Given I upload a document to a project
When the upload completes
Then the document should be stored in the project folder (not a central location)
And the path should follow convention: `{project}/docs/{filename}`
And a git commit should record the addition
```

```gherkin
Given I want to remove a document from a project
When I delete it from the Reference Documents section
Then the file should be removed from the project folder
And require confirmation before deletion
And the deletion should be recorded in git (recoverable)
```

```gherkin
Given I upload a file type that cannot be text-extracted (e.g., binary, video)
When the upload completes
Then the file should still be stored and visible in the dashboard
And the AI should acknowledge it exists but note it cannot read the contents
And suggest alternatives if needed (e.g., "I can see you uploaded a video — could you summarize the key points?")
```

</details>

<details>
<summary><strong>US-12: Daily Digest</strong><br>As an Owner, I want to receive a personalized daily digest each morning that shows me the top things to focus on and a recent win to start my day with momentum.</summary>

**Why this matters:**
- Starting the day with clarity reduces decision fatigue and anxiety
- Seeing a recent win creates positive momentum and reminds you of progress
- A curated focus list prevents overwhelm from a long task list
- Customization lets each person optimize for what motivates them

**Default digest contents:**
1. **Top 3 Next Actions** — Executable tasks you can act on immediately (not vague intentions)
2. **Yesterday's Win** — A completed task or achievement from yesterday to build momentum
3. **Quick context** — Any meetings, deadlines, or time-sensitive items
4. **Follow-ups needed** — Items waiting on others or needing your response
5. **Flow Starter** — One small, easy action to get back into momentum (especially if you've been away)

**Next Action Principle:**
Focus items must be *executable*, not *intentional*. The difference:
- **Intention (bad):** "Work on the website" — not executable, unclear what to do
- **Next action (good):** "Email Sarah to confirm copy deadline" — concrete, actionable

The AI should extract or convert vague statements into next actions when creating tasks.

**Design for Restart, Not Perfection:**
A stable system assumes users will fall off. Don't punish them for it — make restart easy:
- **No catch-up required** — Don't guilt users about what they missed
- **10-minute brain dump** — Just dump whatever's in your head into Quick Capture and pick back up
- **System keeps running** — The automation works whether you engage or not
- **Fresh start anytime** — Every session is a valid restart point

This philosophy permeates the digest: it's not "here's everything you failed to do" — it's "here's an easy way back in."

**Re-engagement & Flow:**
When the user has been away or inactive, the digest should help them get back into flow:
- **Detect inactivity** — Notice if no tasks added/completed recently (e.g., 3+ days)
- **Follow-up awareness** — Surface items waiting on responses or needing attention
- **Flow Starter** — Suggest one small, easy action to build momentum

The Flow Starter should be:
- Something completable in under 5 minutes
- Low cognitive load (review, check, send a quick message)
- Related to an active project to rebuild context
- Examples: "Review your notes from last week's call", "Check if Sarah replied to your email", "Read the first section of the uploaded report"

**Email Delivery:**
The digest can be delivered via email in addition to the dashboard:
- **Morning email** — Configurable delivery time (default: 7am local)
- **Same content** — Focus items, wins, follow-ups, flow starter
- **Reply to capture** — Reply to the email to add notes/tasks directly
- **One-click deep links** — Links to open BrainDrive in the right context
- **Digest-only mode** — For users who prefer email over opening the app

**Steps:**
1. User opens BrainDrive in the morning (or at configured time)
2. System generates personalized digest based on:
   - Active tasks in pulse/index.md (priority, project focus, blocked status)
   - Recently completed tasks in pulse/completed/
   - Calendar/deadline context (if available)
3. Digest appears as a card/modal on the dashboard
4. User can customize what appears in their digest via settings
5. User can dismiss or "Start my day" to enter focus mode

**Customization options (settings):**
- Number of focus items (default: 3)
- Include yesterday's win (default: yes)
- Include upcoming deadlines (default: yes)
- Filter by project (default: all)
- Digest delivery: dashboard only, email only, or both (default: dashboard)
- Email delivery time (default: 7:00 AM local)
- Email address for delivery
- Include motivational quote (default: no)
- Show blocked items needing attention (default: yes)
- Show follow-ups waiting on others (default: yes)
- Show Flow Starter when returning (default: yes)
- Inactivity threshold for "welcome back" mode (default: 3 days)
- Prompt for brain dump when no recent tasks added (default: yes)

**Example digest (active user):**
```
Good morning! Here's your focus for today:

🏆 Yesterday's Win
   ✓ Completed "Add document upload to spec" (braindrive-library)

📋 Top 3 Next Actions
   1. [p0] Read security audit PDF and list top 5 critical findings — #braindrive-core
   2. [p1] Sketch mobile navigation flow in Figma — #braindrive-library
   3. [p1] Write test for JWT token refresh endpoint — #braindrive-core

📬 Follow-ups
   • Waiting on Dave J's response about API integration (sent 2 days ago)
   • Sarah's design review — due tomorrow

⚠️ Needs Attention
   • "API integration" is blocked — waiting on Dave J

Ready to start? [Enter Focus Mode] [Customize Digest]
```

**Example digest (returning after time away):**
```
Welcome back! It's been 4 days since your last session.

💡 Flow Starter (get back in the groove)
   → Review your notes from the Feb 1st strategy call (5 min read)

📬 Needs Follow-up
   • Dave J replied to your API question — needs your response
   • Security audit report was uploaded while you were away

📋 Top 3 Next Actions
   1. [p0] Respond to Dave J's API architecture question — #braindrive-core
   2. [p1] Read new security audit findings — #braindrive-core
   3. [p1] Review mobile mockups Dave sent — #braindrive-library

You haven't added any new tasks in 4 days. Want to do a quick brain dump?
[Quick Capture] [Enter Focus Mode] [Customize Digest]
```

Note: Each focus item is a concrete next action, not a vague intention like "Work on security" or "Do mobile stuff".

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I open BrainDrive in the morning
When the dashboard loads
Then I should see my daily digest with top focus items and yesterday's win
And the focus items should be ordered by priority (p0 first)
And blocked tasks should be excluded from focus items
```

```gherkin
Given I completed tasks yesterday
When the digest generates
Then it should show one completed task as "Yesterday's Win"
And prefer higher-priority or significant completions
And if nothing was completed, show encouraging context instead
```

```gherkin
Given I have tasks across multiple projects
When the digest shows top 3 focus items
Then it should pull from all my projects by default
And respect my project filter settings if configured
And show the project tag for each item
```

```gherkin
Given I want to customize my digest
When I click "Customize Digest" or go to settings
Then I should see options for: number of items, show wins, show deadlines, project filter
And my preferences should persist across sessions
And changes should apply immediately to the current digest
```

```gherkin
Given I have blocked tasks that need attention
When the digest generates
Then blocked items should appear in a separate "Needs Attention" section
And show what they're blocked on
And not count toward the top focus items
```

```gherkin
Given I dismiss the digest
When I want to see it again
Then I should be able to access it from a menu or command
And it should regenerate with current data
```

```gherkin
Given I haven't opened BrainDrive in 3+ days
When the digest generates
Then it should show a "Welcome back" message with days away
And include a Flow Starter (small, easy action to rebuild momentum)
And highlight what changed while I was away (new uploads, replies, etc.)
```

```gherkin
Given I have items waiting on others' responses
When the digest generates
Then it should show a "Follow-ups" section
And indicate how long each item has been waiting
And surface any responses that came in
```

```gherkin
Given I haven't added any new tasks in several days
When the digest generates
Then it should gently note "You haven't added tasks in X days"
And offer a quick capture prompt to do a brain dump
And not be judgmental or guilt-inducing
```

```gherkin
Given I click the Flow Starter action
When I complete it
Then it should be marked done
And the system should suggest the next small step
And help me transition into deeper work naturally
```

```gherkin
Given I have enabled email delivery for my digest
When my configured delivery time arrives (e.g., 7am)
Then I should receive an email with my daily digest
And it should contain the same info as the dashboard digest
And include deep links to open BrainDrive in the right context
```

```gherkin
Given I receive a digest email
When I reply to it with text (e.g., "Remember to call the dentist")
Then that text should be captured as a Quick Capture input
And processed the same as if I typed it in the app
And I should receive a confirmation of what was captured
```

```gherkin
Given I've been away for a while and feel overwhelmed
When I do a 10-minute brain dump into Quick Capture
Then the system should accept whatever I give it without judgment
And organize it into appropriate places
And I should feel "caught up" enough to continue
And no catch-up or backlog review should be required
```

</details>

<details>
<summary><strong>US-13: Initial Interview (Setup Wizard)</strong><br>As a new Owner, I want BrainDrive to interview me when I first set up my Library so that I don't start with a blank slate — my Second Brain is already populated with my projects, goals, and context from day one.</summary>

**Why this matters:**
- Cold start is the #1 killer of productivity tools — empty systems feel overwhelming
- Users don't know what to capture or how to organize when starting fresh
- An interview lets the AI learn about you before you need it
- Starting with populated context makes the first "magic moment" happen immediately
- Users see immediate value: "It already knows about my projects!"

**Design for Warmth, Not Interrogation:**
The interview should feel like a friendly conversation, not a form. The AI:
- Asks open-ended questions and follows natural tangents
- Picks up on mentioned projects, people, goals without forcing structure
- Summarizes what it learned and asks for corrections
- Creates initial structure based on what was discussed, not a template
- Can be skipped entirely for users who want to start blank

**Interview Flow:**

1. **Welcome & Philosophy** (30 seconds)
   - Explain what BrainDrive Library is and how it helps
   - Set expectations: "I'll ask you some questions to get started — takes about 10 minutes"
   - Offer to skip: "Or if you prefer, you can start with a blank Library"

2. **Life Areas Discovery** (2-3 minutes)
   - "Tell me about the main areas of your life you'd like to track"
   - Listen for: work, personal projects, health, finances, learning, relationships, hobbies
   - Follow up naturally: "You mentioned health — is there a specific goal you're working on?"

3. **Active Projects** (3-4 minutes)
   - "What are you actively working on right now?"
   - For each project mentioned: ask about status, blockers, what's next
   - Capture enough context to create initial project folders

4. **Goals & Priorities** (2-3 minutes)
   - "What are your top priorities this quarter/year?"
   - "Is there anything you keep meaning to do but haven't started?"
   - These become tasks in pulse/index.md

5. **People & Teams** (1-2 minutes, if applicable)
   - "Who do you work with regularly?"
   - "Anyone you need to follow up with?"
   - Captures team context for multi-user future

6. **Quick Wins** (1 minute)
   - "What's one small thing you've been meaning to capture?"
   - Demonstrates Quick Capture immediately
   - First file gets created in real-time

7. **Summary & Approval** (1-2 minutes)
   - AI summarizes everything it learned
   - Shows proposed Library structure
   - User approves, modifies, or asks for changes
   - Creates initial files and commits

**What Gets Created:**

```
BrainDrive-Library/
├── AGENT.md                    # Personalized with user's context
├── me/                         # Personal profile and goals
│   ├── about.md                # Who you are, what you care about
│   ├── goals.md                # Life goals and priorities
│   └── people.md               # Key people you mentioned
├── projects/active/            # Projects from interview
│   ├── [project-1]/
│   │   ├── AGENT.md
│   │   └── ideas.md
│   └── [project-2]/...
├── pulse/
│   ├── index.md                # Tasks extracted from interview
│   └── backlog.md              # Someday/maybe items
└── life/                       # Personal threads (if mentioned)
    ├── health/
    ├── finances/
    └── learning/
```

**Steps:**
1. User opens BrainDrive for the first time (or creates new Library)
2. Welcome screen offers: "Let's set up your Second Brain" or "Start blank"
3. If user chooses setup, interview begins in chat interface
4. AI asks questions, listens, follows tangents naturally
5. AI occasionally summarizes: "So far I've heard about X, Y, Z — is that right?"
6. After ~10 minutes, AI presents proposed structure
7. User reviews and approves (can edit any proposed content)
8. System creates all files, commits to git
9. User sees populated Library and Daily Digest with actual items
10. First Quick Capture is suggested: "Anything else on your mind?"

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I open BrainDrive with an empty Library
When the app starts
Then I should see a welcome screen offering setup interview or blank start
And the setup option should explain what the interview does
And there should be a clear "Skip" option for power users
```

```gherkin
Given I choose to do the setup interview
When the interview begins
Then the AI should introduce itself and set expectations
And ask open-ended questions about my life and work
And follow up naturally on topics I mention
And not feel like filling out a form
```

```gherkin
Given I mention "I'm working on a website redesign" during the interview
When the AI processes my response
Then it should ask follow-up questions about the project
And remember this to create a project folder later
And not require me to explicitly say "create a project"
```

```gherkin
Given I mention health goals during the interview
When the AI summarizes what it learned
Then it should include health as a life area
And propose creating a health thread under life/
And extract any specific goals mentioned as tasks
```

```gherkin
Given the interview is complete
When the AI shows the proposed Library structure
Then I should see a preview of all files and folders to be created
And be able to view/edit any proposed content before creation
And approve all, approve with changes, or start over
```

```gherkin
Given I approve the proposed Library structure
When the system creates the files
Then all files should be created with the discussed content
And a git commit should record the initial setup
And my Daily Digest should immediately show items from the interview
```

```gherkin
Given I choose "Start blank" from the welcome screen
When the Library initializes
Then it should create only the minimal structure (AGENT.md, pulse/, projects/)
And not ask any interview questions
And show Quick Capture as the first action
```

```gherkin
Given I'm in the middle of the interview
When I say "I'd rather just start using it"
Then the AI should offer to create a Library with what was discussed so far
And not require completing all questions
And gracefully exit the interview flow
```

```gherkin
Given I completed the setup interview a week ago
When I want to add more context
Then I should be able to run the interview again from settings
And it should build on existing context, not replace it
And only add new information without duplicating
```

```gherkin
Given I'm a returning user creating a new Library
When I start the setup interview
Then it should not assume I'm a first-time user
And explain that this creates initial structure
And offer to import from an existing Library if available
```

</details>

<details>
<summary><strong>US-14: Project Kickoff — From Idea to Ready-to-Build</strong><br>As an Owner, I want to go from a rough idea to a fully-documented, ready-to-build project through a guided conversation so that I don't have to write specs and plans manually, and any AI (or human) can execute the project autonomously from the documentation.</summary>

**Why this matters:**
- Ideas die in the gap between "I should build this" and "I know exactly what to build"
- Writing specs and plans is tedious — most people skip it and start coding
- Undocumented projects lead to scope creep, forgotten decisions, and wasted effort
- Well-structured documentation lets AI agents execute autonomously
- The interview process surfaces edge cases and decisions you'd otherwise discover mid-build

**The Workflow:**

```
"I have an idea" → Interview → Spec → Plan → Project Scaffold → Ready to Build
```

**Phase 1: Discovery Interview** (10-40 minutes depending on complexity)

The AI conducts a structured interview to fully understand what you're building:

1. **Core Understanding** — What exactly are we building? What problem does it solve? Who is it for?
2. **Scope & Intent** — Prototype or production? What's success? What's explicitly NOT in scope?
3. **User Experience** — Walk through the primary user flow step-by-step
4. **Technical Context** — Tech requirements, integration points, constraints
5. **Edge Cases** — Error handling, invalid input, failure modes
6. **Security** — User input, data sensitivity, network exposure, blast radius

The interview is conversational, not a form. The AI follows interesting tangents and challenges assumptions.

**Phase 2: Spec Generation** (automatic)

From the interview, the AI generates a complete `spec.md`:
- Overview and target user
- User stories with Given-When-Then acceptance criteria
- Detailed requirements checklist
- MVP scope (included vs explicitly excluded)
- Technical context and integration points
- Security assessment and mitigations
- Explicit boundaries (what AI should NOT touch)
- Open questions

**Phase 3: Build Plan Generation** (automatic)

From the spec, the AI generates a complete `build-plan.md`:
- Key architectural decisions with rationale
- Component diagram and data flow
- Implementation roadmap in 3-5 testable phases
- Success criteria for each phase (command-based, verifiable)
- Human checkpoints
- Technical details (stack, versions, schema, APIs)
- Risks and mitigations

**Phase 4: Project Scaffold** (automatic)

The AI creates the project structure:
```
projects/active/[project-name]/
├── AGENT.md         # Project entry point
├── spec.md          # Generated specification
├── build-plan.md    # Generated implementation plan
├── decisions.md     # Decision log (seeded from interview)
└── ideas.md         # Future ideas captured during interview
```

Updates root AGENT.md with new project and creates initial task in Pulse.

**Steps:**
1. User says: "I want to start a new project for [idea]"
2. System recognizes project kickoff intent and begins discovery interview
3. AI asks 20-40+ questions across the six interview areas
4. User answers; AI follows up on interesting points, challenges assumptions
5. AI summarizes what it learned and confirms understanding
6. User approves summary or clarifies
7. AI generates spec.md, presents for review
8. User approves or requests changes
9. AI generates build-plan.md, presents for review
10. User approves or requests changes
11. AI scaffolds project folder and files
12. AI creates initial Pulse task: "Start Phase 1 of [project]"
13. User is ready to build with full documentation

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I say "I want to start a new project for a user authentication service"
When the system processes my intent
Then it should recognize this as a project kickoff request
And begin the discovery interview process
And not ask me to fill out templates manually
```

```gherkin
Given the discovery interview is in progress
When the AI asks questions
Then questions should be specific and relevant to my project
And follow up on my answers with deeper questions
And challenge vague statements like "it should be fast"
And cover all six areas: core, scope, UX, technical, edge cases, security
```

```gherkin
Given I've completed the discovery interview
When the AI summarizes what it learned
Then I should see a clear summary of the project scope
And be able to correct any misunderstandings
And confirm before spec generation begins
```

```gherkin
Given the interview is complete and confirmed
When the AI generates the spec
Then it should create a complete spec.md following the template
And include user stories with Given-When-Then acceptance criteria
And mark incomplete sections with [TODO: ...] for my review
And present the spec for my approval before saving
```

```gherkin
Given I approve the generated spec
When the AI generates the build plan
Then it should create a complete build-plan.md following the template
And include 3-5 testable implementation phases
And each phase should have verifiable success criteria
And present the plan for my approval before saving
```

```gherkin
Given I approve both spec and build plan
When the AI scaffolds the project
Then it should create the project folder in projects/active/
And create AGENT.md, spec.md, build-plan.md, decisions.md, ideas.md
And update the root AGENT.md with the new project
And create an initial Pulse task to start Phase 1
And commit all changes to git
```

```gherkin
Given the project kickoff is complete
When an AI agent (or human) reads the project documentation
Then they should be able to start building without additional context
And understand what to build, why, and how
And know what NOT to touch (explicit boundaries)
And verify their work against success criteria
```

```gherkin
Given I want to skip or abbreviate the interview
When I say "I already know what I want, here's the spec"
Then the AI should accept my input and skip to plan generation
Or ask only clarifying questions for gaps
And not force me through the full interview
```

```gherkin
Given decisions are made during the interview
When the project is scaffolded
Then those decisions should be captured in decisions.md
And include the rationale discussed during the interview
And be referenceable during implementation
```

</details>

<details>
<summary><strong>US-15: System Activity Feedback</strong><br>As an Owner, I want to always see clear visual feedback when the system is processing my request so that I know it's working and not frozen — especially on slower operations.</summary>

**Why this matters:**
- Non-technical users (Pat) will assume the app is broken if nothing visually happens for more than 1-2 seconds
- AI operations are inherently variable in duration — Quick Capture might take 2 seconds or 8 seconds depending on complexity
- Transcript processing and document extraction can take 10+ seconds with no visible output
- Trust erodes fast when users can't tell if something is happening or stuck
- Mobile users on slower connections are especially vulnerable to "is it frozen?" anxiety

**Design Principle: Never leave the user staring at nothing.**

Every user-initiated action should produce immediate visual acknowledgment (< 200ms), even if the actual result takes seconds. The feedback should be honest about what's happening — not a fake progress bar, but a real indication of the current step.

**Feedback Tiers:**

| Duration | Feedback Type | Example |
|----------|--------------|---------|
| < 500ms | None needed | File list loads, navigation |
| 500ms - 3s | Subtle spinner/pulse | Quick Capture intent detection |
| 3s - 10s | Spinner + status text | "Analyzing your note...", "Loading project context..." |
| 10s - 30s | Step-by-step progress | Transcript processing: "Parsing speakers... Extracting decisions... Finding related tasks..." |
| 30s+ | Progress with estimate | Document extraction: "Extracting text from 12-page PDF... (page 7 of 12)" |

**Steps:**
1. User initiates an action (Quick Capture, transcript paste, document upload, etc.)
2. System immediately shows visual acknowledgment (spinner, animation, status text)
3. For longer operations, system updates the status text as it progresses through steps
4. If an operation takes unexpectedly long, system shows reassurance: "Still working — this is a large file"
5. When complete, spinner transitions to result (proposal, confirmation, error)
6. If an operation fails, system shows clear error with suggested next steps — not just a silent stop

**Where this applies:**

- **Quick Capture** — "Understanding your input..." → "Finding related context..." → "Preparing proposal..."
- **Deep Work context load** — "Loading project files..." → "Reading recent transcripts..." → "Ready"
- **Transcript processing** — "Parsing transcript..." → "Extracting decisions (found 3)..." → "Matching tasks..." → "Summary ready"
- **Document upload** — "Uploading file..." → "Extracting text..." → "Done — 12 pages indexed"
- **Daily Digest generation** — "Building your digest..." → "Checking tasks..." → "Ready"
- **Search operations** — "Searching Library..." → "Found 7 results"
- **File write/commit** — "Writing file..." → "Committing to git..." → "Done"
- **Interview responses** — "Thinking about your answer..." → follow-up question appears

**Acceptance Criteria (Given-When-Then):**

```gherkin
Given I submit input via Quick Capture
When the AI begins processing
Then I should see a visual indicator within 200ms (spinner, pulse, or animation)
And status text should describe what's happening (e.g., "Analyzing your note...")
And the indicator should remain until the proposal is ready or an error occurs
```

```gherkin
Given I paste a long transcript for processing
When the system begins parsing
Then I should see step-by-step progress updates as each phase completes
And each step should describe what was found (e.g., "Extracting decisions (found 3)...")
And I should never see a static screen for more than 3 seconds without an update
```

```gherkin
Given I upload a large PDF document
When text extraction begins
Then I should see progress indicating pages processed (e.g., "page 4 of 12")
And if extraction takes longer than expected, a reassurance message should appear
And the final state should confirm what was extracted ("Done — 12 pages indexed")
```

```gherkin
Given I enter Deep Work mode for a project
When project context is loading
Then I should see a loading state on the dashboard (skeleton UI or spinner)
And status text should indicate what's being loaded ("Loading project files...")
And the UI should progressively render as sections become available
```

```gherkin
Given an AI operation fails or times out
When the error occurs
Then the spinner should stop and be replaced with a clear error message
And the error should suggest what to do next ("Try again" or "Simplify your input")
And the system should never silently stop with no feedback
```

```gherkin
Given I am on a slow connection or using a local model with slower inference
When any operation takes longer than typical
Then the system should show a "Still working..." reassurance after 5 seconds of no update
And not show a timeout error prematurely
And adapt expectations to the user's environment where possible
```

```gherkin
Given the system is committing changes to git
When the commit is in progress
Then I should see "Saving changes..." or similar feedback
And the confirmation should appear only after the commit succeeds
And if the commit fails, the error should be shown clearly
```

</details>

---

## Detailed Requirements

### Core Functionality
- [ ] Read files from Library folder (scoped access only)
- [ ] Write/create files in Library folder
- [ ] Edit files (append, replace section, insert)
- [ ] Delete files (with confirmation + warning)
- [ ] List files and folders
- [ ] Search file contents
- [ ] List projects with status
- [ ] Get current context/focus
- [ ] List tasks with filters (owner, project, priority, status)
- [ ] Create tasks with auto-generated IDs
- [ ] Extract next actions from vague intentions (convert "work on X" → concrete action)
- [ ] Update tasks (status, priority, owner, context)
- [ ] Complete tasks (move to monthly archive)
- [ ] Process transcripts (extract decisions, tasks, ideas; apply changes)
- [ ] Upload documents to project folders (PDFs, images, files)
- [ ] Extract text from documents where possible (PDF text, OCR for images)
- [ ] List project documents for Deep Work dashboard
- [ ] Search within uploaded documents
- [ ] Generate daily digest (top focus items, yesterday's win, blocked items)
- [ ] Track follow-ups waiting on others' responses
- [ ] Detect user inactivity and generate re-engagement prompts
- [ ] Generate Flow Starter suggestions (small actions to rebuild momentum)
- [ ] Track changes that occurred while user was away
- [ ] Customize digest preferences (item count, sections, project filter)
- [ ] Send digest via email at configured time
- [ ] Process email replies as Quick Capture input
- [ ] **Initial interview flow** (guided conversation to populate Library)
- [ ] **Extract projects, goals, tasks from interview responses**
- [ ] **Generate personalized Library structure from interview**
- [ ] **Preview and approve proposed Library structure**
- [ ] **Re-run interview to add context later** (additive, not destructive)
- [ ] Git auto-commit on all changes
- [ ] Activity log (all actions viewable, auditable)
- [ ] Risk warnings for destructive operations
- [ ] Network isolation (no external access except AI API)

### User Interface
- [ ] Quick Capture modal — minimal UI, text/voice input, shows AI proposal, approve/reject buttons
- [ ] Deep Work view — project dashboard with files, tasks, chat interface, file tree
- [ ] Reference Documents panel — shows uploaded documents for current project in Deep Work mode
- [ ] Document upload zone — drag-drop or file picker for adding documents to projects
- [ ] Document viewer — preview PDFs, images, and other uploaded files
- [ ] Daily Digest card — morning summary with focus items, wins, and blocked items
- [ ] Digest settings panel — customize what appears in daily digest
- [ ] Task List component — filterable, shows hierarchy, status indicators
- [ ] Approval dialog — shows diff/preview, approve/modify/reject options
- [ ] Risk confirmation dialog — extra step for destructive operations with clear warnings
- [ ] Activity log view — chronological list of all AI actions with undo capability
- [ ] Project navigation — browse projects by status (active/completed/archived)
- [ ] Welcome/setup wizard — guides first-time users through AI model and Library setup
- [ ] **Initial interview chat interface** — conversational setup with friendly AI prompts
- [ ] **Library structure preview** — visual tree of proposed files/folders before creation
- [ ] **Interview progress indicator** — shows which phase of setup you're in
- [ ] **Skip/exit interview option** — always accessible to start blank or with partial setup
- [ ] **Activity spinner with status text** — shows what the system is doing during any AI operation (< 200ms response)
- [ ] **Step-by-step progress display** — for long operations (10s+), shows each processing phase with findings
- [ ] **Reassurance message** — "Still working..." appears after 5s of no status update on slow connections/models
- [ ] **Error state with next steps** — replaces spinner on failure with clear message and suggested action
- [ ] **Skeleton/progressive loading** — Deep Work dashboard renders progressively as sections load

### Data & State
- [ ] **Persisted:** All Library files (git-tracked markdown)
- [ ] **Persisted:** Task state in pulse/index.md
- [ ] **Persisted:** Completed tasks in pulse/completed/YYYY-MM.md
- [ ] **Session:** Current project focus (Deep Work mode)
- [ ] **Session:** Conversation history within session
- [ ] **Config:** Library path (BRAINDRIVE_LIBRARY_PATH in .env)
- [ ] **Config:** Auto-commit setting
- [ ] **Config:** Approval mode (all/tiered/none)

---

## Scope

### Feature Type
- [ ] **Prototype** - Proving feasibility, skip polish and edge cases
- [x] **Production** - Full implementation with error handling and polish

### Implementation Location
- [x] **Plugin** - Standalone capability via backend modularization
- [ ] **Core Modification** - Changes to BrainDrive core

**Justification:** The Library Plugin adds API endpoints via the plugin system (Track 2: Backend Modularization). This keeps core lean and allows users to customize without touching core code.

---

## MVP Scope (v1)

### Included
- One-click installer (Mac .dmg, Windows .exe; Linux users use CLI)
- **Initial interview/setup wizard** (populates Library from conversation, solves cold start)
- Library plugin with file CRUD endpoints
- Task management (Pulse) endpoints
- Tool calling for files: read, write, edit, delete, list, search
- Tool calling for tasks: list, create, update, complete
- Transcript processing (paste or attach, extract decisions/tasks/ideas, apply to Library)
- Project document upload (PDFs, images, files to project folders)
- Reference Documents panel in Deep Work mode
- AI can search and reference uploaded documents
- Daily Digest on dashboard and/or email (top 3 focus items, yesterday's win, blocked items)
- Email digest with reply-to-capture (reply to add notes/tasks)
- Customizable digest settings (item count, sections, project filter, delivery method)
- Quick Capture mode (text input, files, tasks, transcripts)
- Deep Work mode (project context, project tasks, reference documents)
- Human approval for all changes (diff view, approve/reject)
- Risk warnings for destructive operations (delete, bulk changes)
- Activity log (view everything the AI has done)
- Network isolation (only AI API calls, no other external access)
- Git auto-commit (full history, undo any change)
- Unified interface (desktop and mobile-responsive)
- Secure remote access via tunneling (Cloudflare Tunnels, Tailscale)
- Single-user support

### Explicitly Excluded (v1)
- Voice input → v1.1
- OCR for images (complex dependency) → v1.1
- Tiered autonomy (auto-approve low-risk) → v2
- Multi-user / permissions → v2
- RAG / embeddings integration → v2
- Semantic search → v2
- Recurring tasks → v2
- External integrations (GitHub Issues, calendars) → v2
- Hosted version deployment → parallel track

---

## Future Versions

### v1.1 (Voice + PWA)
- Voice input for Quick Capture
- PWA installation for mobile home screen
- Hosted deployment option

### v2 (Extended Integration)
- Tiered autonomy (auto-approve low-risk changes)
- RAG/embeddings for semantic search
- MCP server for external AI tool access
- GitHub/GitLab issue integration
- Multi-user with permissions
- Knowledge distillation (consolidate redundant content)

### v3 (Agentic)
- BrainDrive Code integration (coding with Library context)
- Auto PlanSpark (expand one-liners to full plans)
- Proactive AI review (staleness, conflicts, gaps)
- Agent-to-agent communication

### Future Consideration
- VS Code extension for Library access
- Calendar/email integration via MCP
- Knowledge economy (tradeable knowledge packages)

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Any Device                                │
│         Desktop  •  Laptop  •  Phone  •  Tablet                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Secure Access Layer                           │
│    Cloudflare Tunnel  •  Tailscale  •  Direct (local/VPS)       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BrainDrive Interface                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Quick Capture  │  │   Deep Work     │  │   Project Nav   │  │
│  │  (voice/text)   │  │   (focused)     │  │   (browse)      │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
└───────────┼─────────────────────┼─────────────────────┼─────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BrainDrive Backend                            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Library Plugin (API Endpoints)                  ││
│  │  Files: /library/read, /write, /edit, /delete, /list        ││
│  │  Tasks: /library/tasks, /tasks/create, /update, /complete   ││
│  │  Context: /library/projects, /library/context, /search      ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Tool Calling Infrastructure                     ││
│  │  • Model integration (Claude, GPT, local)                   ││
│  │  • File tools + Task tools                                  ││
│  │  • Intent detection                                          ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Local File System                             │
│                                                                  │
│  ~/BrainDrive-Library/                                          │
│  ├── AGENT.md              # Entry point for AI                 │
│  ├── projects/active/      # Project folders                    │
│  ├── pulse/index.md        # Task management                    │
│  ├── transcripts/          # Meeting notes                      │
│  └── system/               # Templates, config                  │
│                                                                  │
│  (Git-tracked, human-readable, portable)                        │
└─────────────────────────────────────────────────────────────────┘
```

### The Library

A folder structure containing your personal/team knowledge — lives on your local machine, VPS, or managed hosting:

```
BrainDrive-Library/
├── AGENT.md              # Entry point for AI agents
├── braindrive/           # Company/product context
├── projects/             # Project folders with specs, plans, decisions
│   ├── active/
│   ├── completed/
│   └── archived/
├── pulse/                # Task management (AI-managed)
│   ├── index.md          # Active tasks (source of truth)
│   ├── backlog.md        # Lower priority / someday
│   └── completed/        # Monthly archives
├── transcripts/          # Meeting and session transcripts
├── topics.md             # Topic index for search
└── system/               # Templates, skills, configuration
```

### Pulse (Task Management)

The `pulse/` folder is the task management system — "the heartbeat of team activity."

**Key characteristics:**
- **AI has full management authority** — Create, update, reprioritize, complete tasks autonomously
- **3-level hierarchy** — Epic → Task → Subtask (no deeper)
- **Single owner required** — Every task has exactly one responsible person
- **Priority-based** — p0 (critical), p1 (high), p2 (normal) — no due dates
- **Project-tagged** — Tasks link to projects via `#project` tags
- **Markdown-native** — Human-readable, git-tracked, works with any AI tool

**Task format:**
```markdown
### T-042: Build authentication system [Dave W] {p0} #braindrive-core
Epic for user auth. Created 2026-01-15 from transcript.

- [ ] **T-043**: Design auth flow [Dave W] {p1}
  Context: Need to decide JWT vs session cookies
  - [ ] T-044: Research OAuth providers [Dave W]
```

**Status markers:** `[ ]` active, `[~]` blocked, `[x]` completed

See [BrainDrive Pulse spec](../../production/braindrive-pulse/spec.md) for full details.

---

## Technical Context

### Plugin Endpoints

**File Operations:**

| Endpoint | Method | Parameters | Response |
|----------|--------|------------|----------|
| `/library/read` | POST | `{ path: string }` | `{ content, metadata }` |
| `/library/write` | POST | `{ path, content }` | `{ success, path }` |
| `/library/edit` | POST | `{ path, operation, content, target? }` | `{ success, diff }` |
| `/library/delete` | POST | `{ path, confirm }` | `{ success }` |
| `/library/list` | GET | `?path=...&recursive=bool` | `{ files, folders }` |
| `/library/search` | POST | `{ query, path? }` | `{ results }` |
| `/library/projects` | GET | none | `{ projects }` |
| `/library/context` | GET | `?project=...` | `{ context }` |

**Document Operations:**

| Endpoint | Method | Parameters | Response |
|----------|--------|------------|----------|
| `/library/documents/upload` | POST | `{ project, file (multipart) }` | `{ success, path, extracted_text? }` |
| `/library/documents/list` | GET | `?project=...` | `{ documents }` |
| `/library/documents/search` | POST | `{ project, query }` | `{ results }` |
| `/library/documents/delete` | POST | `{ path, confirm }` | `{ success }` |

**Daily Digest:**

| Endpoint | Method | Parameters | Response |
|----------|--------|------------|----------|
| `/library/digest` | GET | `?date=YYYY-MM-DD` | `{ focus_items, yesterdays_win, blocked_items, follow_ups, flow_starter, days_away, changes_while_away }` |
| `/library/digest/settings` | GET | none | `{ settings }` |
| `/library/digest/settings` | POST | `{ settings }` | `{ success }` |
| `/library/digest/email` | POST | `{ send_now?: bool }` | `{ success, sent_to }` |
| `/library/digest/email/inbound` | POST | `{ from, subject, body }` | `{ captured, processed }` |

**Task Operations (Pulse):**

| Endpoint | Method | Parameters | Response |
|----------|--------|------------|----------|
| `/library/tasks` | GET | `?owner, project, priority, status` | `{ tasks }` |
| `/library/tasks/create` | POST | `{ title, owner, priority?, project?, context?, parent? }` | `{ success, task }` |
| `/library/tasks/update` | POST | `{ id, status?, priority?, owner?, context? }` | `{ success, task }` |
| `/library/tasks/complete` | POST | `{ id, note? }` | `{ success }` |

**Transcript Processing:**

| Endpoint | Method | Parameters | Response |
|----------|--------|------------|----------|
| `/library/transcript/process` | POST | `{ content, source?, title?, participants? }` | `{ decisions, completed_tasks, new_tasks, ideas }` |
| `/library/transcript/apply` | POST | `{ changes, transcript_content }` | `{ success, applied, transcript_path }` |

**Initial Interview (Setup):**

| Endpoint | Method | Parameters | Response |
|----------|--------|------------|----------|
| `/library/interview/start` | POST | `{ mode?: "full" \| "quick" \| "additive" }` | `{ session_id, first_question }` |
| `/library/interview/respond` | POST | `{ session_id, response }` | `{ follow_up, extracted_items, phase, progress }` |
| `/library/interview/preview` | GET | `?session_id=...` | `{ proposed_structure, files[], projects[], tasks[] }` |
| `/library/interview/apply` | POST | `{ session_id, modifications? }` | `{ success, created_files[], created_projects[], created_tasks[] }` |
| `/library/interview/skip` | POST | `{ session_id?, create_minimal?: bool }` | `{ success }` |
| `/library/interview/status` | GET | none | `{ interview_completed, can_rerun }` |

### Tool Definitions

```yaml
tools:
  # File Operations
  - name: read_file
    description: Read contents of a file from the Library
    parameters:
      path: string (relative to Library root)

  - name: write_file
    description: Create or overwrite a file in the Library
    parameters:
      path: string
      content: string

  - name: edit_file
    description: Edit an existing file (append, replace section, etc.)
    parameters:
      path: string
      operation: append | replace | insert
      content: string
      target: string (for replace/insert)

  - name: delete_file
    description: Delete a file from the Library
    parameters:
      path: string

  - name: list_files
    description: List files in a directory
    parameters:
      path: string
      recursive: boolean

  - name: search_files
    description: Search for content across Library files
    parameters:
      query: string
      path: string (optional, scope search)

  # Task Operations (Pulse)
  - name: list_tasks
    description: List tasks from pulse/index.md with optional filters
    parameters:
      owner: string (optional)
      project: string (optional)
      priority: p0 | p1 | p2 (optional)
      status: active | blocked | all (default: active)

  - name: create_task
    description: Create a new task in pulse/index.md. Converts vague intentions to executable next actions.
    parameters:
      title: string (should be a concrete next action, not a vague intention)
      owner: string (required)
      priority: p0 | p1 | p2 (default: p2)
      project: string (optional)
      context: string (optional)
      parent: string (optional, parent task ID)
    behavior:
      - If title is vague (e.g., "work on website"), ask for clarification or propose concrete action
      - Store executable next action, not intention

  - name: update_task
    description: Update an existing task
    parameters:
      id: string (task ID, e.g., T-042)
      status: active | blocked (optional)
      priority: p0 | p1 | p2 (optional)
      owner: string (optional)
      context: string (optional)

  - name: complete_task
    description: Mark a task as complete
    parameters:
      id: string (task ID)
      note: string (optional)

  # Transcript Processing
  - name: process_transcript
    description: Parse a meeting transcript and extract decisions, tasks, and ideas
    parameters:
      content: string (transcript text or VTT content)
      source: string (optional, e.g., "zoom", "teams", "manual")
      meeting_title: string (optional)
      participants: string[] (optional)
    returns:
      decisions: array of { text, project?, context }
      completed_tasks: array of { id, evidence }
      new_tasks: array of { title, owner, project?, context }
      ideas: array of { text, project?, context }
      transcript_path: string (proposed save location)

  # Document Operations
  - name: list_documents
    description: List uploaded documents for a project
    parameters:
      project: string (project path or name)
    returns:
      documents: array of { name, path, type, size, uploaded_at, has_text }

  - name: search_documents
    description: Search within uploaded documents for a project
    parameters:
      project: string (project path or name)
      query: string (search query)
    returns:
      results: array of { document_path, matches, context }

  - name: get_document_content
    description: Get extracted text content from an uploaded document
    parameters:
      path: string (document path relative to Library)
    returns:
      content: string (extracted text, or error if not extractable)
      type: string (file type)
      extractable: boolean

  # Daily Digest
  - name: get_daily_digest
    description: Generate personalized daily digest with focus items, wins, follow-ups, and re-engagement prompts
    parameters:
      date: string (optional, YYYY-MM-DD, defaults to today)
    returns:
      focus_items: array of { task_id, title, priority, project }
      yesterdays_win: { task_id, title, project, completed_at } | null
      blocked_items: array of { task_id, title, blocked_on }
      follow_ups: array of { item, waiting_since, response_received? }
      flow_starter: { action, time_estimate, project } | null (shown when returning after inactivity)
      days_since_last_session: number
      days_since_last_task_added: number
      changes_while_away: array of { type, description } (new uploads, replies, etc.)
      context: string (any time-sensitive notes)

  # Initial Interview (Setup)
  - name: start_interview
    description: Begin the initial setup interview to populate the Library with user context
    parameters:
      mode: "full" | "quick" | "additive" (default: "full")
        # full: Complete interview for new users (~10 min)
        # quick: Abbreviated version (~3 min)
        # additive: Add to existing Library without replacing
    returns:
      session_id: string (for continuing the conversation)
      first_question: string
      estimated_duration: string

  - name: process_interview_response
    description: Process user's response during setup interview and generate follow-up
    parameters:
      session_id: string
      response: string (user's answer to the current question)
    returns:
      follow_up: string | null (next question, or null if phase complete)
      extracted_items: {
        projects: array of { name, description, status }
        goals: array of { text, area }
        tasks: array of { title, project?, priority? }
        people: array of { name, role?, context? }
        life_areas: array of string
      }
      phase: string (current interview phase)
      progress: number (0-100)
      can_finish_early: boolean

  - name: preview_interview_results
    description: Show user what Library structure will be created from interview
    parameters:
      session_id: string
    returns:
      proposed_structure: {
        folders: array of { path, purpose }
        files: array of { path, content_preview, source_question }
        projects: array of { name, folder_path, initial_files }
        tasks: array of { title, owner, priority, project }
      }
      summary: string (AI's summary of what was learned)

  - name: apply_interview_results
    description: Create the Library structure from completed interview
    parameters:
      session_id: string
      modifications: object (optional, user's edits to proposed structure)
    returns:
      success: boolean
      created_files: array of string
      created_projects: array of string
      created_tasks: array of { id, title }
      git_commit_sha: string
```

### Integration Points
- [x] **API Bridge** - All /library/* endpoints for file and task operations
- [ ] **Events Bridge** - Emit events on file changes, task completions (v2)
- [x] **Theme Bridge** - UI components use BrainDrive theme system
- [x] **Settings Bridge** - Library path, auto-commit, approval mode settings
- [ ] **Page Context Bridge** - Deep Work mode tracks current project
- [x] **Plugin State Bridge** - Current project focus persisted in session

### Dependencies
- **Backend modularization** (Track 2) — Plugin must be able to add API endpoints
- **Tool calling infrastructure** (Track 4) — AI must be able to call tools
- **Git** — Installed on user's system for version control
- **Existing BrainDrive auth** — Plugin endpoints use existing authentication

### Constraints
- **Performance:** Quick Capture < 5 seconds end-to-end; Deep Work context load < 3 seconds
- **Storage:** Library is local files; no database required for v1
- **Offline:** Must work fully offline (local models supported)

---

## Security Considerations

### Risk Level
- [ ] **Low** - No user input, no new APIs, no sensitive data
- [x] **Medium** - Handles user input, new API endpoints, stores user data
- [ ] **High** - Executes user code, touches auth/credentials, exposes new network surfaces

### Threat Assessment
- **User input:** File paths and content are user-provided. Path validation required to prevent traversal. Content is markdown (no code execution).
- **Code execution:** No user code execution. File operations only, no shell commands.
- **Data sensitivity:** Library contains user's personal knowledge. All local, no cloud sync in v1. Git history provides audit trail.
- **Network surface:** New API endpoints require authentication. Same auth as existing BrainDrive endpoints.
- **Blast radius:** Single user's Library. No cross-user access. Compromised endpoint could read/write user's Library folder only.

### Required Mitigations
- [x] Path validation — Reject any path outside Library folder (no `../`, no absolute paths outside)
- [x] Authentication — All endpoints require valid BrainDrive session
- [x] Human approval — All write operations require explicit user approval (v1)
- [x] Git versioning — All changes tracked, rollback available
- [ ] Rate limiting — Prevent rapid-fire operations (v2)
- [ ] Sanitization warnings — Warn if file might contain secrets

### Notes
The approval model is the primary security control. Nothing is written without user consent. Git provides full audit trail and rollback capability.

---

## Explicit Boundaries

> **For AI Agents:** These boundaries define what is OUT OF SCOPE for this feature. Do not modify, touch, or refactor anything in these areas.

### Do Not Modify
- [ ] BrainDrive core backend (this is a plugin, not a core change)
- [ ] Authentication/authorization system (use existing)
- [ ] Other plugins (Library is self-contained)
- [ ] Files outside the configured Library path

### Do Not Introduce
- [ ] Database dependencies (use file system only)
- [ ] Cloud storage/sync (local only for v1)
- [ ] Shell command execution (file ops only)
- [ ] Custom authentication (use existing BrainDrive auth)

### Security Boundaries
- [ ] Never access files outside Library folder
- [ ] Never execute shell commands
- [ ] Never bypass approval flow
- [ ] Never commit secrets or credentials
- [ ] Never modify git config or hooks

### Out of Scope (Even if Related)
- [ ] RAG/embeddings integration (v2)
- [ ] Multi-user permissions (v2)
- [ ] Voice transcription (v1.1)
- [ ] GitHub Issues sync (v2)

---

## Open Questions

- [x] ~~Should task endpoints be separate plugin or part of Library?~~ → Part of Library (D19)
- [ ] What's the maximum file size we should support reading?
- [x] ~~Should we support binary files (images) or markdown only?~~ → Yes, support documents (PDFs, images, files) via upload (US-11)
- [ ] How do we handle merge conflicts if user edits file while AI is proposing changes?
- [ ] Should Deep Work mode auto-refresh when files change externally?
- [ ] What PDF/document extraction library should we use? (PyPDF2, pdfplumber, etc.)
- [ ] Should OCR for images be in v1 or deferred? (adds complexity + dependencies)
- [ ] Maximum document upload size? (suggest 50MB for v1)
- [ ] Should extracted document text be cached or re-extracted on each search?

---

## Success Definition

When this feature is complete, users will be able to:
1. **Install in one click** — Download, double-click, done. No terminal, no technical setup.
2. **Start warm, not cold** — A 10-minute interview populates the Library with projects, goals, and context from day one
3. **Capture instantly** — Notes, decisions, and tasks in under 5 seconds via Quick Capture
4. **Process transcripts** — Drop a meeting transcript and have decisions, tasks, ideas extracted and applied
5. **Upload reference materials** — Add PDFs, images, documents to any project and have the AI reference them
6. **Start the day with clarity** — See a personalized daily digest (dashboard or email) with focus items and wins
7. **Restart without guilt** — Fall off for days/weeks and pick back up with a 10-minute brain dump — no catch-up required
8. **Work with full context** — Any area of life with context loaded automatically (no re-explaining)
9. **Manage tasks naturally** — Have the AI manage their task list across all life areas
10. **Stay in control** — See exactly what the AI proposes, approve or reject, with clear diff views
11. **Trust the system** — Know that risky operations are flagged, nothing happens without approval, everything is logged
12. **Recover anything** — All changes tracked in git, undo any action
13. **Access from anywhere** — Same experience on desktop, laptop, or phone
14. **Feel understood** — Like they're talking to an assistant who actually knows them

> "When I would rather use BrainDrive for this than Claude Code, we're done." — Dave W

---

## Approval

- [ ] Reviewed by: _______________
- [ ] Date: _______________
- [ ] Ready for Planning: [x]

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [build-plan.md](./build-plan.md) | Implementation phases and tasks |
| [decisions.md](./decisions.md) | Key architectural decisions (D13-D19) |
| [future-vision.md](./future-vision.md) | v2/v3 roadmap |
| [BrainDrive Pulse spec](../../production/braindrive-pulse/spec.md) | Task management system details |
| [braindrive/current-strategy.md](../../braindrive/current-strategy.md) | Strategic context |

---

## Appendix: Migration from Previous Approach

This spec supersedes the previous "Librarian CLI" approach documented in the archive folder. Key changes:

| Previous (CLI) | Current (Plugin) |
|----------------|------------------|
| Standalone Python CLI | BrainDrive plugin |
| Terminal-based interaction | Interface-first |
| Materialized `.ai-context/` folders | Direct file system access |
| Complex approval workflows | Simple approve/deny |
| Agent-orchestrated CLI commands | Native tool calling |

The underlying concept (file system as brain, AI manages context) remains the same. The delivery mechanism changed from CLI to integrated plugin.

---

*Next: Review `build-plan.md` and update for template compliance*







