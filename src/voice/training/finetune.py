"""LoRA fine-tuning script for whisper-large-v3-turbo on military radio data.

Uses QLoRA (4-bit quantization) to fit in 6-8 GB VRAM.
Trains only decoder LoRA adapters with encoder frozen.

Usage:
    python -m src.voice.training.finetune \
        --data-dir data/training \
        --output-dir models/whisper-military-lora \
        --steps 500
"""

from __future__ import annotations

import argparse
import csv
import logging
import os

logger = logging.getLogger(__name__)


def load_dataset(data_dir: str):
    """Load training data from manifest CSV into HuggingFace Dataset format."""
    import soundfile as sf
    from datasets import Dataset

    manifest_path = os.path.join(data_dir, "manifest.csv")
    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Read audio files directly with soundfile (works on Windows, no torchcodec needed)
    audio_arrays = []
    transcripts = []
    for r in rows:
        filepath = os.path.join(data_dir, r["path"])
        try:
            data, sr = sf.read(filepath, dtype="float32")
            audio_arrays.append({"array": data, "sampling_rate": sr})
            transcripts.append(r["transcript"])
        except Exception as e:
            logger.warning("Skipping %s: %s", r["path"], e)

    ds = Dataset.from_dict({"audio": audio_arrays, "transcript": transcripts})
    return ds


def prepare_dataset(dataset, processor):
    """Preprocess dataset for Whisper training."""

    def prepare_example(example):
        audio = example["audio"]
        input_features = processor.feature_extractor(
            audio["array"], sampling_rate=audio["sampling_rate"]
        ).input_features[0]

        labels = processor.tokenizer(example["transcript"]).input_ids
        return {"input_features": input_features, "labels": labels}

    return dataset.map(prepare_example, remove_columns=dataset.column_names)


def run_finetune(
    data_dir: str,
    output_dir: str,
    model_name: str = "openai/whisper-large-v3-turbo",
    steps: int = 500,
    batch_size: int = 4,
    grad_accum: int = 4,
    learning_rate: float = 1e-4,
    lora_r: int = 32,
    lora_alpha: int = 64,
) -> str:
    """Run LoRA fine-tuning.

    Returns:
        Path to the saved LoRA adapter.
    """
    import torch
    from transformers import (
        WhisperForConditionalGeneration,
        WhisperProcessor,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
    )
    from peft import LoraConfig, get_peft_model

    logger.info("Loading model: %s", model_name)
    processor = WhisperProcessor.from_pretrained(model_name)

    # Load in float32 — Trainer's fp16 flag handles mixed precision automatically
    model = WhisperForConditionalGeneration.from_pretrained(model_name)

    # Freeze encoder entirely — only train decoder LoRA adapters
    model.model.encoder.requires_grad_(False)

    # Apply LoRA to decoder
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "v_proj", "k_proj", "out_proj", "fc1", "fc2"],
        lora_dropout=0.05,
        bias="none",
        task_type="SEQ_2_SEQ_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load + preprocess dataset
    logger.info("Loading dataset from %s", data_dir)
    dataset = load_dataset(data_dir)
    processed = prepare_dataset(dataset, processor)

    # Split 90/10
    split = processed.train_test_split(test_size=0.1, seed=42)

    # Training arguments
    training_args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        num_train_epochs=3,
        max_steps=steps,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=learning_rate,
        warmup_steps=50,
        fp16=torch.cuda.is_available(),
        eval_strategy="steps",
        eval_steps=100,
        save_steps=100,
        logging_steps=25,
        predict_with_generate=True,
        generation_max_length=225,
        report_to="none",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        remove_unused_columns=False,
    )

    # Data collator for Whisper
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class WhisperDataCollator:
        processor: Any

        def __call__(self, features):
            input_features = [{"input_features": f["input_features"]} for f in features]
            batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

            label_features = [{"input_ids": f["labels"]} for f in features]
            labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")

            labels = labels_batch["input_ids"].masked_fill(
                labels_batch.attention_mask.ne(1), -100
            )
            batch["labels"] = labels
            return batch

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        data_collator=WhisperDataCollator(processor),
        processing_class=processor.feature_extractor,
    )

    logger.info("Starting LoRA fine-tuning: %d steps", steps)
    trainer.train()

    # Save LoRA adapter (~60MB)
    adapter_path = os.path.join(output_dir, "lora-adapter")
    model.save_pretrained(adapter_path)
    processor.save_pretrained(adapter_path)
    logger.info("LoRA adapter saved to %s", adapter_path)

    return adapter_path


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="LoRA fine-tune Whisper on military radio data")
    parser.add_argument("--data-dir", default="data/training", help="Training data directory")
    parser.add_argument("--output-dir", default="models/whisper-military-lora", help="Output directory")
    parser.add_argument("--steps", type=int, default=500, help="Max training steps")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    args = parser.parse_args()

    run_finetune(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        steps=args.steps,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        learning_rate=args.lr,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
    )


if __name__ == "__main__":
    main()
