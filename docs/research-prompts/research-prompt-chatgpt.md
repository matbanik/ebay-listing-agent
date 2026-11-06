# Deep Research Prompt — ChatGPT 5.4

> Copy-paste this into ChatGPT with Deep Research / browsing enabled. ChatGPT excels at structured analysis, code examples, and API documentation.

---

I'm building an agentic AI pipeline for eBay listing automation. The flow is:

**Google Photos → Image Processing → AI Product ID → Price Discovery → eBay Listing Draft → Human Approval**

Three agent roles: Curator (vision-based product identification), Evaluator (validation + pricing from sold comps), Lister (eBay API listing creation via MCP server).

I need deep research on these topics. For each, find working examples, current API details, code snippets, and real-world implementations:

## 1. eBay Sell API — Listing Creation Flow (2025-2026)
Research the current eBay Sell API workflow:
- Inventory API: `createOrReplaceInventoryItem` — exact request structure, required fields, image hosting
- Offer API: `createOffer`, `publishOffer` — how draft → live works
- Category Tree API: `getCategorySuggestions`, `getItemAspectsForCategory` — finding the right category
- What item specifics are REQUIRED vs optional per category? How does this affect search ranking?
- The `ebay-mcp` npm package (github.com/YosefHayim/ebay-mcp) — what MCP tools does it expose for listing creation?
- eBay OAuth 2.0 flow for user tokens — step by step for individual sellers
- Sandbox vs Production — key differences for testing

## 2. eBay Sold/Completed Items for Price Discovery
- Which eBay API endpoint returns completed/sold items with final sale prices?
- Is the Finding API `findCompletedItems` still available? What replaced it?
- Browse API `search` with completed items filter — does this work?
- Third-party alternatives: Apify eBay Sold Listings API, Terapeak, RapidAPI options
- Show me a working example (Python or JavaScript) of fetching sold prices for a specific product
- How to calculate fair market value from sold comps (statistical methodology)

## 3. Image Processing for eBay — Technical Pipeline
- eBay's current image size/format requirements (exact specs, 2025-2026)
- Python script for batch processing: resize to 1600px, JPEG Q92, EXIF auto-orient, metadata strip
- Handling iPhone HEIC images (pillow-heif vs other solutions)
- Background removal options: rembg, remove.bg API, Pillow-based approaches
- Google Photos export handling: Takeout JSON metadata, date preservation
- Image quality assessment — how to detect and reject blurry/dark photos programmatically

## 4. AI Vision Product Identification — Prompt Engineering
- Best prompts for GPT-4o / Gemini / Claude vision to identify brand, model, condition from product photos
- How to structure a multi-image analysis prompt (e.g., "here are 5 photos of the same item")
- Condition grading prompts — what works for assessing wear, scratches, completeness
- How accurate are current vision models at product ID? Any benchmarks or real-world reports?
- Handling ambiguous products — when the AI isn't sure, what's the best fallback strategy?

## 5. AGENTS.md & Skill Architecture for AI Coding Assistants
- The AGENTS.md convention — what sections should it contain for a project like this?
- Skills vs Workflows vs Tools — how are these concepts different in AI agent architectures?
- SKILL.md format — frontmatter structure, instruction format, resource organization
- The `.agent/` folder convention — docs, workflows, skills, context — how should these be organized?
- Examples of real AGENTS.md files from open-source projects that use multi-agent patterns
- How to write slash-command workflows that work across Gemini, Claude, and ChatGPT-based assistants

## 6. Multi-Agent Pipeline Patterns
- Sequential handoff pattern (Agent A output → Agent B input) — best practices for structured data passing
- Evaluator-optimizer pattern — how an evaluator agent validates and refines another agent's output
- Human-in-the-loop checkpoints — where to pause for approval in listing pipelines
- Report templates — what format works best for inter-agent communication (markdown, JSON, structured)?
- Error handling — what happens when the curator can't identify a product? When price discovery fails?

For each section, please provide: (1) current best practices with sources, (2) working code examples where applicable, (3) specific tool/API recommendations with versions, (4) common pitfalls to avoid.
