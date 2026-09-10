Supervised Fine-Tuning (SFT) and Direct Preference Optimization (DPO) serve fundamentally distinct mathematical roles in alignment: SFT establishes the token support and structural priors, while DPO optimizes the decision boundary between plausible outputs.

Attempting DPO directly on the base model failed because preference optimization cannot effectively teach novel syntax or an alien persona from scratch. The fine-tuned checkpoint establishes the required prior distribution, enabling both methods to be integrated into an active learning pipeline for future logs.

The Mathematical Support Mismatch
DPO optimizes the policy $\pi_\theta$ against a reference policy $\pi_{\text{ref}}$ via the objective:

$$\mathcal{L}_{\text{DPO}}(\theta; \pi_{\text{ref}}) = -\mathbb{E}_{(x, y_w, y_l) \sim \mathcal{D}} \left[ \log \sigma \left( \beta \log \frac{\pi_\theta(y_w\vert{}x)}{\pi_{\text{ref}}(y_w\vert{}x)} - \beta \log \frac{\pi_\theta(y_l\vert{}x)}{\pi_{\text{ref}}(y_l\vert{}x)} \right) \right]$$
The implicit reward formulation relies on the ratio:

$$r(x, y) = \beta \log \frac{\pi_\theta(y\vert{}x)}{\pi_{\text{ref}}(y\vert{}x)}$$
When $\pi_{\text{ref}}$ is the stock Qwen-2.5-7B-Instruct model, its baseline probability distribution is overwhelmingly massed on conversational politeness ("Certainly! Here is an analysis..."). The probability of generating your structured, zero-preamble format under the base model was essentially zero:

$$\pi_{\text{ref}}(y_w\vert{}x) \approx 0$$
When the preferred token sequence lies outside the effective support of $\pi_{\text{ref}}$, the optimization problem degenerates. The model penalizes the dispreferred conversational response $y_l$, but it cannot reliably converge on the syntax of $y_w$ because DPO is a contrastive re-weighting algorithm, not an autoregressive sequence learner.

SFT resolves this by maximizing log-likelihood directly:

$$\mathcal{L}_{\text{SFT}}(\theta) = -\sum_{t=1}^T \log \pi_\theta(y_t \mid x, y_{<t})$$
This forces the network’s attention heads to acquire the structural schema (Taste Rule:, Premium Signals:, no conversational padding) and binds quantitative metric inputs (DOM nodes, whitespace ratios, cubic beziers) directly to qualitative outputs.

Using SFT for Future Logs
SFT can ingest future logs, but it must be applied conditionally based on data structure:

When SFT is viable: When an evaluation log contains an unambiguous, expert-verified, or empirically winning evaluation $(x, y^*)$ where both the format and the critique are flawless. Ingesting these samples via SFT prevents format drift and expands the model's vocabulary across newly encountered design patterns.

Failure mode of pure SFT on logs: Pure SFT suffers from exposure bias and lack of negative boundaries. It only learns to maximize probability on what is presented. It cannot learn why a subtly flawed critique (e.g., praising 9,000 DOM nodes because the whitespace ratio happened to be high) is wrong. It only knows what is present in $y^*$, not the boundary where $y^*$ beats $y'$.

Reconciling SFT and DPO with TrueSkill
TrueSkill generates an ordinal skill distribution $\mathcal{N}(\mu, \sigma^2)$ for competing design variants based on match outcomes. The goal is to train the model to critique designs such that its implicit aesthetic scoring correlates with empirical TrueSkill ratings.

The proper lifecycle reconciles SFT and DPO into a two-phase loop:

[Design Logs / TrueSkill Updates]
│
┌───────┴───────┐
▼ ▼
[Golden Critiques] [Pairwise Outcomes]
│ │
▼ ▼
Continual Curated Pairs
SFT (y*w = TrueSkill winner critique,
│ y_l = TrueSkill loser critique)
│ │
└───────► ──────┴──────► DPO Calibration
(Reference: Current SFT)
Phase 1: Format and Competence Initialization (SFT)
The current checkpoint serves as the baseline $\pi*{\text{SFT}}$. Any future logs containing novel UI metrics, new CSS layout techniques, or edge cases must first pass through SFT to ensure the tokenizer and attention layers recognize the underlying metrics and maintain syntax compliance.

