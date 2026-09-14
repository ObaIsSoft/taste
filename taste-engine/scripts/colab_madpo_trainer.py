"""
Margin-Adaptive DPO (MADPO) Trainer for Unsloth / TRL
Designed for Google Colab

This script overrides the standard DPOTrainer to implement TrueSkill Margin scaling,
length normalization, and a 5% SFT mix-in to prevent formatting drift.
"""

import torch
import torch.nn.functional as F
from trl import DPOTrainer

class MADPOTrainer(DPOTrainer):
    def __init__(self, sft_weight=0.05, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sft_weight = sft_weight
        
    def get_batch_loss_metrics(
        self,
        model,
        batch,
        train_eval: str = "train",
    ):
        """
        Override TRL's get_batch_loss_metrics to apply Instance-Weighted DPO
        using our TrueSkill margins.
        """
        metrics = {}

        # 1. Forward pass for chosen and rejected
        policy_chosen_logps, policy_rejected_logps, policy_chosen_logits, policy_rejected_logits = self.concatenated_forward(
            model, batch
        )

        with torch.no_grad():
            if self.ref_model is None:
                # If using PEFT/LoRA, the base model is used via context manager
                with self.null_ref_context():
                    reference_chosen_logps, reference_rejected_logps, _, _ = self.concatenated_forward(
                        model, batch
                    )
            else:
                reference_chosen_logps, reference_rejected_logps, _, _ = self.concatenated_forward(
                    self.ref_model, batch
                )

        # 2. Length Normalization
        # Divide logprobs by sequence length to prevent verbosity hacking
        chosen_lens = batch.get("chosen_labels").ne(-100).sum(dim=-1).float()
        rejected_lens = batch.get("rejected_labels").ne(-100).sum(dim=-1).float()
        
        policy_chosen_logps_norm = policy_chosen_logps / chosen_lens
        policy_rejected_logps_norm = policy_rejected_logps / rejected_lens
        reference_chosen_logps_norm = reference_chosen_logps / chosen_lens
        reference_rejected_logps_norm = reference_rejected_logps / rejected_lens

        # 3. Standard DPO Implicit Reward
        chosen_rewards = self.beta * (policy_chosen_logps_norm - reference_chosen_logps_norm)
        rejected_rewards = self.beta * (policy_rejected_logps_norm - reference_rejected_logps_norm)
        
        # 4. Apply Margin Weighting (Instance-Weighted DPO)
        # Margins are passed through the dataset
        raw_margins = batch.get("margin", None)
        if raw_margins is None:
            raise ValueError("CRITICAL BUG: 'margin' column was purged by the data collator. Ensure remove_unused_columns=False in DPOConfig.")
        margins = raw_margins
        
        # Log-sigmoid loss scaled by the TrueSkill margin
        dpo_loss = -margins * F.logsigmoid(chosen_rewards - rejected_rewards)
        
        # 5. SFT Mix-in (Format Drift Prevention)
        # Calculate standard autoregressive NLL on the chosen response
        # policy_chosen_logps is exactly the -NLL loss scaled by length. 
        # TRL already returned the log probabilities of the labels.
        # We want to MINIMIZE negative logprobs, so we add -policy_chosen_logps_norm
        sft_loss = -policy_chosen_logps_norm
        
        # Final combined loss
        loss = dpo_loss + (self.sft_weight * sft_loss)

        # 6. Logging metrics
        reward_accuracies = (chosen_rewards > rejected_rewards).float()
        
        metrics[f"loss/{train_eval}"] = loss.mean().item()
        metrics[f"dpo_loss/{train_eval}"] = dpo_loss.mean().item()
        metrics[f"sft_loss/{train_eval}"] = sft_loss.mean().item()
        metrics[f"rewards/chosen_{train_eval}"] = chosen_rewards.mean().item()
        metrics[f"rewards/rejected_{train_eval}"] = rejected_rewards.mean().item()
        metrics[f"rewards/accuracies_{train_eval}"] = reward_accuracies.mean().item()
        metrics[f"rewards/margins_{train_eval}"] = margins.mean().item()

        return loss.mean(), chosen_rewards.mean(), rejected_rewards.mean(), metrics

# --- Example Colab Usage ---
if __name__ == "__main__":
    print("This script provides the MADPOTrainer class. Do not run it directly.")
    print("In your Colab notebook, define this class and use it instead of DPOTrainer:")
    print('''
# Colab Snippet:
from colab_madpo_trainer import MADPOTrainer

trainer = MADPOTrainer(
    sft_weight=0.05,
    model=model,
    ref_model=None, # if using PEFT
    args=training_args,
    beta=0.1,
    train_dataset=dataset,
    tokenizer=tokenizer,
)
trainer.train()
    ''')
