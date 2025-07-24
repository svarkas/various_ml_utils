import sys
from types import prepare_class
from typing import Optional
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForTokenClassification, TrainingArguments, Trainer
import numpy as np
from seqeval.metrics import classification_report, accuracy_score, f1_score

my_dataset = load_dataset("json", data_files={"train": "data/train_data.jsonl"})
labels = set()

for row in my_dataset["train"]:
    labels.update(row["labels"])

label_list = sorted(labels)
label_to_id = {label: i for i, label in enumerate(label_list)}
id_to_label =  {i: label for label, i in label_to_id.items()}

tokenizer = AutoTokenizer.from_pretrained("bert-base-cased")

def tokenize_and_aligh_labels(example):
    tokenized = tokenizer( example["tokens"], truncation=True, is_split_into_words=True, return_offsets_mapping=True )

    label_ids = []
    previous_word_idx = None
    word_ids = tokenized.word_ids()

    for word_idx in word_ids:
        if word_idx is None:
            label_ids.append(-100)
        elif word_idx != previous_word_idx:
            label_ids.append(label_to_id[example["labels"][word_idx]])
        else:
            orig_label = example["labels"][word_idx]
            if orig_label.startswith("B-"):
                new_label = "I-" + orig_label[2:]
            else:
                new_label = orig_label
            label_ids.append(label_to_id[new_label])
        previous_word_idx = word_idx
    
    tokenized["labels"] = label_ids
    
    return tokenized

tokenized_dataset = my_dataset.map(tokenize_and_aligh_labels)

model = AutoModelForTokenClassification.from_pretrained("bert-base-cased",
                                                        num_labels=len(label_list),
                                                        id2label=id_to_label,
                                                        label2id=label_to_id,
                                                        )

args = TrainingArguments(output_dir="./data/cell_line_model",
                        evaluation_strategy="epoch",
                        learning_rate=2e-5,
                        per_device_train_batch_size=8,
                        num_train_epochs=5,
                        weight_decay=0.01,
                        )

def compute_metrics(p):
    prediction, labels = p 
    predictions = np.argmax(predictions, axis=2)

    true_labels = [[id_to_label[l] for l in label if l !=-100] for label in labels]
    true_preds = [[id_to_label[p] for (p, l) in zip(pred, label) if l !=-100] for pred, label in zip(predictions, labels)]

    return {
            "accuracy": accuracy_score(true_labels, true_preds),
            "fi": f1_score(true_labels, true_preds),
    }

trainer = Trainer(
    model=model,
        args=args,
        train_dataset=tokenized_dataset["train"],
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
)

trainer.train()

trainer.save_mode("my_cell_model")
tokenizer.save_pretrained("my_cell_model")
