from typing import Optional, List, Any

import torch
import torch.nn as nn
from transformers import PreTrainedModel

from ..model_utils import SequenceLabelingOutput, MODEL_MAP
from ...datasets.utils import tensor_to_cpu
from ...layers import HandshakingKernel
from ...losses import MultilabelCategoricalCrossentropy


def get_auto_tplinker_ner_model(
    model_type: Optional[str] = "bert",
    base_model: Optional[PreTrainedModel] = None,
    parent_model: Optional[PreTrainedModel] = None,
):
    if base_model is None and parent_model is None:
        base_model, parent_model = MODEL_MAP[model_type]

    class TPLinkerPlusForNer(parent_model):
        """
        基于`BERT`的`TPLinker`实体识别模型
        + 📖 将`TPLinker`的`shaking`机制引入实体识别模型
        + 📖 对于`token`对采用矩阵上三角展开的方式进行多标签分类

        Args:
            `config`: 模型的配置对象

        Reference:
            ⭐️ [TPLinker: Single-stage Joint Extraction of Entities and Relations Through Token Pair Linking.](https://aclanthology.org/2020.coling-main.138.pdf)
            🚀 [Official Code](https://github.com/131250208/TPlinker-joint-extraction)
            🚀 [Simplified Code](https://github.com/Tongjilibo/bert4torch/blob/master/examples/sequence_labeling/task_sequence_labeling_ner_tplinker_plus.py)
        """

        def __init__(self, config):
            super().__init__(config)
            self.config = config
            setattr(self, self.base_model_prefix, base_model(config, add_pooling_layer=False))

            classifier_dropout = (
                config.classifier_dropout if config.classifier_dropout is not None else config.hidden_dropout_prob
            )
            self.dropout = nn.Dropout(classifier_dropout)

            self.handshaking_kernel = HandshakingKernel(config.hidden_size, config.shaking_type)
            self.out_dense = nn.Linear(config.hidden_size, config.num_labels)

            # Initialize weights and apply final processing
            self.post_init()

        def forward(
            self,
            input_ids: Optional[torch.Tensor] = None,
            attention_mask: Optional[torch.Tensor] = None,
            token_type_ids: Optional[torch.Tensor] = None,
            labels: Optional[torch.Tensor] = None,
            texts: Optional[List[str]] = None,
            offset_mapping: Optional[List[Any]] = None,
            target: Optional[List[Any]] = None,
            return_decoded_labels: Optional[bool] = True,
        ) -> SequenceLabelingOutput:

            outputs = getattr(self, self.base_model_prefix)(
                input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
            )

            sequence_output = self.dropout(outputs[0])

            # shaking_hiddens: (batch_size, shaking_seq_len, hidden_size)
            shaking_hiddens = self.handshaking_kernel(sequence_output)
            # shaking_logits: (batch_size, shaking_seq_len, tag_size)
            shaking_logits = self.out_dense(shaking_hiddens)

            loss, predictions = None, None
            if labels is not None:
                loss = self.compute_loss([shaking_logits, labels])

            if not self.training and return_decoded_labels:
                predictions = self.decode(shaking_logits, attention_mask, texts, offset_mapping)

            return SequenceLabelingOutput(
                loss=loss,
                logits=shaking_logits,
                predictions=predictions,
                groundtruths=target,
                hidden_states=outputs.hidden_states,
                attentions=outputs.attentions,
            )

        def decode(self, shaking_logits, attention_mask, texts, offset_mapping):
            all_entity_list = []
            seq_len = attention_mask.shape[1]

            seqlens, shaking_logits = tensor_to_cpu(attention_mask.sum(1)), tensor_to_cpu(shaking_logits)
            shaking_idx2matrix_idx = [(s, e) for s in range(seq_len) for e in list(range(seq_len))[s:]]
            id2label = {int(v): k for k, v in self.config.tplinker_label2id.items()}

            for _shaking_logits, l, text, mapping in zip(shaking_logits, seqlens, texts, offset_mapping):
                entities = set()
                l = l.item()
                matrix_spots = self.get_spots_fr_shaking_tag(shaking_idx2matrix_idx, _shaking_logits)

                for e in matrix_spots:
                    tag = id2label[e[2]]
                    # for an entity, the start position can not be larger than the end pos.
                    if e[0] > e[1] or 0 in [e[0], e[1]] or e[0] >= l - 1 or e[1] >= l - 1:
                        continue
                    _start, _end = mapping[e[0]][0], mapping[e[1]][1]
                    entities.add(
                        (
                            tag,
                            _start,
                            _end,
                            text[_start: _end]
                        )
                    )
                all_entity_list.append(entities)

            return all_entity_list

        def get_spots_fr_shaking_tag(self, shaking_idx2matrix_idx, shaking_outputs):
            """
            shaking_tag -> spots
            shaking_tag: (shaking_seq_len, tag_id)
            spots: [(start, end, tag), ]
            """
            spots = []
            pred_shaking_tag = (shaking_outputs > self.config.decode_thresh).long()
            nonzero_points = torch.nonzero(pred_shaking_tag, as_tuple=False)
            for point in nonzero_points:
                shaking_idx, tag_idx = point[0].item(), point[1].item()
                pos1, pos2 = shaking_idx2matrix_idx[shaking_idx]
                spot = (pos1, pos2, tag_idx)
                spots.append(spot)
            return spots

        def compute_loss(self, inputs):
            shaking_logits, labels = inputs[:2]
            loss_fct = MultilabelCategoricalCrossentropy()
            return loss_fct(shaking_logits, labels)

    return TPLinkerPlusForNer


def get_tplinker_ner_model_config(labels: list, **kwargs):
    labels = sorted(labels)
    label2id = {v: i for i, v in enumerate(labels)}
    model_config = {
        "num_labels": len(labels),
        "tplinker_label2id": label2id,
        "shaking_type": "cln_plus",
        "decode_thresh": 0.,
    }
    model_config.update(kwargs)
    return model_config
