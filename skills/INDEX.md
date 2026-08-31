# VibeMind Skill Library Index

_Generated: 2026-05-11T22:01:15+00:00_  
_Total skills: **305** across **27** app namespaces · avg confidence: **0.91**_

This index lists every SKILL.md in `vibemind-os/skills/`. 
Skills are auto-discoverable via `_loader.py` and semantically searchable via Qdrant (`vibemind_skills` collection).

## Namespaces

| App | Skills | Origin |
|---|---:|---|
| [`aws`](#aws) | 5 | local |
| [`chat-plugin`](#chat-plugin) | 1 | local |
| [`chrome`](#chrome) | 4 | local |
| [`claude-desktop`](#claude-desktop) | 2 | local |
| [`composio`](#composio) | 6 | local |
| [`data`](#data) | 1 | local |
| [`dev`](#dev) | 16 | local |
| [`devops`](#devops) | 19 | local |
| [`excel`](#excel) | 22 | local |
| [`file-explorer`](#file-explorer) | 3 | local |
| [`hr`](#hr) | 13 | local |
| [`manager-skill`](#manager-skill) | 1 | local |
| [`mcp-bridge`](#mcp-bridge) | 1 | local |
| [`notepad`](#notepad) | 1 | local |
| [`office`](#office) | 17 | local |
| [`openclaw-official`](#openclaw-official) | 22 | local |
| [`orchestrator`](#orchestrator) | 1 | local |
| [`relay-skill`](#relay-skill) | 1 | local |
| [`research`](#research) | 1 | local |
| [`roarboot`](#roarboot) | 12 | local |
| [`rowboat`](#rowboat) | 1 | local |
| [`science`](#science) | 136 | local |
| [`security`](#security) | 1 | local |
| [`tapestry`](#tapestry) | 7 | local |
| [`utility`](#utility) | 4 | local |
| [`vscode`](#vscode) | 3 | local |
| [`word`](#word) | 4 | local |

## aws

_5 skills_

| Name | Description |
|---|---|
| `aws-agentic-ai` | AWS Bedrock AgentCore comprehensive expert for deploying and managing AI agents at scale. Use when working with any AgentCore service including Gateway, Runtime, Memory, Identity, Code Interpreter,... |
| `aws-cdk-development` | AWS Cloud Development Kit (CDK) expert for building cloud infrastructure with TypeScript/Python. Use when creating CDK stacks, defining CDK constructs, implementing infrastructure as code, or when ... |
| `aws-cost-operations` | AWS cost optimization, monitoring, and operational excellence expert. Use when analyzing AWS bills, estimating costs, setting up CloudWatch alarms, querying logs, auditing CloudTrail activity, or a... |
| `aws-mcp-setup` | Configure AWS MCP servers for documentation search and API access. Use when setting up AWS MCP, configuring AWS documentation tools, troubleshooting MCP connectivity, or when user mentions aws-mcp,... |
| `aws-serverless-eda` | AWS serverless and event-driven architecture expert based on Well-Architected Framework. Use when building serverless APIs, Lambda functions, REST APIs, microservices, or async workflows. Covers La... |

## chat-plugin

_1 skills_

| Name | Description |
|---|---|
| `chat-plugin-Claude Code Orchestration` | Skill for orchestrating Claude Code sessions from OpenClaw. Covers launching, monitoring, multi-turn interaction, lifecycle management, notifications, and parallel work patterns. |

## chrome

_4 skills_

| Name | Description |
|---|---|
| `chrome-open-url` | Oeffne eine URL in einem neuen Chrome-Tab (Strg+T + URL + Enter). |
| `chrome-playwright-extract-text` | Extrahiere strukturierten Text/Daten von einer Webseite via Playwright-MCP read_page. |
| `chrome-playwright-fill-form` | Fuelle ein HTML-Formular auf einer Seite via Playwright-MCP (deterministische Selektoren). |
| `chrome-search-google` | Öffne einen neuen Tab in Chrome und suche auf Google nach einem gegebenen Suchbegriff. |

## claude-desktop

_2 skills_

| Name | Description |
|---|---|
| `claude-desktop-new-chat` | Starte einen neuen Chat in der Claude-Desktop-App. |
| `claude-desktop-send-message` | Tippe eine Nachricht ins Claude-Desktop-Eingabefeld und schicke sie ab. |

## composio

_6 skills_

| Name | Description |
|---|---|
| `composio-content-research-writer` | Assists in writing high-quality content by conducting research, adding citations, improving hooks, iterating on outlines, and providing real-time feedback on each section. Transforms your writing p... |
| `composio-image-enhancer` | Improves the quality of images, especially screenshots, by enhancing resolution, sharpness, and clarity. Perfect for preparing images for presentations, documentation, or social media posts. |
| `composio-meeting-insights-analyzer` | Analyzes meeting transcripts and recordings to uncover behavioral patterns, communication insights, and actionable feedback. Identifies when you avoid conflict, use filler words, dominate conversat... |
| `composio-tailored-resume-generator` | Analyzes job descriptions and generates tailored resumes that highlight relevant experience, skills, and achievements to maximize interview chances |
| `composio-twitter-algorithm-optimizer` | Analyze and optimize tweets for maximum reach using Twitter's open-source algorithm insights. Rewrite and edit user tweets to improve engagement and visibility based on how the recommendation syste... |
| `composio-youtube-downloader` | Download YouTube videos with customizable quality and format options. Use this skill when the user asks to download, save, or grab YouTube videos. Supports various quality settings (best, 1080p, 72... |

## data

_1 skills_

| Name | Description |
|---|---|
| `data-csv-data-summarizer` | Analyzes CSV files, generates summary stats, and plots quick visualizations using Python and pandas. |

## dev

_16 skills_

| Name | Description |
|---|---|
| `dev-brainstorming` | You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation. |
| `dev-dispatching-parallel-agents` | Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies |
| `dev-executing-plans` | Use when you have a written implementation plan to execute in a separate session with review checkpoints |
| `dev-finishing-a-development-branch` | Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup |
| `dev-move-code-quality` | Analyzes Move language packages against the official Move Book Code Quality Checklist. Use this skill when reviewing Move code, checking Move 2024 Edition compliance, or analyzing Move packages for... |
| `dev-pict-test-designer` | Design comprehensive test cases using PICT (Pairwise Independent Combinatorial Testing) for any piece of requirements or code. Analyzes inputs, generates PICT models with parameters, values, and co... |
| `dev-receiving-code-review` | Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performat... |
| `dev-requesting-code-review` | Use when completing tasks, implementing major features, or before merging to verify work meets requirements |
| `dev-subagent-driven-development` | Use when executing implementation plans with independent tasks in the current session |
| `dev-systematic-debugging` | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| `dev-test-driven-development` | Use when implementing any feature or bugfix, before writing implementation code |
| `dev-using-git-worktrees` | Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or git worktree fallback |
| `dev-using-superpowers` | Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response including clarifying questions |
| `dev-verification-before-completion` | Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evide... |
| `dev-writing-plans` | Use when you have a spec or requirements for a multi-step task, before touching code |
| `dev-writing-skills` | Use when creating new skills, editing existing skills, or verifying skills work before deployment |

## devops

_19 skills_

| Name | Description |
|---|---|
| `devops-architecture-diagram-creator` | Create comprehensive HTML architecture diagrams showing data flows, business objectives, features, technical architecture, and deployment. Use when users request system architecture, project docume... |
| `devops-code-auditor` | Performs comprehensive codebase analysis covering architecture, code quality, security, performance, testing, and maintainability. Use when user wants to audit code quality, identify technical debt... |
| `devops-code-execution` | Execute Python code locally with marketplace API access for 90%+ token savings on bulk operations. Activates when user requests bulk operations (10+ files), complex multi-step workflows, iterative ... |
| `devops-code-refactor` | Perform bulk code refactoring operations like renaming variables/functions across files, replacing patterns, and updating API calls. Use when users request renaming identifiers, replacing deprecate... |
| `devops-code-transfer` | Transfer code between files with line-based precision. Use when users request copying code from one location to another, moving functions or classes between files, extracting code blocks, or insert... |
| `devops-codebase-documenter` | Generates comprehensive documentation explaining how a codebase works, including architecture, key components, data flow, and development guidelines. Use when user wants to understand unfamiliar co... |
| `devops-conversation-analyzer` | Analyzes your Claude Code conversation history to identify patterns, common mistakes, and opportunities for workflow improvement. Use when user wants to understand usage patterns, optimize workflow... |
| `devops-dashboard-creator` | Create HTML dashboards with KPI metric cards, bar/pie/line charts, progress indicators, and data visualizations. Use when users request dashboards, metrics displays, KPI visualizations, data charts... |
| `devops-ensemble-solving` | Generate multiple diverse solutions in parallel and select the best. Use for architecture decisions, code generation with multiple valid approaches, or creative tasks where exploring alternatives i... |
| `devops-feature-planning` | Break down feature requests into detailed, implementable plans with clear tasks. Use when user requests a new feature, enhancement, or complex change. |
| `devops-file-operations` | Analyze files and get detailed metadata including size, line counts, modification times, and content statistics. Use when users request file information, statistics, or analysis without modifying f... |
| `devops-flowchart-creator` | Create HTML flowcharts and process diagrams with decision trees, color-coded stages, arrows, and swimlanes. Use when users request flowcharts, process diagrams, workflow visualizations, or decision... |
| `devops-git-pushing` | Stage, commit, and push git changes with conventional commit messages. Use when user wants to commit and push changes, mentions pushing to remote, or asks to save and push their work. Also activate... |
| `devops-linear` | Work with Linear issues via CLI - use this skill whenever the user asks about Linear issues, creating, updating, commenting on, or deleting issues, or checking issue status and details |
| `devops-project-bootstrapper` | Sets up new projects or improves existing projects with development best practices, tooling, documentation, and workflow automation. Use when user wants to start a new project, improve project stru... |
| `devops-review-implementing` | Process and implement code review feedback systematically. Use when user provides reviewer comments, PR feedback, code review notes, or asks to implement suggestions from reviews. |
| `devops-technical-doc-creator` | Create HTML technical documentation with code blocks, API workflows, system architecture diagrams, and syntax highlighting. Use when users request technical documentation, API docs, API references,... |
| `devops-test-fixing` | Run tests and systematically fix all failing tests using smart error grouping. Use when user asks to fix failing tests, mentions test failures, runs test suite and failures occur, or requests to ma... |
| `devops-timeline-creator` | Create HTML timelines and project roadmaps with Gantt charts, milestones, phase groupings, and progress indicators. Use when users request timelines, roadmaps, Gantt charts, project schedules, or m... |

## excel

_22 skills_

| Name | Description |
|---|---|
| `excel-autofilter-on` | Aktiviert AutoFilter (Strg+Shift+L). |
| `excel-clear-cell` | Loescht den Inhalt der aktuellen Zelle (Entf-Taste). |
| `excel-fill-cell` | Schreibe einen Wert in eine bestimmte Excel-Zelle. |
| `excel-fill-range` | Pastet eine 2D-Liste an Cell start_cell. |
| `excel-find-replace` | Strg+H = Suchen und Ersetzen. |
| `excel-format-as-table` | Markiere Range + Strg+T = formatiere als Tabelle. |
| `excel-formula-average` | Schreibt =MITTELWERT(A1:A3). |
| `excel-formula-sum` | Schreibt =SUMME(A1:A3) und validiert das Ergebnis. |
| `excel-formula-today` | Schreibt =HEUTE() und validiert ein Datum. |
| `excel-goto-cell` | Springe in Microsoft Excel zu einer bestimmten Zelle (z.B. A1, B5, AB42). |
| `excel-jump-to-a1` | Springe in Excel zur Zelle A1 (Strg+Pos1/Strg+Home) |
| `excel-jump-to-end` | Strg+Ende = springe zur letzten verwendeten Zelle. |
| `excel-make-bold` | Macht die selektierte Zelle fett (Strg+B). |
| `excel-named-range-goto` | Strg+G + Range/Name eingeben + Enter. |
| `excel-new-sheet` | Shift+F11 = neues Tabellenblatt. |
| `excel-page-setup-landscape` | Setzt Seitenausrichtung auf Querformat. |
| `excel-paste-skill-list-table` | Pastet die komplette VibeMind-Skill-Library als 2D-Tabelle nach Excel A1 |
| `excel-rename-sheet` | Doppelklick auf Sheet-Tab oder F2/Alt+H,O,R = Sheet umbenennen. |
| `excel-save-as` | Speichere die aktive Excel-Mappe unter einem neuen Pfad/Namen. |
| `excel-save-ctrl-s` | Strg+S = speichert die aktive Mappe (oder oeffnet Save-Dialog wenn neu). |
| `excel-select-range` | Markiere einen Zellbereich in Excel (z.B. A1:C5). |
| `excel-switch-sheet-next` | Strg+Bild-ab = naechstes Tabellenblatt aktivieren. |

## file-explorer

_3 skills_

| Name | Description |
|---|---|
| `file-explorer-address-bar-navigate` | Navigiere im File-Explorer ueber die Adressleiste zu einem absoluten Pfad. |
| `file-explorer-create-folder` | Erstelle einen neuen Ordner im aktuellen File-Explorer-Fenster. |
| `file-explorer-rename` | Benenne die aktuell ausgewaehlte Datei/Ordner um (F2). |

## hr

_13 skills_

| Name | Description |
|---|---|
| `hr-arbeitszeugnis-vorlage` | Arbeitszeugnis-Vorlage als Word-Dokument mit Standard-Formulierungen und Platzhaltern. |
| `hr-bewerbungs-tracker` | Bewerbungs-Tracker mit Status-Pipeline (Sichtung -> Interview -> Angebot/Absage), Status-Farbcodierung. |
| `hr-kennzahlen-dashboard` | HR-Kennzahlen-Dashboard mit Daten-Sheet (monatlich) und KPIs-Sheet (Fluktuation, Krankenquote, Recruiting-Trichter). |
| `hr-krankenstand-tracker` | Krankenstand-Tracker mit Q1-Q4-Tabs + Jahres-Summary mit Krankenquoten-Berechnung. |
| `hr-lohnabrechnung-hilfstabelle` | Lohnabrechnung-Hilfstabelle mit echten Beitragsformeln (RV, KV, AV, PV, LSt) und Parameter-Sheet. |
| `hr-mitarbeiter-stammdatenliste` | Mitarbeiter-Stammdatenliste mit allen relevanten HR-Feldern, Header bold + frozen, Status-Farbcodierung. |
| `hr-mitarbeitergespraech-protokoll` | Mitarbeitergespräch-Protokoll als Word-Dokument mit Sektionen für Rückblick, Ziele, Entwicklung, Gehalt. |
| `hr-offboarding-checkliste` | Offboarding-Checkliste mit Kündigungsfristen, IT-Asset-Rückgabe, Steuer/SV-Abmeldung. |
| `hr-onboarding-checkliste` | Onboarding-Checkliste Multi-Phase (Vor 1. Tag, Tag 1, Woche 1, Monat 1, 100-Tage) mit Status-Färbung. |
| `hr-spesen-abrechnung` | Spesen-Abrechnung mit Kategorien, MwSt-Berechnung und Genehmigungs-Footer. |
| `hr-stundenzettel-monatsvorlage` | Stundenzettel-Monatsvorlage mit Wochen-Sheets (KW18-KW21) + Summary-Sheet mit Cross-Sheet-Formeln. |
| `hr-urlaubs-uebersicht` | Urlaubs-Übersicht mit Anträge-Sheet (Tage via NETTOARBEITSTAGE) + Resturlaub-Sheet. |
| `hr-vibemind-onboarding-checklist` | Erstellt Onboarding-Checkliste fuer neuen VibeMind-Mitarbeiter direkt als xlsx via openpyxl, oeffnet in Excel, validiert via openpyxl |

## manager-skill

_1 skills_

| Name | Description |
|---|---|
| `manager-skill-onboarding` | This skill should be used when the user asks to "set up OpenClaw", "get started", "onboard me", "plan my setup", or "help me choose channels". Conducts an interactive interview, then generates a ta... |

## mcp-bridge

_1 skills_

| Name | Description |
|---|---|
| `mcp-bridge-openclaw-management` | This skill should be used when the user wants to interact with OpenClaw, delegate tasks to their AI assistant, or check gateway status. Activates for AI assistant delegation and orchestration. |

## notepad

_1 skills_

| Name | Description |
|---|---|
| `notepad-write-text` | Automates writing a specified text into Notepad. |

## office

_17 skills_

| Name | Description |
|---|---|
| `office-algorithmic-art` | Creating algorithmic art using p5.js with seeded randomness and interactive parameter exploration. Use this when users request creating art using code, generative art, algorithmic art, flow fields,... |
| `office-brand-guidelines` | Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidelines, visual formatt... |
| `office-canvas-design` | Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create ... |
| `office-claude-api` | Build, debug, and optimize Claude API / Anthropic SDK apps. Apps built with this skill should include prompt caching. Also handles migrating existing Claude API code between Claude model versions (... |
| `office-doc-coauthoring` | Guide users through a structured workflow for co-authoring documentation. Use when user wants to write documentation, proposals, technical specs, decision docs, or similar structured content. This ... |
| `office-docx` | Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produ... |
| `office-frontend-design` | Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples in... |
| `office-internal-comms` | A set of resources to help me write all kinds of internal communications, using the formats that my company likes to use. Claude should use this skill whenever asked to write some sort of internal ... |
| `office-mcp-builder` | Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate exte... |
| `office-pdf` | Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, r... |
| `office-pptx` | Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text fro... |
| `office-skill-creator` | Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a sk... |
| `office-slack-gif-creator` | Knowledge and utilities for creating animated GIFs optimized for Slack. Provides constraints, validation tools, and animation concepts. Use when users request animated GIFs for Slack like "make me ... |
| `office-theme-factory` | Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifac... |
| `office-web-artifacts-builder` | Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state ma... |
| `office-webapp-testing` | Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browse... |
| `office-xlsx` | Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., ... |

## openclaw-official

_22 skills_

| Name | Description |
|---|---|
| `openclaw-official-clawsweeper` | Use for all ClawSweeper work: OpenClaw issue/PR sweep reports, commit-review reports, repair jobs, cloud fix PRs, @clawsweeper maintainer mention commands, trusted ClawSweeper-reviewed autofix/auto... |
| `openclaw-official-crabbox` | Use Crabbox for OpenClaw remote Linux validation. Default to Blacksmith Testbox; includes direct Blacksmith and owned AWS/Hetzner fallback notes when Crabbox fails. |
| `openclaw-official-discord-clawd` | Use to talk to the Discord-backed OpenClaw agent/session; not for archive search. |
| `openclaw-official-gitcrawl` | Use gitcrawl for OpenClaw issue and PR archive search, duplicate discovery, related-thread clustering, and local GitHub mirror freshness checks. |
| `openclaw-official-openclaw-debugging` | Debug OpenClaw model, provider, tool-surface, code-mode, streaming, and live/Crabbox behavior by choosing the right logs, probes, and proof path before changing code. |
| `openclaw-official-openclaw-docs` | Write or review high-quality OpenClaw developer documentation. |
| `openclaw-official-openclaw-ghsa-maintainer` | Inspect, patch, validate, publish, or confirm OpenClaw GHSA security advisories and private-fork state. |
| `openclaw-official-openclaw-parallels-smoke` | Run, rerun, debug, or interpret OpenClaw Parallels install, onboarding, gateway smoke, and upgrade checks. |
| `openclaw-official-openclaw-pr-maintainer` | Use immediately for any pasted OpenClaw GitHub issue or PR URL/number, and for OpenClaw issue/PR review, triage, duplicate search, opener identity/who wrote it, author account age/activity, comment... |
| `openclaw-official-openclaw-pre-release-plugin-testing` | Plan and run pre-release OpenClaw plugin validation across bundled plugins, package artifacts, lifecycle commands, doctor/fix, config round-trip, gateway startup, SDK compatibility, Docker E2E, Pac... |
| `openclaw-official-openclaw-qa-testing` | Run, watch, debug, extend, or explain OpenClaw qa-lab and qa-channel scenarios, artifacts, and live lanes. |
| `openclaw-official-openclaw-release-maintainer` | Prepare or verify OpenClaw stable/beta releases, changelogs, release notes, publish commands, and artifacts. |
| `openclaw-official-openclaw-secret-scanning-maintainer` | Triage, redact, clean up, and resolve OpenClaw GitHub Secret Scanning alerts in issues or PRs. |
| `openclaw-official-openclaw-small-bugfix-sweep` | Fix only small, high-certainty OpenClaw bugs from a pasted issue/PR list after deep code review. |
| `openclaw-official-openclaw-test-heap-leaks` | Investigate OpenClaw pnpm test memory growth, Vitest OOMs, RSS spikes, and heap snapshot deltas. |
| `openclaw-official-openclaw-test-performance` | Benchmark, diagnose, and optimize OpenClaw test and plugin-suite runtime, import hotspots, CPU/RSS, heap growth, and slow coverage paths. |
| `openclaw-official-openclaw-testing` | Choose, run, rerun, or debug OpenClaw tests, CI checks, Docker E2E lanes, release validation, and the cheapest safe verification path. |
| `openclaw-official-optimizetests` | Optimize OpenClaw slow tests, imports, misplaced coverage, and CI wall time without dropping coverage. |
| `openclaw-official-parallels-discord-roundtrip` | Run macOS Parallels smoke with Discord send, host verification, host reply, and guest readback proof. |
| `openclaw-official-security-triage` | Triage OpenClaw security advisories, drafts, and GHSA reports with shipped-tag and trust-model proof. |
| `openclaw-official-tag-duplicate-prs-issues` | Use gitcrawl to search duplicate OpenClaw PRs/issues, group related work in prtags, and sync duplicate state to GitHub. |
| `openclaw-official-telegram-crabbox-e2e-proof` | Use when reviewing, reproducing, or proving OpenClaw Telegram behavior with a real Telegram user on Crabbox, including PR review workflows that need an agent-controlled Telegram Desktop recording, ... |

## orchestrator

_1 skills_

| Name | Description |
|---|---|
| `orchestrator-claw-orchestrator` | Manage persistent coding sessions across Claude Code, Codex, Gemini, Cursor, and OpenCode engines. Use when orchestrating multi-engine coding agents, starting/sending/stopping sessions, running mul... |

## relay-skill

_1 skills_

| Name | Description |
|---|---|
| `relay-skill-openclaw-bridge` | Bridge to an OpenClaw agent. Use when user says "Ask OpenClaw", "OpenClaw mode on/off", or wants to relay a question or task to the OpenClaw agent. Any capabilities, skills, or tools available on t... |

## research

_1 skills_

| Name | Description |
|---|---|
| `research-family-history-planning` | Provides assistance with planning family history and genealogy research projects. |

## roarboot

_12 skills_

| Name | Description |
|---|---|
| `roarboot-export-folder` | Exportiert eine Roarboot-Knowledge-Folder nach Excel, fragt den User interaktiv welchen Folder |
| `roarboot-extract-bewerbungen` | Extrahiert strukturierte Bewerber-Daten aus Roarboot-Bewerbung-Folder |
| `roarboot-grant-application-docx` | Generates investor-ready Word DOCX of the AI Nation Grant application from the Roarboot Fragenkatalog markdown. Cover, TOC, sections, Q&A, status table. |
| `roarboot-grant-gap-finder` | Cross-references Investor-Grant Fragenkatalog mit allen 115 Roarboot-Projekten und schlaegt fuer jede unvollstaendige Frage Quellen + LLM-Vorschlaege vor. |
| `roarboot-grant-progress-tracker` | Parst Investor-Grant Fragenkatalog zu Excel mit Status-Color-Coding und Fortschritts-Summary |
| `roarboot-html-to-pdf` | Renders an HTML pitch deck as a landscape A4 PDF via Playwright print-to-pdf, one page per slide. |
| `roarboot-html-to-pptx` | Converts a scroll-snap HTML pitch deck (Skill B output) to PowerPoint by screenshotting each slide via headless Playwright at 1920x1080 and embedding as full-bleed images. |
| `roarboot-investor-pack` | Bundles Grant DOCX + Pitch HTML/PDF/PPTX into one investor-ready ZIP with SHA256 manifest and reproducibility instructions. |
| `roarboot-join-bewerbungen-people` | Joint Roarboot-Bewerbungen mit People-Profilen auf Name-Match und schreibt unified Excel |
| `roarboot-parametric-extract` | Parametrische Extraktion: User waehlt Folder + Felder via Telegram, Skill generiert massgeschneiderte Excel mit LLM-Extraktion |
| `roarboot-pitch-deck-html` | Generates a self-contained HTML pitch deck from real Roarboot Project + Grant data. 6 slides with theme, scroll-snap, no JS dependencies. |
| `roarboot-project-portfolio` | Excel-Portfolio-Dashboard aller Roarboot-Projekte (regex-parsed _overview.md, kein LLM noetig fuer Daten) |

## rowboat

_1 skills_

| Name | Description |
|---|---|
| `rowboat-export-bubble-notes` | Exportiert Notizen einer Rowboat-Bubble nach Excel |

## science

_136 skills_

| Name | Description |
|---|---|
| `science-adaptyv` | How to use the Adaptyv Bio Foundry API and Python SDK for protein experiment design, submission, and results retrieval. Use this skill whenever the user mentions Adaptyv, Foundry API, protein bindi... |
| `science-aeon` | This skill should be used for time series machine learning tasks including classification, regression, clustering, forecasting, anomaly detection, segmentation, and similarity search. Use when work... |
| `science-anndata` | Data structure for annotated matrices in single-cell analysis. Use when working with .h5ad files or integrating with the scverse ecosystem. This is the data format skill—for analysis workflows use ... |
| `science-arboreto` | Infer gene regulatory networks (GRNs) from gene expression data using scalable algorithms (GRNBoost2, GENIE3). Use when analyzing transcriptomics data (bulk RNA-seq, single-cell RNA-seq) to identif... |
| `science-astropy` | Comprehensive Python library for astronomy and astrophysics. This skill should be used when working with astronomical data including celestial coordinates, physical units, FITS files, cosmological ... |
| `science-autoskill` | Observe the user's screen via screenpipe, detect repeated research workflows, match them against existing scientific-agent-skills, and draft new skills (or composition recipes that chain existing o... |
| `science-benchling-integration` | Benchling R&D platform integration. Access registry (DNA, proteins), inventory, ELN entries, workflows via API, build Benchling Apps, query Data Warehouse, for lab data management automation. |
| `science-bgpt-paper-search` | Search scientific papers and retrieve structured experimental data extracted from full-text studies via the BGPT MCP server. Returns 25+ fields per paper including methods, results, sample sizes, q... |
| `science-biopython` | Comprehensive molecular biology toolkit. Use for sequence manipulation, file parsing (FASTA/GenBank/PDB), phylogenetics, and programmatic NCBI/PubMed access (Bio.Entrez). Best for batch processing,... |
| `science-bioservices` | Unified Python interface to 40+ bioinformatics services. Use when querying multiple databases (UniProt, KEGG, ChEMBL, Reactome) in a single workflow with consistent API. Best for cross-database ana... |
| `science-cellxgene-census` | Query the CELLxGENE Census (61M+ cells) programmatically. Use when you need expression data across tissues, diseases, or cell types from the largest curated single-cell atlas. Best for population-s... |
| `science-cirq` | Google quantum computing framework. Use when targeting Google Quantum AI hardware, designing noise-aware circuits, or running quantum characterization experiments. Best for Google hardware, noise m... |
| `science-citation-management` | Comprehensive citation management for academic research. Search Google Scholar and PubMed for papers, extract accurate metadata, validate citations, and generate properly formatted BibTeX entries. ... |
| `science-clinical-decision-support` | Generate professional clinical decision support (CDS) documents for pharmaceutical and clinical research settings, including patient cohort analyses (biomarker-stratified with outcomes) and treatme... |
| `science-clinical-reports` | Write comprehensive clinical reports including case reports (CARE guidelines), diagnostic reports (radiology/pathology/lab), clinical trial reports (ICH-E3, SAE, CSR), and patient documentation (SO... |
| `science-cobrapy` | Constraint-based metabolic modeling (COBRA). FBA, FVA, gene knockouts, flux sampling, SBML models, for systems biology and metabolic engineering analysis. |
| `science-consciousness-council` | Run a multi-perspective Mind Council deliberation on any question, decision, or creative challenge. Use this skill whenever the user wants diverse viewpoints, needs help making a tough decision, as... |
| `science-dask` | Distributed computing for larger-than-RAM pandas/NumPy workflows. Use when you need to scale existing pandas/NumPy code beyond memory or across clusters. Best for parallel file processing, distribu... |
| `science-database-lookup` | Search 78 public scientific, biomedical, materials science, and economic databases via REST APIs. Covers physics/astronomy (NASA, NIST, SDSS, SIMBAD), earth/environment (USGS, NOAA, EPA), chemistry... |
| `science-datamol` | Pythonic wrapper around RDKit with simplified interface and sensible defaults. Preferred for standard drug discovery including SMILES parsing, standardization, descriptors, fingerprints, clustering... |
| `science-deepchem` | Molecular ML with diverse featurizers and pre-built datasets. Use for property prediction (ADMET, toxicity) with traditional ML or GNNs when you want extensive featurization options and MoleculeNet... |
| `science-deeptools` | NGS analysis toolkit. BAM to bigWig conversion, QC (correlation, PCA, fingerprints), heatmaps/profiles (TSS, peaks), for ChIP-seq, RNA-seq, ATAC-seq visualization. |
| `science-depmap` | Query the Cancer Dependency Map (DepMap) for cancer cell line gene dependency scores (CRISPR Chronos), drug sensitivity data, and gene effect profiles. Use for identifying cancer-specific vulnerabi... |
| `science-dhdna-profiler` | Extract cognitive patterns and thinking fingerprints from any text. Use this skill when the user wants to analyze how someone thinks, understand cognitive style, profile writing or speech patterns,... |
| `science-diffdock` | Diffusion-based molecular docking. Predict protein-ligand binding poses from PDB/SMILES, confidence scores, virtual screening, for structure-based drug design. Not for affinity prediction. |
| `science-dnanexus-integration` | DNAnexus cloud genomics platform. Build apps/applets, manage data (upload/download), dxpy Python SDK, run workflows, FASTQ/BAM/VCF, for genomics pipeline development and execution. |
| `science-docx` | Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produ... |
| `science-esm` | Comprehensive toolkit for protein language models including ESM3 (generative multimodal protein design across sequence, structure, and function) and ESM C (efficient protein embeddings and represen... |
| `science-etetoolkit` | Phylogenetic tree toolkit (ETE). Tree manipulation (Newick/NHX), evolutionary event detection, orthology/paralogy, NCBI taxonomy, visualization (PDF/SVG), for phylogenomics. |
| `science-exa-search` | Web toolkit powered by Exa, tuned for scientific and technical content. Use this skill when the user needs to search the web or fetch/extract URL content. Covers: web search (semantic lookups, rese... |
| `science-exploratory-data-analysis` | Perform comprehensive exploratory data analysis on scientific data files across 200+ file formats. This skill should be used when analyzing any scientific data file to understand its structure, con... |
| `science-flowio` | Parse FCS (Flow Cytometry Standard) files v2.0-3.1. Extract events as NumPy arrays, read metadata/channels, convert to CSV/DataFrame, for flow cytometry data preprocessing. |
| `science-fluidsim` | Framework for computational fluid dynamics simulations using Python. Use when running fluid dynamics simulations including Navier-Stokes equations (2D/3D), shallow water equations, stratified flows... |
| `science-generate-image` | Generate or edit images using AI models (FLUX, Nano Banana 2). Use for general-purpose image generation including photos, illustrations, artwork, visual assets, concept art, and any image that is n... |
| `science-geniml` | This skill should be used when working with genomic interval data (BED files) for machine learning tasks. Use for training region embeddings (Region2Vec, BEDspace), single-cell ATAC-seq analysis (s... |
| `science-geomaster` | Comprehensive geospatial science skill covering remote sensing, GIS, spatial analysis, machine learning for earth observation, and 30+ scientific domains. Supports satellite imagery processing (Sen... |
| `science-geopandas` | Python library for working with geospatial vector data including shapefiles, GeoJSON, and GeoPackage files. Use when working with geographic data for spatial analysis, geometric operations, coordin... |
| `science-get-available-resources` | This skill should be used at the start of any computationally intensive scientific task to detect and report available system resources (CPU cores, GPUs, memory, disk space). It creates a JSON file... |
| `science-gget` | Fast CLI/Python queries to 20+ bioinformatics databases. Use for quick lookups: gene info, BLAST searches, AlphaFold structures, enrichment analysis. Best for interactive exploration, simple querie... |
| `science-ginkgo-cloud-lab` | Submit and manage protocols on Ginkgo Bioworks Cloud Lab (cloud.ginkgo.bio), a web-based interface for autonomous lab execution on Reconfigurable Automation Carts (RACs). Use when the user wants to... |
| `science-glycoengineering` | Analyze and engineer protein glycosylation. Scan sequences for N-glycosylation sequons (N-X-S/T), predict O-glycosylation hotspots, and access curated glycoengineering tools (NetOGlyc, GlycoShield,... |
| `science-gtars` | High-performance toolkit for genomic interval analysis in Rust with Python bindings. Use when working with genomic regions, BED files, coverage tracks, overlap detection, tokenization for ML models... |
| `science-histolab` | Lightweight WSI tile extraction and preprocessing. Use for basic slide processing tissue detection, tile extraction, stain normalization for H&E images. Best for simple pipelines, dataset preparati... |
| `science-hugging-science` | Use when the user is doing AI/ML work in a scientific domain — biology, chemistry, physics, astronomy, climate, genomics, materials science, medicine, ecology, energy, conservation, engineering, ma... |
| `science-hypogenic` | Automated LLM-driven hypothesis generation and testing on tabular datasets. Use when you want to systematically explore hypotheses about patterns in empirical data (e.g., deception detection, conte... |
| `science-hypothesis-generation` | Structured hypothesis formulation from observations. Use when you have experimental observations or data and need to formulate testable hypotheses with predictions, propose mechanisms, and design e... |
| `science-imaging-data-commons` | Query and download public cancer imaging data from NCI Imaging Data Commons using idc-index. Use for accessing large-scale radiology (CT, MR, PET) and pathology datasets for AI training or research... |
| `science-infographics` | Create professional infographics using Nano Banana Pro AI with smart iterative refinement. Uses Gemini 3 Pro for quality review. Integrates research-lookup and web search for accurate data. Support... |
| `science-iso-13485-certification` | Comprehensive toolkit for preparing ISO 13485 certification documentation for medical device Quality Management Systems. Use when users need help with ISO 13485 QMS documentation, including (1) con... |
| `science-labarchive-integration` | Electronic lab notebook API integration. Access notebooks, manage entries/attachments, backup notebooks, integrate with Protocols.io/Jupyter/REDCap, for programmatic ELN workflows. |
| `science-lamindb` | This skill should be used when working with LaminDB, an open-source data framework for biology that makes data queryable, traceable, reproducible, and FAIR. Use when managing biological datasets (s... |
| `science-latchbio-integration` | Latch platform for bioinformatics workflows. Build pipelines with Latch SDK, @workflow/@task decorators, deploy serverless workflows, LatchFile/LatchDir, Nextflow/Snakemake integration. |
| `science-latex-posters` | Create professional research posters in LaTeX using beamerposter, tikzposter, or baposter. Support for conference presentations, academic posters, and scientific communication. Includes layout desi... |
| `science-literature-review` | Conduct comprehensive, systematic literature reviews using multiple academic databases (PubMed, arXiv, bioRxiv, Semantic Scholar, etc.). This skill should be used when conducting systematic literat... |
| `science-markdown-mermaid-writing` | Comprehensive markdown and Mermaid diagram writing skill. Use when creating any scientific document, report, analysis, or visualization. Establishes text-based diagrams as the default documentation... |
| `science-market-research-reports` | Generate comprehensive market research reports (50+ pages) in the style of top consulting firms (McKinsey, BCG, Gartner). Features professional LaTeX formatting, extensive visual generation with sc... |
| `science-markitdown` | Convert files and office documents to Markdown. Supports PDF, DOCX, PPTX, XLSX, images (with OCR), audio (with transcription), HTML, CSV, JSON, XML, ZIP, YouTube URLs, EPubs and more. |
| `science-matchms` | Spectral similarity and compound identification for metabolomics. Use for comparing mass spectra, computing similarity scores (cosine, modified cosine), and identifying unknown compounds from spect... |
| `science-matlab` | MATLAB and GNU Octave numerical computing for matrix operations, data analysis, visualization, and scientific computing. Use when writing MATLAB/Octave scripts for linear algebra, signal processing... |
| `science-matplotlib` | Low-level plotting library for full customization. Use when you need fine-grained control over every plot element, creating novel plot types, or integrating with specific scientific workflows. Expo... |
| `science-medchem` | Medicinal chemistry filters. Apply drug-likeness rules (Lipinski, Veber), PAINS filters, structural alerts, complexity metrics, for compound prioritization and library filtering. |
| `science-modal` | Cloud computing platform for running Python on GPUs and serverless infrastructure. Use when deploying AI/ML models, running GPU-accelerated workloads, serving web endpoints, scheduling batch jobs, ... |
| `science-molecular-dynamics` | Run and analyze molecular dynamics simulations with OpenMM and MDAnalysis. Set up protein/small molecule systems, define force fields, run energy minimization and production MD, analyze trajectorie... |
| `science-molfeat` | Molecular featurization for ML (100+ featurizers). ECFP, MACCS, descriptors, pretrained models (ChemBERTa), convert SMILES to features, for QSAR and molecular ML. |
| `science-networkx` | Comprehensive toolkit for creating, analyzing, and visualizing complex networks and graphs in Python. Use when working with network/graph data structures, analyzing relationships between entities, ... |
| `science-neurokit2` | Comprehensive biosignal processing toolkit for analyzing physiological data including ECG, EEG, EDA, RSP, PPG, EMG, and EOG signals. Use this skill when processing cardiovascular signals, brain act... |
| `science-neuropixels-analysis` | Neuropixels neural recording analysis. Load SpikeGLX/OpenEphys data, preprocess, motion correction, Kilosort4 spike sorting, quality metrics, Allen/IBL curation, AI-assisted visual analysis, for Ne... |
| `science-omero-integration` | Microscopy data management platform. Access images via Python, retrieve datasets, analyze pixels, manage ROIs/annotations, batch processing, for high-content screening and microscopy workflows. |
| `science-open-notebook` | Self-hosted, open-source alternative to Google NotebookLM for AI-powered research and document analysis. Use when organizing research materials into notebooks, ingesting diverse content sources (PD... |
| `science-opentrons-integration` | Official Opentrons Protocol API for OT-2 and Flex robots. Use when writing protocols specifically for Opentrons hardware with full access to Protocol API v2 features. Best for production Opentrons ... |
| `science-optimize-for-gpu` | GPU-accelerate Python code using CuPy, Numba CUDA, Warp, cuDF, cuML, cuGraph, KvikIO, cuCIM, cuxfilter, cuVS, cuSpatial, and RAFT. Use whenever the user mentions GPU/CUDA/NVIDIA acceleration, or wa... |
| `science-paper-lookup` | Search 10 academic paper databases via REST APIs for research papers, preprints, and scholarly articles. Covers PubMed, PMC (full text), bioRxiv, medRxiv, arXiv, OpenAlex, Crossref, Semantic Schola... |
| `science-paperzilla` | Chat with your agent about projects, recommendations, and canonical papers in Paperzilla. Use when users ask for recent project recommendations, canonical paper details, markdown-based summaries, r... |
| `science-parallel-web` | All-in-one web toolkit powered by parallel-cli, with a strong emphasis on academic and scientific sources. Use this skill whenever the user needs to search the web, fetch/extract URL content, enric... |
| `science-pathml` | Full-featured computational pathology toolkit. Use for advanced WSI analysis including multiplexed immunofluorescence (CODEX, Vectra), nucleus segmentation, tissue graph construction, and ML model ... |
| `science-pdf` | Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, r... |
| `science-peer-review` | Structured manuscript/grant review with checklist-based evaluation. Use when writing formal peer reviews with specific criteria methodology assessment, statistical validity, reporting standards com... |
| `science-pennylane` | Hardware-agnostic quantum ML framework with automatic differentiation. Use when training quantum circuits via gradients, building hybrid quantum-classical models, or needing device portability acro... |
| `science-phylogenetics` | Build and analyze phylogenetic trees using MAFFT (multiple alignment), IQ-TREE 2 (maximum likelihood), and FastTree (fast NJ/ML). Visualize with ETE3 or FigTree. For evolutionary analysis, microbia... |
| `science-polars` | Fast in-memory DataFrame library for datasets that fit in RAM. Use when pandas is too slow but data still fits in memory. Lazy evaluation, parallel execution, Apache Arrow backend. Best for 1-100GB... |
| `science-polars-bio` | High-performance genomic interval operations and bioinformatics file I/O on Polars DataFrames. Overlap, nearest, merge, coverage, complement, subtract for BED/VCF/BAM/GFF intervals. Streaming, clou... |
| `science-pptx` | Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text fro... |
| `science-pptx-posters` | Create research posters using HTML/CSS that can be exported to PDF or PPTX. Use this skill ONLY when the user explicitly requests PowerPoint/PPTX poster format. For standard research posters, use l... |
| `science-primekg` | Query the Precision Medicine Knowledge Graph (PrimeKG) for multiscale biological data including genes, drugs, diseases, phenotypes, and more. |
| `science-protocolsio-integration` | Integration with protocols.io API for managing scientific protocols. This skill should be used when working with protocols.io to search, create, update, or publish protocols; manage protocol steps ... |
| `science-pufferlib` | High-performance reinforcement learning framework optimized for speed and scale. Use when you need fast parallel training, vectorized environments, multi-agent systems, or integration with game env... |
| `science-pydeseq2` | Differential gene expression analysis (Python DESeq2). Identify DE genes from bulk RNA-seq counts, Wald tests, FDR correction, volcano/MA plots, for RNA-seq analysis. |
| `science-pydicom` | Python library for working with DICOM (Digital Imaging and Communications in Medicine) files. Use this skill when reading, writing, or modifying medical imaging data in DICOM format, extracting pix... |
| `science-pyhealth` | Build clinical/healthcare deep-learning pipelines with PyHealth — loading EHR/signal/imaging datasets (MIMIC-III/IV, eICU, OMOP, SleepEDF, ChestXray14, EHRShot), defining tasks (mortality, readmiss... |
| `science-pylabrobot` | Vendor-agnostic lab automation framework. Use when controlling multiple equipment types (Hamilton, Tecan, Opentrons, plate readers, pumps) or needing unified programming across different vendors. B... |
| `science-pymatgen` | Materials science toolkit. Crystal structures (CIF, POSCAR), phase diagrams, band structure, DOS, Materials Project integration, format conversion, for computational materials science. |
| `science-pymc` | Bayesian modeling with PyMC. Build hierarchical models, MCMC (NUTS), variational inference, LOO/WAIC comparison, posterior checks, for probabilistic programming and inference. |
| `science-pymoo` | Multi-objective optimization framework. NSGA-II, NSGA-III, MOEA/D, Pareto fronts, constraint handling, benchmarks (ZDT, DTLZ), for engineering design and optimization problems. |
| `science-pyopenms` | Complete mass spectrometry analysis platform. Use for proteomics workflows feature detection, peptide identification, protein quantification, and complex LC-MS/MS pipelines. Supports extensive file... |
| `science-pysam` | Genomic file toolkit. Read/write SAM/BAM/CRAM alignments, VCF/BCF variants, FASTA/FASTQ sequences, extract regions, calculate coverage, for NGS data processing pipelines. |
| `science-pytdc` | Therapeutics Data Commons. AI-ready drug discovery datasets (ADME, toxicity, DTI), benchmarks, scaffold splits, molecular oracles, for therapeutic ML and pharmacological prediction. |
| `science-pytorch-lightning` | Deep learning framework (PyTorch Lightning). Organize PyTorch code into LightningModules, configure Trainers for multi-GPU/TPU, implement data pipelines, callbacks, logging (W&B, TensorBoard), dist... |
| `science-pyzotero` | Interact with Zotero reference management libraries using the pyzotero Python client. Retrieve, create, update, and delete items, collections, tags, and attachments via the Zotero Web API v3. Use t... |
| `science-qiskit` | IBM quantum computing framework. Use when targeting IBM Quantum hardware, working with Qiskit Runtime for production workloads, or needing IBM optimization tools. Best for IBM hardware execution, q... |
| `science-qutip` | Quantum physics simulation library for open quantum systems. Use when studying master equations, Lindblad dynamics, decoherence, quantum optics, or cavity QED. Best for physics research, open syste... |
| `science-rdkit` | Cheminformatics toolkit for fine-grained molecular control. SMILES/SDF parsing, descriptors (MW, LogP, TPSA), fingerprints, substructure search, 2D/3D generation, similarity, reactions. For standar... |
| `science-research-grants` | Write competitive research proposals for NSF, NIH, DOE, DARPA, and Taiwan NSTC. Agency-specific formatting, review criteria, budget preparation, broader impacts, significance statements, innovation... |
| `science-rowan` | Rowan is a cloud-native molecular modeling and medicinal-chemistry workflow platform with a Python API. Use for pKa and macropKa prediction, conformer and tautomer ensembles, docking and analogue d... |
| `science-scanpy` | Standard single-cell RNA-seq analysis pipeline. Use for QC, normalization, dimensionality reduction (PCA/UMAP/t-SNE), clustering, differential expression, and visualization. Best for exploratory sc... |
| `science-scholar-evaluation` | Systematically evaluate scholarly work using the ScholarEval framework, providing structured assessment across research quality dimensions including problem formulation, methodology, analysis, and ... |
| `science-scientific-brainstorming` | Creative research ideation and exploration. Use for open-ended brainstorming sessions, exploring interdisciplinary connections, challenging assumptions, or identifying research gaps. Best for early... |
| `science-scientific-critical-thinking` | Evaluate scientific claims and evidence quality. Use for assessing experimental design validity, identifying biases and confounders, applying evidence grading frameworks (GRADE, Cochrane Risk of Bi... |
| `science-scientific-schematics` | Create publication-quality scientific diagrams using Nano Banana 2 AI with smart iterative refinement. Uses Gemini 3.1 Pro Preview for quality review. Only regenerates if quality is below threshold... |
| `science-scientific-slides` | Build slide decks and presentations for research talks. Use this for making PowerPoint slides, conference presentations, seminar talks, research presentations, thesis defense slides, or any scienti... |
| `science-scientific-visualization` | Meta-skill for publication-ready figures. Use when creating journal submission figures requiring multi-panel layouts, significance annotations, error bars, colorblind-safe palettes, and specific jo... |
| `science-scientific-writing` | Core skill for the deep research and writing tool. Write scientific manuscripts in full paragraphs (never bullet points). Use two-stage process with (1) section outlines with key points using resea... |
| `science-scikit-bio` | Biological data toolkit. Sequence analysis, alignments, phylogenetic trees, diversity metrics (alpha/beta, UniFrac), ordination (PCoA), PERMANOVA, FASTA/Newick I/O, for microbiome analysis. |
| `science-scikit-learn` | Machine learning in Python with scikit-learn. Use when working with supervised learning (classification, regression), unsupervised learning (clustering, dimensionality reduction), model evaluation,... |
| `science-scikit-survival` | Comprehensive toolkit for survival analysis and time-to-event modeling in Python using scikit-survival. Use this skill when working with censored survival data, performing time-to-event analysis, f... |
| `science-scvelo` | RNA velocity analysis with scVelo. Estimate cell state transitions from unspliced/spliced mRNA dynamics, infer trajectory directions, compute latent time, and identify driver genes in single-cell R... |
| `science-scvi-tools` | Deep generative models for single-cell omics. Use when you need probabilistic batch correction (scVI), transfer learning, differential expression with uncertainty, or multi-modal integration (TOTAL... |
| `science-seaborn` | Statistical visualization with pandas integration. Use for quick exploration of distributions, relationships, and categorical comparisons with attractive defaults. Best for box plots, violin plots,... |
| `science-shap` | Model interpretability and explainability using SHAP (SHapley Additive exPlanations). Use this skill when explaining machine learning model predictions, computing feature importance, generating SHA... |
| `science-simpy` | Process-based discrete-event simulation framework in Python. Use this skill when building simulations of systems with processes, queues, resources, and time-based events such as manufacturing syste... |
| `science-stable-baselines3` | Production-ready reinforcement learning algorithms (PPO, SAC, DQN, TD3, DDPG, A2C) with scikit-learn-like API. Use for standard RL experiments, quick prototyping, and well-documented algorithm impl... |
| `science-statistical-analysis` | Guided statistical analysis with test selection and reporting. Use when you need help choosing appropriate tests for your data, assumption checking, power analysis, and APA-formatted results. Best ... |
| `science-statsmodels` | Statistical models library for Python. Use when you need specific model classes (OLS, GLM, mixed models, ARIMA) with detailed diagnostics, residuals, and inference. Best for econometrics, time seri... |
| `science-sympy` | Use this skill when working with symbolic mathematics in Python. This skill should be used for symbolic computation tasks including solving equations algebraically, performing calculus operations (... |
| `science-tiledbvcf` | Efficient storage and retrieval of genomic variant data using TileDB. Scalable VCF/BCF ingestion, incremental sample addition, compressed storage, parallel queries, and export capabilities for popu... |
| `science-timesfm-forecasting` | Zero-shot time series forecasting with Google's TimesFM foundation model. Use for any univariate time series (sales, sensors, energy, vitals, weather) without training a custom model. Supports CSV/... |
| `science-torch-geometric` | Guide for building Graph Neural Networks with PyTorch Geometric (PyG). Use this skill whenever the user asks about graph neural networks, GNNs, node classification, link prediction, graph classific... |
| `science-torchdrug` | PyTorch-native graph neural networks for molecules and proteins. Use when building custom GNN architectures for drug discovery, protein modeling, or knowledge graph reasoning. Best for custom model... |
| `science-transformers` | This skill should be used when working with pre-trained transformer models for natural language processing, computer vision, audio, or multimodal tasks. Use for text generation, classification, que... |
| `science-treatment-plans` | Generate concise (3-4 page), focused medical treatment plans in LaTeX/PDF format for all clinical specialties. Supports general medical treatment, rehabilitation therapy, mental health care, chroni... |
| `science-umap-learn` | UMAP dimensionality reduction. Fast nonlinear manifold learning for 2D/3D visualization, clustering preprocessing (HDBSCAN), supervised/parametric UMAP, for high-dimensional data. |
| `science-usfiscaldata` | Query the U.S. Treasury Fiscal Data API for federal financial data including national debt, government spending, revenue, interest rates, exchange rates, and savings bonds. Access 54 datasets and 1... |
| `science-vaex` | Use this skill for processing and analyzing large tabular datasets (billions of rows) that exceed available RAM. Vaex excels at out-of-core DataFrame operations, lazy evaluation, fast aggregations,... |
| `science-venue-templates` | Access comprehensive LaTeX templates, formatting requirements, and submission guidelines for major scientific publication venues (Nature, Science, PLOS, IEEE, ACM), academic conferences (NeurIPS, I... |
| `science-what-if-oracle` | Run structured What-If scenario analysis with multi-branch possibility exploration. Use this skill when the user asks speculative questions like "what if...", "what would happen if...", "what are t... |
| `science-xlsx` | Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., ... |
| `science-zarr-python` | Chunked N-D arrays for cloud storage. Compressed arrays, parallel I/O, S3/GCS integration, NumPy/Dask/Xarray compatible, for large-scale scientific computing pipelines. |

## security

_1 skills_

| Name | Description |
|---|---|
| `security-ffuf-web-fuzzing` | Expert guidance for ffuf web fuzzing during penetration testing, including authenticated fuzzing with raw requests, auto-calibration, and result analysis |

## tapestry

_7 skills_

| Name | Description |
|---|---|
| `tapestry-article-extractor` | Extract clean article content from URLs (blog posts, articles, tutorials) and save as readable text. Use when user wants to download, extract, or save an article/blog post from a URL without ads, n... |
| `tapestry-learn-this` | Unified content extraction and action planning. Use when user says "learn-this <URL>", "learn this <URL>", "weave <URL>", "help me plan <URL>", "extract and plan <URL>", "make this actionable <URL>... |
| `tapestry-scrum-sage` | AI-powered Scrum Master and Enterprise Agility Coach based on Jeff Sutherland, Taiichi Ohno, and First Principles thinking. Use when user needs help with Scrum, sprint analysis, backlog refinement,... |
| `tapestry-session-log` | Summarize the current conversation session and append results to the weekly agent-log. Use when user says "log this", "session log", "summarize this session", or asks to write results to the agent-... |
| `tapestry-ship-learn-next` | Transform learning content (like YouTube transcripts, articles, tutorials) into actionable implementation plans using the Ship-Learn-Next framework. Use when user wants to turn advice, lessons, or ... |
| `tapestry-unblock-action` | Help the user unblock a vague or stuck action item by clarifying the intended output, scoping it to today, and identifying the concrete next action. Use when user says "unblock", "unstick", "I'm st... |
| `tapestry-youtube-transcript` | Download YouTube video transcripts when user provides a YouTube URL or asks to download/get/fetch a transcript from YouTube. Also use when user wants to transcribe or get captions/subtitles from a ... |

## utility

_4 skills_

| Name | Description |
|---|---|
| `utility-markdown-to-epub-converter` | Convert markdown documents and chat summaries into formatted EPUB ebook files that can be read on any device or uploaded to Kindle. |
| `utility-plaid` | Plaid banking API expert for financial data integration. Covers Plaid Link, Auth (account/routing numbers), Transactions, Identity verification, Balance checking, and webhooks. Build fintech apps w... |
| `utility-terminal-title` | Automatically updates terminal window title to reflect the current high-level task. Use at the start of every Claude Code session when the user provides their first prompt, and whenever the user sw... |
| `utility-toon-formatter` | Token-Oriented Object Notation (TOON) format expert for 30-60% token savings on structured data. Auto-applies to arrays with 5+ items, tables, logs, API responses, database results. Supports tabula... |

## vscode

_3 skills_

| Name | Description |
|---|---|
| `vscode-command-palette` | Oeffne die VS Code Command Palette und fuehre einen Befehl aus. |
| `vscode-quick-open` | Oeffne eine Datei in VS Code via Quick-Open (Strg+P). |
| `vscode-toggle-terminal` | Oeffne oder schliesse das Terminal-Panel in VS Code (Strg+`). |

## word

_4 skills_

| Name | Description |
|---|---|
| `word-find-replace` | Suchen-und-Ersetzen in Word (Strg+H), ersetzt alle Vorkommen eines Strings durch einen anderen. |
| `word-new-document` | Erstelle ein leeres neues Word-Dokument (Strg+N) und optional tippe einen Anfangstext. |
| `word-save-as` | Speichere das aktive Word-Dokument unter einem neuen Pfad (F12). |
| `word-write-text` | Schreibe einen Text in ein Word-Dokument. |

---

Regenerate with `python scripts/generate_skill_catalog.py`.