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

import json
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from typing import Optional

import pandas as pd
import yaml  # type: ignore
from datasets import Dataset, load_from_disk
from pyarrow import feather
from pyarrow import parquet as pq
from transformers import DataCollatorWithPadding

from .base import HuggingFaceFineTuner


class HuggingFaceClassificationFineTuner(HuggingFaceFineTuner):
    r"""
    A bolt for fine-tuning Hugging Face models for text classification tasks.

    ```
    Args:
        model: The pre-trained model to fine-tune.
        tokenizer: The tokenizer associated with the model.
        input (BatchInput): The batch input data.
        output (OutputConfig): The output data.
        state (State): The state manager.
    ```
    """

    def load_dataset(self, dataset_path: str, **kwargs) -> Optional[Dataset]:
        r"""
        Load a classification dataset from a directory.

        ```
        The directory can contain any of the following file types:
        - Dataset files saved by the Hugging Face datasets library.
        - JSONL files: Each line is a JSON object representing an example. Structure:
            {
                "text": "The text content",
                "label": "The label"
            }
        - XML files: Each 'record' element should contain 'text' and 'label' child elements.
        - YAML files: Each document should be a dictionary with 'text' and 'label' keys.
        - TSV files: Should contain 'text' and 'label' columns separated by tabs.
        - Excel files (.xls, .xlsx): Should contain 'text' and 'label' columns.
        - SQLite files (.db): Should contain a table with 'text' and 'label' columns.
        - Feather files: Should contain 'text' and 'label' columns.
        ```

        Args:
            dataset_path (str): The path to the dataset directory.

        Returns:
            Dataset: The loaded dataset.

        Raises:
            Exception: If there was an error loading the dataset.
        """

        self.data_collator = DataCollatorWithPadding(tokenizer=self.tokenizer)

        self.label_to_id = self.model.config.label2id if self.model and self.model.config.label2id else None  # type: ignore

        def tokenize_function(examples):
            tokenized_data = self.tokenizer(examples["text"], padding="max_length", truncation=True, max_length=512)
            tokenized_data["label"] = [self.label_to_id[label] for label in examples["label"]]
            return tokenized_data

        try:
            logging.info(f"Loading dataset from {dataset_path}")
            if os.path.isfile(os.path.join(dataset_path, "dataset_info.json")):
                # Load dataset saved by Hugging Face datasets library
                return load_from_disk(dataset_path).map(tokenize_function, batched=True)
            else:
                data = []
                for filename in os.listdir(dataset_path):
                    filepath = os.path.join(dataset_path, filename)
                    if filename.endswith(".jsonl"):
                        with open(filepath, "r") as f:
                            for line in f:
                                example = json.loads(line)
                                data.append(example)

                    elif filename.endswith(".csv"):
                        df = pd.read_csv(filepath)
                        data.extend(df.to_dict("records"))

                    elif filename.endswith(".parquet"):
                        df = pq.read_table(filepath).to_pandas()
                        data.extend(df.to_dict("records"))

                    elif filename.endswith(".json"):
                        with open(filepath, "r") as f:
                            json_data = json.load(f)
                            data.extend(json_data)

                    elif filename.endswith(".xml"):
                        tree = ET.parse(filepath)
                        root = tree.getroot()
                        for record in root.findall("record"):
                            text = record.find("text").text  # type: ignore
                            label = record.find("label").text  # type: ignore
                            data.append({"text": text, "label": label})

                    elif filename.endswith(".yaml") or filename.endswith(".yml"):
                        with open(filepath, "r") as f:
                            yaml_data = yaml.safe_load(f)
                            data.extend(yaml_data)

                    elif filename.endswith(".tsv"):
                        df = pd.read_csv(filepath, sep="\t")
                        data.extend(df.to_dict("records"))

                    elif filename.endswith((".xls", ".xlsx")):
                        df = pd.read_excel(filepath)
                        data.extend(df.to_dict("records"))

                    elif filename.endswith(".db"):
                        conn = sqlite3.connect(filepath)
                        query = "SELECT text, label FROM dataset_table;"
                        df = pd.read_sql_query(query, conn)
                        data.extend(df.to_dict("records"))

                    elif filename.endswith(".feather"):
                        df = feather.read_feather(filepath)
                        data.extend(df.to_dict("records"))

                # Create label_to_id mapping and save it in model config
                unique_labels = (example["label"] for example in data)
                self.label_to_id = {label: i for i, label in enumerate(unique_labels)}
                if self.model:
                    if self.model.config.label2id != self.label_to_id:
                        self.log.warning("New labels detected, ignore if fine-tuning")
                    self.model.config.label2id = self.label_to_id
                    self.model.config.id2label = {i: label for label, i in self.label_to_id.items()}

                return Dataset.from_pandas(pd.DataFrame(data)).map(tokenize_function, batched=True)
        except Exception as e:
            logging.error(f"Error occurred when loading dataset from {dataset_path}. Error: {e}")
            raise
