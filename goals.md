Short Term — Immediate Pipeline Fix (do now, in order)
preprocess_video.py — Re-extract clean keyframes from 100 existing videos (37 frames max, content filter on)
analyzer.py — Re-run math on all 100 hero screenshots (whitespace, asymmetry, color variance — the full data now)
enrich.py — Run minicpm-v on the clean keyframes per site → regenerate taste_rationale.md
embed_rationale.py — Re-embed the new rationales with nomic-embed-text → regenerate embedding.json
extract_taste.py — Run Gemma 4 on the unified Winners vs Losers table → produce taste_extraction_report.md (the "Rules of Taste")
Mid Term — Pipeline Improvements
Wire vision_llm.py into extract_taste.py — Pull the minicpm-v descriptions into the Markdown table so Gemma 4 gets both hard numbers AND qualitative design language per site
Scale to 400–900 sites — Currently at 100 sites. Re-scraper needs to run with the fixed scroll settings (250px, 90s duration) on the full URL list
Fix enrich.py to use keyframes instead of just the hero — Currently enrich.py passes the hero screenshot to minicpm-v. Needs updating to loop across the 37 keyframes for the scroll-story analysis
Update config.py REASONING_MODEL references across all scripts — Some scripts may still be calling deepseek-r1:8b directly rather than reading from config
