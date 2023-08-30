# 🧠 Geniusrise
# Copyright (C) 2023  geniusrise.ai
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import tempfile

import numpy as np
import pytest
from datasets import Dataset
from huggingface.translation import HuggingFaceTranslationFineTuner
from geniusrise.core import BatchInput, BatchOutput, InMemoryState
from transformers import EvalPrediction, MarianMTModel, MarianTokenizer


def create_synthetic_data(size: int, temp_dir: str):
    # Generate synthetic data
    data = {
        "translation": [
            {
                "en": f"This is a synthetic text example {i}",
                "fr": f"C'est un exemple de texte synthétique {i}",
            }
            for i in range(size)
        ],
    }

    # Create a Hugging Face Dataset object from the data
    dataset = Dataset.from_dict(data)

    # Save the dataset to disk
    dataset.save_to_disk(os.path.join(temp_dir, "train"))
    dataset.save_to_disk(os.path.join(temp_dir, "eval"))


@pytest.fixture
def translation_bolt():
    model = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-en-fr")
    tokenizer = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-fr")

    # Use temporary directories for input and output
    input_dir = tempfile.mkdtemp()
    output_dir = tempfile.mkdtemp()

    # Create synthetic data
    create_synthetic_data(100, input_dir)

    input = BatchInput(input_dir, "geniusrise-test-bucket", "test-🤗-input")
    output = BatchOutput(output_dir, "geniusrise-test-bucket", "test-🤗-output")
    state = InMemoryState()

    return HuggingFaceTranslationFineTuner(
        model=model,
        tokenizer=tokenizer,
        input=input,
        output=output,
        state=state,
        eval=True,
    )


def test_translation_bolt_init(translation_bolt):
    assert translation_bolt.model is not None
    assert translation_bolt.tokenizer is not None
    assert translation_bolt.input is not None
    assert translation_bolt.output is not None
    assert translation_bolt.state is not None


def test_load_dataset(translation_bolt):
    train_dataset = translation_bolt.load_dataset(translation_bolt.input.get() + "/train")
    assert train_dataset is not None

    eval_dataset = translation_bolt.load_dataset(translation_bolt.input.get() + "/eval")
    assert eval_dataset is not None


def test_translation_bolt_compute_metrics(translation_bolt):
    # Mocking an EvalPrediction object
    logits = np.array([[0.6, 0.4], [0.4, 0.6]])
    labels = np.array([0, 1])
    eval_pred = EvalPrediction(predictions=logits, label_ids=labels)

    metrics = translation_bolt.compute_metrics(eval_pred)

    assert "accuracy" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1" in metrics


def test_translation_bolt_create_optimizer_and_scheduler(translation_bolt):
    optimizer, scheduler = translation_bolt.create_optimizer_and_scheduler(10)
    assert optimizer is not None
    assert scheduler is not None


def test_translation_bolt_fine_tune(translation_bolt):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Fine-tuning with minimum epochs and batch size for speed
        translation_bolt.fine_tune(output_dir=tmpdir, num_train_epochs=1, per_device_train_batch_size=1)

        # Check that model files are created in the output directory
        assert os.path.isfile(os.path.join(tmpdir, "pytorch_model.bin"))
        assert os.path.isfile(os.path.join(tmpdir, "config.json"))
        assert os.path.isfile(os.path.join(tmpdir, "training_args.bin"))
