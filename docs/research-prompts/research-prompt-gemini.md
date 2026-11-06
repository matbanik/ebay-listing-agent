# Deep Research Prompt — Gemini 3.1 Pro

> Copy-paste this into Gemini Deep Research. Gemini excels at multi-source synthesis and visual/technical analysis.

---

I'm building an agentic AI pipeline that takes product photos (downloaded from Google Photos), identifies the products, discovers fair market pricing, and creates eBay listings — with human approval before going live.

The pipeline uses 3 AI agent roles: **Curator** (image analysis → product ID), **Evaluator** (validation + pricing), **Lister** (eBay listing via API).

I need deep research on ALL of the following areas. For each, find current best practices, real examples, tool recommendations, and any gotchas:

## 1. Image Processing Pipeline for eBay Sellers
- What are eBay's exact current image requirements (2025-2026)? Dimensions, file size, format, count per listing.
- What's the optimal image processing pipeline? Resize, compress, background removal, auto-orient, metadata stripping.
- Best Python libraries for batch image processing (Pillow, OpenCV, rembg, etc.) — which for what task?
- How to handle Google Photos exports (HEIC from iPhone, metadata JSON from Takeout, date preservation).
- What makes a great eBay product photo? Composition, lighting, angles, number of photos per listing for different categories.

## 2. AI Vision for Product Identification
- What are the best approaches for AI-based product identification from photos? (GPT-4o vision, Gemini vision, Claude vision, Google Lens API, etc.)
- How accurate is AI vision at identifying brand, model, and condition of used consumer products?
- What prompt engineering techniques work best for product identification from images?
- How should condition grading work? What are eBay's exact condition codes and when to use each?
- Any open-source or API-based product recognition tools specifically for consumer goods / eBay?

## 3. eBay Price Discovery & Completed Listings
- How to access eBay's completed/sold item data programmatically? Which APIs work in 2025-2026?
- What is the `ebay-mcp` npm package (github.com/YosefHayim/ebay-mcp) — what tools does it provide for pricing?
- Best methodology for pricing used items from sold comps (median, percentile ranges, condition adjustments)?
- Third-party pricing APIs or scrapers (Apify, Terapeak, WatchCount, etc.) — pros/cons of each?
- How do successful eBay resellers determine their listing price?

## 4. eBay Listing Creation via API
- What's the current eBay listing creation flow via the Sell API? (Inventory API → Offer → Publish)
- What are the most important item specifics that eBay's algorithm rewards in search rankings?
- How to write SEO-optimized eBay titles (80 char limit) and descriptions?
- Category selection best practices — how to find the most specific category?
- Listing policies: what fulfillment, payment, and return policies work best for individual sellers?

## 5. Agentic AI Workflow Architecture
- What patterns exist for multi-agent pipelines (sequential handoff, evaluator-optimizer, orchestrator)?
- How should agent roles be defined in AGENTS.md files for coding assistants?
- What is the `.agent/` folder convention? How should workflows, docs, skills, and context be organized?
- How do teams structure slash-command workflows for AI coding assistants?
- What are best practices for human-in-the-loop checkpoints in agentic workflows?

## 6. Skills Architecture for AI Agents
- What is a "skill" in the context of AI coding agents? How is it different from a workflow or a tool?
- How should SKILL.md files be structured (frontmatter, instructions, scripts, resources)?
- Examples of well-designed skill folders for multi-step agentic tasks?
- How to make skills reusable across different AI models (Gemini, Claude, ChatGPT)?

Please provide concrete examples, real tool names with versions, actual API endpoints where relevant, and link to sources. Prioritize information from 2025-2026.
