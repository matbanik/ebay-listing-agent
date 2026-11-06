# Deep Research Prompt — Claude Opus 4.6

> Copy-paste this into Claude with Extended Thinking / Research enabled. Claude excels at architectural reasoning, workflow design, and careful analysis of tradeoffs.

---

I'm designing a multi-agent AI system for automating eBay listings. I need you to research and reason deeply about the architecture, agent design, and workflow structure.

## Context

**Pipeline**: Raw product photos (from Google Photos) → image processing → AI-based product identification → price discovery from eBay sold data → listing creation via eBay MCP server → human review → go live.

**Three agent roles**:
- **Curator**: Analyzes product images with AI vision, identifies brand/model/condition, organizes files
- **Evaluator**: Validates identification, finds official specs, performs price discovery from eBay sold comps
- **Lister**: Creates eBay listing draft via the `ebay-mcp` npm package (325 eBay API tools), notifies human

**Tech stack**: Windows, Node.js (ebay-mcp), Python (image processing), AI coding assistant (Antigravity/Gemini), MCP servers for tool integration.

## Research Areas

### 1. Agent Architecture & Role Design
Research how to properly design agent roles for this pipeline:
- What information should pass between Curator → Evaluator → Lister? What's the optimal inter-agent data format?
- How should each agent's scope be bounded? What decisions should each agent make vs. defer?
- Where should human-in-the-loop checkpoints be placed? Only before publishing, or also between agents?
- For error handling: what happens when identification is uncertain? When no sold comps exist? When the API fails?
- How do production multi-agent systems handle agent disagreement (e.g., curator says "Like New" but evaluator's research suggests "Good")?

### 2. AGENTS.md Design & `.agent/` Folder Structure
Research the emerging conventions for AI agent configuration in code repos:
- What is the AGENTS.md standard? What sections are essential vs. optional?
- How should the `.agent/` folder be organized? What goes in `docs/`, `workflows/`, `skills/`, `context/`?
- What is a "skill" (SKILL.md) vs a "workflow" — when to use each?
- How should skills be structured so they work across different AI models (Gemini, Claude, ChatGPT)?
- What naming conventions and numbering schemes work for sequential workflows?
- Find examples of well-structured AGENTS.md files from real open-source projects.

### 3. eBay Image Requirements & Processing Best Practices
Research the current state of eBay image optimization:
- Exact current dimension, format, file size, and count requirements (2025-2026 rules)
- What image processing pipeline produces the best eBay listing photos from phone camera shots?
- Background removal: when is it worth doing? What tools work best (rembg, remove.bg)?
- Google Photos export quirks: HEIC handling, Takeout JSON metadata, batch processing
- How many photos per listing for different product categories? What angles/compositions convert best?

### 4. AI Vision for Used Product Identification & Condition Grading
Research the current capabilities and limitations:
- How reliable are current AI vision models (GPT-4o, Gemini 2.0 Flash, Claude Sonnet 4) for identifying consumer products from photos?
- What's the best prompt structure for product identification? For condition grading?
- eBay's condition codes — what are the exact definitions and when should each be used?
- How to handle edge cases: generic/unbranded items, bundles, items with no visible branding, damaged items
- Should condition assessment be conservative or optimistic? What's the eBay seller best practice?

### 5. Price Discovery Methodology
Research how to reliably determine fair market value:
- Which eBay APIs or endpoints give access to completed/sold item data in 2025-2026?
- What statistical method works best for pricing from sold comps? (Median, trimmed mean, percentile ranges)
- How to adjust for condition differences between comps and the item being listed?
- What to do when fewer than 5 sold comps exist? Broaden search or use alternative data?
- How do professional eBay resellers (flippers) determine their listing prices?

### 6. eBay Listing Creation via MCP
Research the `ebay-mcp` server (github.com/YosefHayim/ebay-mcp) and eBay Sell API:
- What's the current inventory → offer → publish flow for creating listings?
- How to write eBay titles that rank well in search? What are the exact character limits and SEO patterns?
- What item specifics matter most for search visibility?
- How to handle listing policies (shipping, returns, payment) for individual sellers?
- Sandbox testing approach — how to verify the pipeline works before going to production?

## Output Format

For each area, provide:
1. **Key findings** — what I should know
2. **Recommended approach** — what I should implement
3. **Tradeoffs** — alternatives considered and why the recommendation wins
4. **Risks & mitigations** — what could go wrong and how to handle it
5. **Sources** — where you found this information
