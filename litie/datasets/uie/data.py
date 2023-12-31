from functools import partial
from typing import Optional, Union, Dict

import numpy as np
from datasets import Dataset
from transformers import default_data_collator

from ..base import TaskDataModule


class UieDataModule(TaskDataModule):
    def __init__(self, *args, task_name: str = "uie", is_chinese: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.is_chinese = is_chinese

    def process_data(self, dataset: Union[Dataset, Dict], stage: Optional[str] = None) -> Union[Dataset, Dict]:
        convert_to_features = partial(
            UieDataModule.convert_example,
            tokenizer=self.tokenizer,
            max_seq_len=self.train_max_length,
        )

        dataset = dataset.map(
            convert_to_features,
            remove_columns=dataset["train"].column_names,
            num_proc=self.num_workers,
        )

        return dataset

    @staticmethod
    def convert_example(example, tokenizer, max_seq_len):
        """ example: {prompt content result_list} """
        encoded_inputs = tokenizer(
            text=[example["prompt"]],
            text_pair=[example["content"]],
            truncation=True,
            max_length=max_seq_len,
            add_special_tokens=True,
            return_offsets_mapping=True)

        offset_mapping = [list(x) for x in encoded_inputs["offset_mapping"][0]]
        bias = 0
        for index in range(1, len(offset_mapping)):
            mapping = offset_mapping[index]
            if mapping[0] == 0 and mapping[1] == 0 and bias == 0:
                bias = offset_mapping[index - 1][1] + 1  # Includes [SEP] token
            if mapping[0] == 0 and mapping[1] == 0:
                continue

            offset_mapping[index][0] += bias
            offset_mapping[index][1] += bias

        start_ids = np.zeros((max_seq_len,))
        end_ids = np.zeros((max_seq_len,))

        def map_offset(ori_offset, offset_mapping):
            """
            map ori offset to token offset
            """
            return next((index for index, span in enumerate(offset_mapping) if span[0] <= ori_offset < span[1]), -1)

        for item in example["result_list"]:
            start = map_offset(item["start"] + bias, offset_mapping)
            end = map_offset(item["end"] - 1 + bias, offset_mapping)
            start_ids[start] = 1.0
            end_ids[end] = 1.0

        input_ids = np.array(encoded_inputs["input_ids"][0], dtype="int64")
        attention_mask = np.asarray(encoded_inputs["attention_mask"][0], dtype="int64")
        token_type_ids = np.asarray(encoded_inputs["token_type_ids"][0], dtype="int64")

        tokenized_output = {
            "input_ids": input_ids,
            "token_type_ids": token_type_ids,
            "attention_mask": attention_mask,
            "start_positions": start_ids,
            "end_positions": end_ids,
        }

        tokenized_output = {
            k: np.pad(v, (0, max_seq_len - v.shape[-1]), 'constant')
            for k, v in tokenized_output.items()
        }
        return tokenized_output

    @property
    def collate_fn(self):
        return default_data_collator
