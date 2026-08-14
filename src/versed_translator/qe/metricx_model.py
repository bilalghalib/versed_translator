#
# Vendored from google-research/metricx (`metricx24/models.py`).
#   https://github.com/google-research/metricx
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# ---------------------------------------------------------------------------
# WHY THIS FILE EXISTS
#
# The MetricX-24 checkpoints on the Hugging Face Hub ship *only* `config.json`
# and `pytorch_model.bin`. There is no `auto_map`, no custom-code loader and no
# tokenizer, so `AutoModel.from_pretrained` cannot instantiate them: the
# regression head below is the missing piece. The upstream `metricx24` package
# is a plain source tree on GitHub with no `setup.py`/`pyproject.toml` and no
# PyPI release (`pip install metricx24` 404s; the unrelated `metricx` on PyPI
# is a benchmark-data library by a different author), so it cannot be added as
# a dependency. Apache-2.0 permits vendoring; the notice above is retained per
# the license.
#
# DELIBERATE DEVIATIONS FROM UPSTREAM (upstream pins transformers==4.30.2; we
# run 4.5x):
#   1. `use_cache` is forced to False for the decoder call. The decoder is run
#      for exactly one dummy step, so a KV cache buys nothing, and newer
#      transformers returns a `Cache` object here rather than a tuple.
#   2. The dummy `decoder_input_ids` are placed on the encoder output's device
#      instead of an unconditional `.to("cuda")`. Upstream's version breaks on
#      CPU-only and MPS hosts; this repo scores on CPU.
#   3. Cosmetic only: 4-space indent, PEP 604 type hints, no `# coding=utf-8`,
#      and the unused `past_key_values` arg absorbed into `**kwargs`. This is
#      what this repo's ruff config demands; none of it touches behavior.
# The parts that decide the number — the magic `<extra_id_10>` logit index, the
# single dummy decoder step, and the [0, 25] clamp — are unchanged.
# ---------------------------------------------------------------------------
"""MT5ForRegression: the MetricX prediction head, for loading MetricX-24."""

from __future__ import annotations

import copy
import dataclasses

import torch
import transformers
import transformers.modeling_outputs
from torch import nn

BaseModelOutput = transformers.modeling_outputs.BaseModelOutput
ModelOutput = transformers.modeling_outputs.ModelOutput

MT5Config = transformers.models.mt5.modeling_mt5.MT5Config
MT5PreTrainedModel = transformers.models.mt5.modeling_mt5.MT5PreTrainedModel
MT5Stack = transformers.models.mt5.modeling_mt5.MT5Stack

# The vocabulary id of `<extra_id_10>`. MetricX was trained in T5X to emit its
# score as the logit of this one token at decoder step 0 — it is not a
# configurable hyperparameter, it is baked into the checkpoint weights.
_SCORE_TOKEN_ID = 250089

# MetricX-24 clamps predictions into the MQM-style error range [0, 25].
METRICX_SCORE_MIN = 0.0
METRICX_SCORE_MAX = 25.0


@dataclasses.dataclass
class MT5ForRegressionOutput(ModelOutput):
    loss: torch.FloatTensor | None = None
    predictions: torch.FloatTensor = None


class MT5ForRegression(MT5PreTrainedModel):
    """MT5 encoder-decoder with a scalar regression read-out.

    `forward` returns `predictions`: a per-example float in [0, 25] that is an
    **error** score — LOWER IS BETTER. Callers in this repo must not use it
    raw; see `detection_matrix.load_metricx`, which negates it.
    """

    def __init__(self, config: MT5Config):
        super().__init__(config)
        self.model_dim = config.d_model

        self.shared = nn.Embedding(config.vocab_size, config.d_model)

        encoder_config = copy.deepcopy(config)
        encoder_config.is_decoder = False
        encoder_config.use_cache = False
        encoder_config.is_encoder_decoder = False
        self.encoder = MT5Stack(encoder_config, self.shared)

        decoder_config = copy.deepcopy(config)
        decoder_config.is_decoder = True
        decoder_config.is_encoder_decoder = False
        decoder_config.num_layers = config.num_decoder_layers
        self.decoder = MT5Stack(decoder_config, self.shared)

        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        self.post_init()

        self.model_parallel = False
        self.device_map = None

    def forward(
        self,
        input_ids: torch.LongTensor | None = None,
        attention_mask: torch.FloatTensor | None = None,
        decoder_attention_mask: torch.BoolTensor | None = None,
        head_mask: torch.FloatTensor | None = None,
        decoder_head_mask: torch.FloatTensor | None = None,
        cross_attn_head_mask: torch.Tensor | None = None,
        encoder_outputs: tuple[tuple[torch.Tensor]] | None = None,
        inputs_embeds: torch.FloatTensor | None = None,
        decoder_inputs_embeds: torch.FloatTensor | None = None,
        labels: torch.FloatTensor | None = None,
        output_attentions: bool | None = None,
        output_hidden_states: bool | None = None,
        return_dict: bool | None = None,
        **kwargs,
    ) -> tuple[torch.FloatTensor] | MT5ForRegressionOutput:
        return_dict = return_dict if return_dict is not None else True

        if encoder_outputs is None:
            encoder_outputs = self.encoder(
                input_ids=input_ids,
                attention_mask=attention_mask,
                inputs_embeds=inputs_embeds,
                head_mask=head_mask,
                output_attentions=output_attentions,
                output_hidden_states=output_hidden_states,
                return_dict=return_dict,
            )
        elif return_dict and not isinstance(encoder_outputs, BaseModelOutput):
            encoder_outputs = BaseModelOutput(
                last_hidden_state=encoder_outputs[0],
                hidden_states=encoder_outputs[1] if len(encoder_outputs) > 1 else None,
                attentions=encoder_outputs[2] if len(encoder_outputs) > 2 else None,
            )

        hidden_states = encoder_outputs[0]

        # One step of dummy decoder input. MetricX reads its score off decoder
        # position 0, so a single BOS-equivalent step is the whole decode.
        batch_size = hidden_states.size(0)
        decoder_input_ids = torch.zeros(
            (batch_size, 1), dtype=torch.long, device=hidden_states.device
        )

        decoder_outputs = self.decoder(
            input_ids=decoder_input_ids,
            attention_mask=decoder_attention_mask,
            inputs_embeds=decoder_inputs_embeds,
            encoder_hidden_states=hidden_states,
            encoder_attention_mask=attention_mask,
            head_mask=decoder_head_mask,
            cross_attn_head_mask=cross_attn_head_mask,
            use_cache=False,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        sequence_output = decoder_outputs[0]

        if self.config.tie_word_embeddings:
            # Rescale output before projecting on vocab. See
            # https://github.com/tensorflow/mesh/blob/fa19d69/mesh_tensorflow/transformer/transformer.py#L586
            sequence_output = sequence_output * (self.model_dim**-0.5)

        lm_logits = self.lm_head(sequence_output)

        predictions = lm_logits[:, 0, _SCORE_TOKEN_ID]
        predictions = torch.clamp(predictions, METRICX_SCORE_MIN, METRICX_SCORE_MAX)

        loss = None
        if labels is not None:
            loss_fct = nn.MSELoss()
            labels = labels.to(predictions.device)
            loss = loss_fct(predictions.view(-1), labels.view(-1))

        return MT5ForRegressionOutput(loss=loss, predictions=predictions)
