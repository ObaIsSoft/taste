## Short Term — Immediate Pipeline Fix (do now, in order)
- [x] `preprocess_video.py` — Re-extract clean keyframes from 100 existing videos (37 frames max, content filter on)
- [x] `analyzer.py` — Re-run math on all 100 hero screenshots (whitespace, asymmetry, color variance — the full data now)
- [x] `enrich.py` — Run minicpm-v on the clean keyframes per site → regenerate taste_rationale.md
- [x] `embed_rationale.py` — Re-embed the new rationales with nomic-embed-text → regenerate embedding.json
- [x] `extract_taste.py` — Run Gemma 4 on the unified Winners vs Losers table → produce taste_extraction_report.md (the "Rules of Taste")

## Mid Term — Pipeline Improvements
- [x] Wire `vision_llm.py` into `extract_taste.py` — (Deprecated `vision_llm.py`, piped VLM directly via `enrich.py`)
- [x] Fix `enrich.py` to use keyframes instead of just the hero — (Updated to sample 4 downscaled sequence frames for VRAM safety)
- [x] Update `config.py` REASONING_MODEL references across all scripts — (Completed in recent git refactor)
- [ ] Scale to 400–900 sites — Re-scraper needs to run with the fixed scroll settings (250px, 90s duration) on the full URL list

## Long Term — The Generative UI Steering Loop
- [ ] Build `bridge.py` — Create the Model Context Protocol (MCP) interface that allows Coding Agents (Claude, Cursor) to submit raw HTML to the Taste Engine for critique.
- [ ] Implement Autonomous Revision — Wire the `taste-critic` verdict back into the generative agent to force CSS refactoring until "elite aesthetic execution" is achieved.
- [ ] Transition from SFT to DPO — Upgrade the training pipeline from Supervised Fine-Tuning (SFT) to true Direct Preference Optimization (DPO) so the model learns the contrastive difference between Generic and Elite design.
