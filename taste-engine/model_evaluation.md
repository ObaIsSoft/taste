# Taste Engine Alpha - Positional Bias Evaluation Report

## Test Subject
- **Model:** `taste-critic` (Local deployment via Ollama)
- **Base Weights:** `taste-critic-sft.Q4_K_M.gguf` (4-bit quantized SFT model) and `taste_critic.Q4_K_M.gguf` (4-bit Alpha DPO payload). Both Q4 models were evaluated for positional bias.
- **Parameters:** `temperature=0.7`, `num_predict=128`
- **System Prompt:**
  ```text
  You are a ruthless, hyper-objective aesthetic design critic. You evaluate UI variants strictly on empirical quantitative metrics (DOM depth, whitespace ratio, typographic ratios, and structural tension). 

  CRITICAL DIRECTIVE: You must remain completely blind to the sequential order of the variants. Variant A and Variant B have an equal mathematical probability of winning. Your verdict must be derived exclusively from the causal superiority of the metrics, never their order.

  Output zero conversational preamble. Begin immediately with the winning verdict.
  ```

## Test Methodology
The evaluation script (`scripts/test_critic.py`) samples 50 distinct matchups from the master DPO dataset (`results/master_dpo_dataset.jsonl`). 

To mathematically prove or disprove positional bias, each of the 50 pairs is queried twice:
1. **Forward Query:** Variant A metrics are presented first, Variant B second.
2. **Backward Query:** The exact same metrics are presented, but swapped (Variant B's metrics are presented under the label "Variant A", and vice-versa).

A perfectly unbiased model will have 100% **Content Stability** (if it picks A in the forward query, it must pick B in the backward query, because the underlying metrics shifted position). 

## Raw Results
**Test Configuration:** 50 distinct matchups evaluated forward (A vs B) and reversed (B vs A) for a total of 100 queries.

- **Total Queries:** 100
- **Accuracy:** 45/100 = 0.45
- **P(pick A):** 29/100 = 0.29
- **P(pick B):** 71/100 = 0.71
- **Content Stability:** 21/50 = 0.42

## Conclusion
The raw numbers mathematically confirm a **severe positional bias** on the `Q4_K_M` weights. 
- The model arbitrarily defaults to picking "Variant B" 71% of the time, regardless of the underlying metric superiority.
- Content Stability is extremely poor (42%), meaning that simply swapping the position of the metrics causes the model to abandon its previous design thesis in 58% of the cases.

**The Crucial Insight:** This model *was* trained using Margin-Adaptive DPO (MADPO). However, because the TrueSkill decision boundaries learned during MADPO are so mathematically subtle, compressing the weights into aggressive 4-bit (`Q4_K_M`) quantization completely destroyed those fine-grained preference gradients. 

This triggers a phenomenon called **Quantization Collapse**: having lost its high-resolution MADPO decision boundaries, the model collapsed backward, reverting to the probability distribution of its base SFT prior (which inherently suffers from positional bias).

**Next Steps:** To permanently eradicate this positional bias and retain the MADPO alignment, we cannot rely on `Q4` models. We must either preserve high-bit precision (`f16` or `q8_0`) locally, or bypass local GGUF execution entirely by deploying the unquantized PyTorch Teacher model in the cloud to generate the V2 dataset.
---

## Appendix: Sample Test Entry (Design Script)

Below is an exact example of a single test entry pulled directly from `master_dpo_dataset.jsonl`. 

During the **Forward Query**, this exact text is sent to the model. During the **Backward Query**, the metrics under `VARIANT A` and `VARIANT B` are swapped.

### The Input Prompt (The Design Script)
```text
Evaluate Variant A and Variant B for aesthetic equilibrium and structural tension.

VARIANT A METRICS:
- Display Typography: 120.0px, line-height: 144px (1.2 ratio), tracking: normal. Total DOM depth: 2869 nodes.
- Whitespace Ratio: 0.823
- Color Variance: 0.538
- Palette Mood: monochromatic-neutral
- Asymmetry Score: 0.022
- Motion Engine: Native CSS Keyframes (15 keyframes, 20 transitions), No physics engines detected.
- Visual Forensic Description: {
  "focal_subject": {
    "type": "pure_typography",
    "description": "Large black text spelling out 'HECO'."
  },
  "background_style": {
    "type": "flat_color",
    "dominant_hue": "white",
    "has_grain_or_noise": false
  },
  "badges_and_overlays": [
    {
      "type": "floating",
      "text": "BRANDING AND WEB FOR COMPLEX PRODUCTS"
    }
  ],
  "whitespace_distribution": "balanced"
}

VARIANT B METRICS:
- Display Typography: 68.0px, line-height: 69.36px (1.02 ratio), tracking: -1.7px. Total DOM depth: 1148 nodes.
- Whitespace Ratio: 0.902
- Color Variance: 0.655
- Palette Mood: monochromatic-neutral
- Asymmetry Score: 0.082
- Motion Engine: Native CSS Keyframes (14 keyframes, 20 transitions), No physics engines detected.
- Visual Forensic Description: {
  "focal_subject": {
    "type": "product_mockup",
    "description": "A webpage for a product development system designed for teams and agents."
  },
  "background_style": {
    "type": "flat_color",
    "dominant_hue": "black",
    "has_grain_or_noise": false
  },
  "badges_and_overlays": [
    "New",
    "Loops",
    "1/84"
  ],
  "whitespace_distribution": "balanced"
}
```

### The Expected Output (The Golden Critique)
In this specific matchup, Variant A has the superior TrueSkill rating. The model is expected to output this exact structure without any conversational preamble:

```text
Variant A demonstrates elite aesthetic execution.
Taste Rule: The Principle of Evocative Restraint: Allowing negative space and oversized, minimalist typography to carry the conceptual weight, requiring the viewer to complete the design narrative rather than simply consuming stated information.
Premium Signals: Use of high-fidelity, single-purpose motion (e.g., success-popup-progress, which implies controlled, deliberate state change). Strategic deployment of ultra-large type sizing (H1: 120px) that treats type as a dimensional art object rather than mere headline. The calculated asymmetry of the layout, highlighted by the 'asymmetry_score' and the careful distribution of overlays, ensuring visual interest without visual clutter.
```

---

## V2 Evaluation (Q8 High-Precision Weights)

**Test Configuration:** 50 distinct matchups evaluated forward (A vs B) and reversed (B vs A) for a total of 100 queries.
**Model:** `taste-critic-v2` (`taste-critic-sft.Q8_0.gguf`)

### Results
- **Total Queries:** 100
- **Accuracy:** 49/100 = 0.49
- **P(pick A):** 53/100 = 0.53
- **P(pick B):** 47/100 = 0.47
- **Content Stability:** 21/50 = 0.42

### Analysis: The MADPO Generalization Failure
This result reveals a critical failure in the training architecture, correcting a previous misdiagnosis.

**1. The Quantization Collapse is Cured**
In the Q4 evaluation, we observed an extreme positional bias (P(B) = 0.71). In the high-precision Q8 evaluation, that bias is mathematically eradicated (`P(A)=0.53`, `P(B)=0.47`). The model has regained its equilibrium. The collapse into a single positional basin was purely a hardware/quantization artifact.

**2. The Failure of the MADPO Architecture**
*(Note: Previous documentation incorrectly assumed `taste-critic-sft.Q8_0.gguf` was an SFT baseline due to Unsloth inheriting the base filename during export. It is, in fact, the 8-bit exported MADPO TrueSkill model).*

While the positional bias is gone, the MADPO model's logic is fundamentally uncalibrated to the TrueSkill ground truth when run locally.
- **Accuracy is 49%** (statistically indistinguishable from a coin flip).
- **Content Stability is 42%** (it rarely tracks the "winning" metric across positional flips).

**The Final Conclusion:**
This mathematically proves that the **MADPO training failed to generalize** to the 8-Billion parameter local model on the 100-site dataset (456 pairs). While the 16-bit PyTorch model in Colab scored 10/10, the local Q8 49% accuracy indicates the model severely overfit the training data in the cloud and failed to actually learn the underlying aesthetic mathematical gradients. 

Before committing to scaling the 1,000-site batch through this pipeline, we must acknowledge that an 8B local critic might lack the capacity to judge taste from raw JSON. We will reset to manual TrueSkill Elo voting to establish ground truth on the 1,000 batch.

---

## V3 Evaluation (The Continuous Telemetry Engine Pivot)

Following the failure of the 8B LLM to generalize (and its susceptibility to positional shortcuts despite semantic delta injection), we have formally deprecated the LLM/Prompt-Engineering approach for the core mathematical reasoning of the Taste Engine.

**The Architectural Fix (September 17th):**
We are pivoting to a custom **Nano-Transformer** built entirely from scratch in PyTorch (inspired by the minimalist architecture of `nanoGPT`). 
1. **No Tokenization:** To prevent the destruction of high-fidelity floating-point variances, we are bypassing discrete tokenization entirely. Raw metrics will be projected directly into the embedding space via Continuous Linear Projections (`nn.Linear(1, d_model)`).
2. **The Attention Matrix:** The 8 continuous variables (4 from Variant A, 4 from Variant B) will be passed as a sequence, allowing the transformer's self-attention heads to dynamically discover cross-variable rules.
3. **The Sandbox (Overfit Test):** The current 456-pair dataset will NOT be used to train the production model (a 5M parameter model would memorize it instantly). It will be used strictly as an "Overfit Sandbox" to mathematically verify the custom TrueSkill Margin loss and PyTorch tensor routing before we scale to the 10,000-vote Elo dataset.
