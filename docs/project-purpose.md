# CodeAtlas: Project Purpose

> An AI-powered security scanner that maps code flows into graphs and uses independent agents to uncover vulnerabilities, trace attack paths, and cross-check findings.

The primary goal is scan quality. Aim for high precision by minimizing false positives and high recall by catching as many real vulnerabilities in the scanned code as possible. The interactive graph helps developers understand and investigate those results.

## Why CodeAtlas exists

A security issue often spans several parts of a repository. An entry point accepts input, application logic processes it, and another function reads data, writes to storage, or performs a sensitive operation. Looking at those pieces separately can hide the conditions that make a vulnerability possible.

CodeAtlas aims to make those connections understandable and useful for security analysis. It should help developers and security reviewers answer three questions:

- How is this repository organized, and how does information move through it?
- Where could a security weakness occur, and what code path makes it possible?
- What evidence supports the finding, and what still needs investigation?

## What the project should do

### Analyze repositories statically

CodeAtlas examines repository source without running the target application. A user should be able to provide a repository and receive an analysis grounded in a clearly identified version of its code.

The analysis should connect findings to actual files, symbols, and source locations. It should make supported, unsupported, and partially analyzed areas visible so that an incomplete scan cannot be mistaken for a clean result.

### Map code structure and flows

Graphs and code mappings are central to the project. They should represent meaningful relationships between entry points, functions, modules, data access, and other security-relevant operations.

Two complementary perspectives matter:

- **Code structure:** how files, declarations, and syntax relate to one another, including an abstract syntax tree (AST) view.
- **Code flow:** how entry points connect to application logic and sensitive operations, including database reads and writes.

These perspectives should help explain the repository and support security investigation. Structural relationships must remain distinguishable from calls or data flows. A connection that cannot be established should be treated as a gap, rather than invented to complete a diagram.

### Find vulnerabilities with independent AI review

AI agents should use the mapped relationships together with source evidence to discover potential vulnerabilities and investigate their surrounding context. The objective is to find meaningful weaknesses across the repository, including issues that involve multiple functions or files.

Findings should be cross-checked through independent agent agreement. The intended default is agreement from at least two agents, with a configurable threshold. Reports should distinguish preliminary candidates from findings that satisfy the configured agreement requirement.

Agreement increases confidence; it does not establish that exploitation is possible in every deployment. Missing paths, assumptions, disagreement, and incomplete reviews should remain explicit.

### Produce findings people can investigate

A useful result explains the issue, its potential impact, the relevant source locations, and the path that may enable it. It should identify supporting evidence and material prerequisites, such as required access or a particular configuration.

Where a path is unresolved, CodeAtlas should say so. Recommendations should help a reviewer understand what to inspect or change, without presenting speculation as established behavior.

## What success looks like

A developer can scan a repository, understand its important relationships, and investigate a reported vulnerability from entry point to sensitive operation without reconstructing the entire context manually. The result is traceable to source, clear about uncertainty, and useful for deciding what to fix or review next.

## Scope of this document

This document defines the project's purpose and intended outcomes. It does not choose languages to support, parsing tools, graph representations, agent orchestration, storage, APIs, frameworks, or deployment arrangements. Architecture and implementation decisions will be documented separately in a later session.

CodeAtlas is a static analysis and investigation tool. Visualizing a potential exploit path does not mean executing an exploit, testing a live system, or guaranteeing that every vulnerability has been found.

For the intended user experience, see [Product Vision and Experience](product-experience.md).
