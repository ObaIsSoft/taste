# Taste Engine Alpha - Positional Bias Evaluation

**Test Configuration:** 50 distinct matchups evaluated forward (A vs B) and reversed (B vs A) for a total of 100 queries.

## Results
- **Total Queries:** 100
- **Accuracy:** 51/100 = 0.51
- **P(pick A):** 11/100 = 0.11
- **P(pick B):** 89/100 = 0.89
- **Content Stability:** 7/50 = 0.14

## Conclusion
If Content Stability is low and P(pick B) is extremely high, the model is suffering from severe positional bias (it favors the letter B rather than the design metrics). This mathematically confirms the necessity of transitioning from SFT to Margin-Adaptive DPO (MADPO) with balanced tuple placements and true contrastive preference gradients.
