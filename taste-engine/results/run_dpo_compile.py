import json
import os

def compile_conversational_dpo(input_filepath: str, output_filepath: str):
    """
    Transforms raw or mixed-format DPO data into strict TRL-compliant 
    conversational arrays, ensuring ChatML token masking compatibility.
    """
    system_directive = (
        "You are a ruthless, hyper-objective aesthetic design critic. You evaluate UI variants strictly on empirical quantitative metrics (DOM depth, whitespace ratio, typographic ratios, and structural tension).\n\n"
        "CRITICAL DIRECTIVE: You must remain completely blind to the sequential order of the variants. Variant A and Variant B have an equal mathematical probability of winning. Your verdict must be derived exclusively from the causal superiority of the metrics, never their order.\n\n"
        "Output zero conversational preamble. Begin immediately with the winning verdict."
    )

    formatted_dataset = []

    with open(input_filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): 
                continue
            data = json.loads(line)

            # Extract raw text regardless of previous v1 (string) or v2 (list) formatting
            raw_prompt = data['prompt'] if isinstance(data['prompt'], str) else data['prompt'][-1]['content']
            raw_chosen = data['chosen'] if isinstance(data['chosen'], str) else data['chosen'][0]['content']
            raw_rejected = data['rejected'] if isinstance(data['rejected'], str) else data['rejected'][0]['content']

            # Strip existing system prompts if they were accidentally baked into the user string during v1 extraction
            if "CRITICAL DIRECTIVE:" in raw_prompt:
                split_prompt = raw_prompt.split("Output zero conversational preamble. Begin immediately with the winning verdict.")
                raw_prompt = split_prompt[-1].strip()

            formatted_entry = {
                "prompt": [
                    {"role": "system", "content": system_directive},
                    {"role": "user", "content": raw_prompt.strip()}
                ],
                "chosen": [
                    {"role": "assistant", "content": raw_chosen.strip()}
                ],
                "rejected": [
                    {"role": "assistant", "content": raw_rejected.strip()}
                ],
                "margin": float(data.get('margin', 0.1)) # Fallback margin to prevent NaN if missing
            }
            formatted_dataset.append(formatted_entry)

    with open(output_filepath, 'w', encoding='utf-8') as f:
        for entry in formatted_dataset:
            f.write(json.dumps(entry) + '\n')

    print(f"Compilation complete. {len(formatted_dataset)} records formatted for TRL DPOTrainer.")

# Execution
compile_conversational_dpo("master_dpo_dataset.jsonl", "master_dpo_dataset_v3.jsonl")
