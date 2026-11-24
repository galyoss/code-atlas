# CodeAtlas

Scan quality comes first. Aim for high precision and recall. Use the interactive graph to explore the code and investigate findings.

Shahaf Cohen and Gal Yossipov both work across the whole project:

- The analysis core: repository parsing, graph design and construction, and the architecture of the agents that scan code and identify vulnerabilities. Measure changes here with the IDOR benchmark in `benchmarks/idor` when it applies.
- The product experience: submitting a repository for scanning, exploring its code flows at adjustable levels of detail, and investigating vulnerabilities on the graph. Keep product work aligned with [Product Vision and Experience](docs/product-experience.md).
