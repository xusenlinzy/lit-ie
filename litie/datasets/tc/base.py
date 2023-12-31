from typing import Any, List, Optional, Callable
from .rdrop import DataCollatorForRDrop
from datasets import ClassLabel, Dataset
from pytorch_lightning.utilities import rank_zero_warn
from transformers import PreTrainedTokenizerBase
from transformers.data import DataCollatorWithPadding

from ..base import TaskDataModule


class TextClassificationDataModule(TaskDataModule):
    def __init__(
        self,
        *args,
        use_rdrop: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.use_rdrop = use_rdrop

    def process_data(self, dataset: Dataset, stage: Optional[str] = None) -> Dataset:
        input_feature_fields = [k for k, v in dataset["train"].features.items() if k not in ["label", "idx", "id"]]
        dataset = TextClassificationDataModule.preprocess(
            dataset,
            tokenizer=self.tokenizer,
            input_feature_fields=input_feature_fields,
            padding=False,
            truncation=True,
            max_length=self.train_max_length,
        )
        cols_to_keep = [
            x for x in ["input_ids", "attention_mask", "token_type_ids", "labels"] if x in dataset["train"].features
        ]
        if not isinstance(dataset["train"].features["labels"], ClassLabel):
            dataset = dataset.class_encode_column("labels")
        dataset.set_format("torch", columns=cols_to_keep)
        self.labels = dataset["train"].features["labels"]
        return dataset

    @property
    def num_classes(self) -> int:
        if self.labels is None:
            rank_zero_warn("Labels has not been set, calling `setup('fit')`.")
            self.setup("fit")
        return self.labels.num_classes

    @property
    def label2id(self) -> dict:
        if self.labels is None:
            rank_zero_warn("Labels has not been set, calling `setup('fit')`.")
            self.setup("fit")
        return {l: int(i) for i, l in enumerate(self.labels.names)}

    @staticmethod
    def convert_to_features(
        example_batch: Any, _, tokenizer: PreTrainedTokenizerBase, input_feature_fields: List[str], **tokenizer_kwargs
    ):
        # Either encode single sentence or sentence pairs
        if len(input_feature_fields) > 1:
            texts_or_text_pairs = list(
                zip(example_batch[input_feature_fields[0]], example_batch[input_feature_fields[1]])
            )
        else:
            texts_or_text_pairs = example_batch[input_feature_fields[0]]
        # Tokenize the text/text pairs
        return tokenizer(texts_or_text_pairs, **tokenizer_kwargs)

    @staticmethod
    def preprocess(ds: Dataset, **fn_kwargs) -> Dataset:
        ds = ds.map(
            TextClassificationDataModule.convert_to_features,
            batched=True,
            with_indices=True,
            fn_kwargs=fn_kwargs,
        )
        ds = ds.rename_column("label", "labels")
        return ds

    @property
    def collate_fn(self) -> Optional[Callable]:
        return DataCollatorWithPadding(self.tokenizer) if not self.use_rdrop else DataCollatorForRDrop(self.tokenizer)