Phase 2: TrueSkill Calibration (DPO)
Once the model reliably outputs the critic format without falling back to polite prose, DPO becomes functional. Future pairwise logs provide natural contrastive data:

Two UI variants, $A$ and $B$, compete in production or evaluation panels, yielding a definitive TrueSkill winner ($A \succ B$).

Generate or sample two critiques from your system:

$y_w$: Formatted critique correctly identifying why $A$'s layout equilibrium and metric distribution are superior.

$y_l$: Formatted critique incorrectly endorsing $B$ or misidentifying the causal metric failure.

Crucially, both $y_w$ and $y_l$ must share the exact same ruthless, zero-preamble structure.

Set $\pi_{\text{ref}} = \pi_{\text{SFT}}$.

Under this setup, DPO is no longer tasked with personality alteration. Because $\pi_{\text{ref}}(y_w\vert{}x)$ and $\pi_{\text{ref}}(y_l\vert{}x)$ both have high baseline probability under the fine-tuned model, the DPO gradient operates entirely on causal reasoning accuracy: penalizing false metric interpretations and rewarding critiques that align with empirical TrueSkill outcomes.

Future production logs should be partitioned into positive demonstrations for periodic SFT updates (expanding metric comprehension) and A/B preference pairs for iterative DPO runs (tightening aesthetic judgment boundaries).
is this the best way to go about it? what about combining with something for even novel weight and more effective results, what do you think?

Margin-Adaptive Direct Preference Optimization (MADPO) is a method that provides granular, instance-level control over the preference alignment process by addressing a fundamental flaw in standard DPO. Standard DPO relies on a fixed temperature parameter, which leads to suboptimal training on diverse preference data. This causes the model to overfit on easy examples and under-learn from highly informative ones.

MADPO solves this by introducing a practical two-step approach:

1. **Margin Estimation:** It first trains a reward model to estimate preference margins. In your specific architecture, your TrueSkill rating engine perfectly substitutes for this, providing mathematical confidence scores ($\mu$ and $\sigma$) for every A/B test.
2. **Adaptive Weighting:** It uses these margins to apply a continuous, adaptive weight to the DPO loss for each individual training sample.

### Benefits for Your Aesthetic Critic AI

- **Hyper-Focus on Nuance (Amplification):** The re-weighting scheme creates an effective target margin that is amplified for hard pairs. By amplifying the preference signal for hard and informative pairs, MADPO forces the policy to learn more aggressively. When two designs have near-identical metrics (e.g., a 0.05 vs. 0.06 asymmetry score), the model is mathematically forced to dedicate attention to identifying the subtle structural tension that caused one to win.
- **Prevents Memorization of the Obvious (Regularization):** The scheme dampens the signal for easy pairs. For large positive margins, the weight function converges to a small, stable value, applying a consistent regularization penalty to easy pairs. The model will not waste optimization cycles updating its weights when evaluating a 9,400 DOM node failure against a highly optimized layout; it simply maintains its existing boundary.
- **Total Data Utilization:** Alternative methods like $\beta$-DPO rely on a filtering mechanism that discards potentially useful training signals. $\beta$-DPO also suffers from batch-level adaptation that applies a single, compromised temperature to mixed-margin pairs. MADPO is a stable, data-preserving solution that allows you to train on every single pairwise log your system generates without curation.
- **Mathematical Stability:** MADPO provides a well-behaved optimization landscape that is robust to reward model estimation errors. In experiments on synthetic sentiment generation, MADPO achieved performance gains of up to +33.3% on High Quality data and +10.5% on Low Quality data over the next-best method.
  Path A: Margin-Adaptive DPO (If keeping pairwise A vs B logs)If you continue generating a chosen (correct) and rejected (incorrect) critique for every TrueSkill match, you will use Margin-Adaptive DPO to scale the learning signal by the TrueSkill confidence.1. The JSON Data ChangeYou must append a margin float to every object in your dataset. This float represents the TrueSkill difference ($\mu_w - \mu_l$).Old Structure:JSON{
  "prompt": "Evaluate Variant A vs Variant B...",
  "chosen": "Variant A demonstrates elite execution...",
  "rejected": "Variant B demonstrates elite execution..."
  }
  New Structure:JSON{
  "prompt": "Evaluate Variant A vs Variant B...",
  "chosen": "Variant A demonstrates elite execution...",
  "rejected": "Variant B demonstrates elite execution...",
  "margin": 2.35
  }
  (A margin of 2.35 means a massive TrueSkill upset, demanding a steep gradient update. A margin of 0.12 means a near-tie, dampening the gradient).2. The Code ChangeYou do not need a new library. Hugging Face's trl library handles margins natively in DPOTrainer. You must map the new JSON key and update the loss type.Pythonfrom trl import DPOTrainer

