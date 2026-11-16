# CodeAtlas: Product Vision and Experience

## Product promise

Give a developer reliable security findings for the repository they submit. Scan quality is the first priority. Report real vulnerabilities with as few false alarms and missed issues as possible.

Present the scan results in a polished, visually compelling interactive graph. Developers can explore how the code works, see where findings occur, and follow the evidence to the relevant source.

## From a repository link to a running scan

The primary journey should be straightforward:

1. Paste a GitHub repository URL and confirm the repository and revision to analyze.
2. Select an available model and review the scan configuration.
3. Choose relevant options, including the number of reviewing agents and the agreement threshold. Provide sensible defaults; keep less common settings under advanced options.
4. Click **Run scan**.
5. Follow understandable progress, then open the resulting graph and findings.

The user should not need to assemble commands or understand internal processing stages to complete this journey. Repository access problems, unavailable models, and invalid configuration should be explained before a scan starts whenever possible. Any required setup, source-sharing implications, and available cost or usage information should be clear at the point of choice.

During a scan, show what is happening and whether work is still progressing. Completion, partial completion, and failure must be distinguishable. If something fails, preserve any usable results, explain the gap, and offer a clear next action. Avoid making the user start over without understanding why.

## A graph that appears immediately

Opening a completed scan should immediately reveal a meaningful graph with visible, readable nodes and connections. A user should not have to navigate through a gallery of file or symbol cards before seeing it.

The graph should occupy most of the workspace. Keep the surrounding interface restrained: a compact project selector, essential graph controls, and access to files and findings. Large metric strips, repeated explanations, and permanently open side panels should not compete with the code map.

When the repository is too large to show legibly at once, start with a useful view and clearly identify its scope. Let the user move between repository context, files, and symbols without losing their place. A focused view must not silently imply that it represents the entire repository.

Give users control over how much detail the graph shows. At low detail, show where requests and data enter, which areas of business logic they pass through, and where data is read or written. As users increase the detail, reveal individual entry points, methods, calls, and data operations while keeping the flow they're following in view.

Use the [per-route code graph schema](code-graph-schema.md) to let users trace an HTTP request through its handler, authentication and authorization checks, and calls that read or write data. Link each step to its source and show where the scan left part of the path unresolved.

## Explore the code visually

The experience should support:

- Panning, zooming, and fitting the graph to the available space.
- Finding a file or symbol and navigating directly to its context.
- Selecting a node to see its role, file, source range, declaration, and available documentation.
- Following actual connections to callers, callees, data operations, and related source.
- Switching between code-flow and AST perspectives, with a clear distinction between execution-related relationships and syntax structure.
- Returning from a focused investigation to the broader graph without starting again.

Use concise labels, clear direction, and consistent visual treatment for entry points, logic, data access, and structural connections. Full names and source details should remain accessible when labels are shortened. Dense graphs need progressive exploration, not unreadably small text or unexplained omissions.

Details should appear on demand. Prefer one contextual panel at a time, with a clear close action that restores the unobstructed graph. Deeper explanations and secondary metadata can expand inside that panel.

## Investigate vulnerabilities through both a graph and a list

The findings list and the graph should be two connected ways to explore the same analysis.

Mark findings on the code graph so users can spot affected flows while exploring the repository. The list should make it easy to search, filter, and prioritize issues by severity, review status, and location. Selecting a finding should reveal its explanation and highlight the relevant nodes and path on the graph. Selecting a graph node should expose related findings when they exist.

A finding should make the following understandable:

- What the suspected vulnerability is and why it matters.
- Which entry point, functions, and sensitive operations are involved.
- The source locations and evidence supporting the claim.
- The potential impact and conditions required for exploitation.
- The reviewing agents' agreement, disagreement, or incomplete work.
- What the reviewer should investigate or change next.

Potential exploit paths should stand out visually, while unrelated code becomes less prominent. Users should be able to step through the path and inspect the source at each point. Missing connections must remain visible as gaps; highlighting a path must not imply that an exploit has been executed or proven.

Candidates and findings that meet the configured agreement threshold need distinct labels. The graph should make evidence easier to inspect, rather than turn uncertain claims into visually convincing conclusions.

## A product people want to use

The visual goal is a confident, memorable interface with strong typography, deliberate spacing, clear hierarchy, and smooth interaction. Animation and emphasis should help users follow connections, understand selection, and maintain context.

Visual quality must support usability: readable contrast, accessible controls, keyboard navigation, and a layout that works on smaller screens. A quiet workspace is preferable to a wall of cards, counters, and controls. The user should always be able to answer: which repository am I viewing, what part of it is shown, and what can I do next?

Saved scans should be easy to discover and reopen. Show repository identity, revision, and scan status clearly. Links should open the intended report; an unavailable report should explain the problem rather than silently substitute a demo. Remember useful selection context and provide a way to export or share results.

## Observable product goals

The experience is successful when a user can:

- Start a scan from a GitHub link, model choice, and configuration through a clear click-to-run flow.
- Open the result and see a meaningful graph immediately.
- Follow a flow from the repository overview down to individual methods, calls, and source locations.
- Select a file or node and understand its connections and source context.
- Move from a finding in the list to its highlighted path and inspect the supporting code.
- Recognize incomplete coverage, unresolved relationships, and uncertain findings.
- Close details, switch projects, and reopen a saved result without losing orientation.

These are product goals, not a claim that every capability is already implemented. Specific screen designs, technical architecture, supported integrations, and implementation choices will be defined separately. The project's analytical purpose is described in [Project Purpose](project-purpose.md).