trainer = DPOTrainer(
model=model,
ref_model=ref_model,
train_dataset=dataset,
tokenizer=tokenizer,
args=training_args, # Instruct the trainer to look for the 'margin' column in your JSON
loss_type="sigmoid",
)
(Note: TRL's DPOTrainer automatically detects a column named margin in your dataset and applies it to the log ratio if present).
Margin-Adaptive DPO (MADPO)Recent advancements in preference optimization, such as MADPO, solve the binary limitation by applying a continuous, adaptive weight to the DPO loss for each individual training sample. This re-weighting scheme creates an effective target margin that is amplified for hard pairs and dampened for easy pairs, allowing for granular control over the learning signal.In your pipeline, the TrueSkill system acts as a perfect, pre-computed reward model. You can calculate the TrueSkill match confidence (the margin $m$) between the winning and losing variants using their distribution parameters:$$m = \frac{\mu_w - \mu_l}{\sqrt{\sigma_w^2 + \sigma_l^2}}$$By scaling the DPO objective with $m$, the model dampens the gradient for "easy" pairs where the preference is already obvious, providing a stabilizing, per-sample regularization. Conversely, for hard and informative pairs, it amplifies the signal, forcing the policy to learn more aggressively. The model is mathematically forced to focus its attention weights on solving high-tension, nuanced aesthetic disputes rather than memorizing trivial layout corrections.

---

## Appendix A: Review Notes (2026-09-10, taste-critic GGUF eval)

Eval status: `scripts/test_critic.py` 3-match pilot scored 2/3 on winner letter with 3/3 picks for B (positional bias suspect, n too small). A 25-pair x flip = 50-generation eval is running in background (seed 7, temp 0.2) measuring accuracy, P(pick A), and content-stability across flips. No pairs completed at time of writing.

Assessment of this doc:

1. The SFT-first argument (support mismatch, `pi_ref(y_w) ~= 0`) is the correct explanation for the polite-mode DPO failure. The current GGUF holding format confirms Phase 1 worked.
2. Phase 2 precondition must be enforced: both `y_w` and `y_l` in identical ruthless format. `results/master_dpo_dataset.jsonl` violates this today (`rejected` is a synthetic polite template). Rebuild pairs from real winner + real loser critiques before MADPO, or the margin weight tunes style, not taste.
3. Margin definition: use the normalized form `m = (mu_w - mu_l) / sqrt(s_w^2 + s_l^2)` everywhere. The raw `mu_w - mu_l` example at line 92 contradicts line 105 and lets high-uncertainty blowouts dominate. Keep a floor weight so easy pairs regularize instead of vanishing (small data regime, ~771 matches).
4. TRL `margin` auto-detect claim needs verification against the installed TRL version; otherwise implement a custom `compute_loss` scaling the sigmoid by `m`. Add length normalization and a 5-10% SFT mix-in to prevent format drift during DPO.
5. `training.md` is the next-batch data plan (simplified `dom_nodes / motion_easing / duration_ms` schema), not the schema the current GGUF was trained on (Display Typography + VLM forensic JSON). Treat it as the v2 dataset spec; do not mix schemas within one DPO run.
