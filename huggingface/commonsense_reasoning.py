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
import os
import sqlite3
import xml.etree.ElementTree as ET
from typing import Any, Dict, Union

import pandas as pd
import pyarrow.parquet as pq
import yaml  # type: ignore
from datasets import Dataset, DatasetDict, load_from_disk
from pyarrow import feather
from transformers import DataCollatorWithPadding

from .base import HuggingFaceFineTuner


class HuggingFaceCommonsenseReasoningFineTuner(HuggingFaceFineTuner):
    r"""
    A bolt for fine-tuning Hugging Face models on commonsense reasoning tasks.

    Args:
        model: The pre-trained model to fine-tune.
        tokenizer: The tokenizer associated with the model.
        input (BatchInput): The batch input data.
        output (OutputConfig): The output data.
        state (State): The state manager.
    """

    def load_dataset(self, dataset_path: str, **kwargs: Any) -> Union[Dataset, DatasetDict, None]:
        r"""
        Load a commonsense reasoning dataset from a directory.

        ```
        The directory can contain any of the following file types:
        - Dataset files saved by the Hugging Face datasets library.
        - JSONL files: Each line is a JSON object representing an example. Structure:
            {
                "premise": "The premise text",
                "hypothesis": "The hypothesis text",
                "label": 0 or 1 or 2
            }
        - CSV files: Should contain 'premise', 'hypothesis', and 'label' columns.
        - Parquet files: Should contain 'premise', 'hypothesis', and 'label' columns.
        - JSON files: Should be an array of objects with 'premise', 'hypothesis', and 'label' keys.
        - XML files: Each 'record' element should contain 'premise', 'hypothesis', and 'label' child elements.
        - YAML/YML files: Each document should be a dictionary with 'premise', 'hypothesis', and 'label' keys.
        - TSV files: Should contain 'premise', 'hypothesis', and 'label' columns separated by tabs.
        - Excel files (.xls, .xlsx): Should contain 'premise', 'hypothesis', and 'label' columns.
        - Feather files: Should contain 'premise', 'hypothesis', and 'label' columns.
        ```

        Args:
            dataset_path (str): The path to the dataset directory.
            **kwargs: Additional keyword arguments.

        Returns:
            Dataset: The loaded dataset.

        Raises:
            Exception: If there was an error loading the dataset.
        """
        try:
            if os.path.isfile(os.path.join(dataset_path, "dataset_info.json")):
                dataset = load_from_disk(dataset_path)
                return dataset.map(
                    self.prepare_train_features,
                    batched=True,
                    remove_columns=dataset.column_names,
                )
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
                            data.extend(json.load(f))
                    elif filename.endswith(".xml"):
                        tree = ET.parse(filepath)
                        root = tree.getroot()
                        for record in root.findall("record"):
                            example = {
                                "premise": record.find("premise").text,  # type: ignore
                                "hypothesis": record.find("hypothesis").text,  # type: ignore
                                "label": int(record.find("label").text),  # type: ignore
                            }
                            data.append(example)
                    elif filename.endswith((".yaml", ".yml")):
                        with open(filepath, "r") as f:
                            data.extend(yaml.safe_load(f))
                    elif filename.endswith(".tsv"):
                        df = pd.read_csv(filepath, sep="\t")
                        data.extend(df.to_dict("records"))
                    elif filename.endswith((".xls", ".xlsx")):
                        df = pd.read_excel(filepath)
                        data.extend(df.to_dict("records"))
                    elif filename.endswith(".db"):
                        conn = sqlite3.connect(filepath)
                        query = "SELECT premise, hypothesis, label FROM dataset_table;"
                        df = pd.read_sql_query(query, conn)
                        data.extend(df.to_dict("records"))
                    elif filename.endswith(".feather"):
                        df = feather.read_feather(filepath)
                        data.extend(df.to_dict("records"))

                dataset = Dataset.from_pandas(pd.DataFrame(data))
                return dataset.map(
                    self.prepare_train_features,
                    batched=True,
                    remove_columns=dataset.column_names,
                )

        except Exception as e:
            print(f"Error loading dataset: {e}")
            raise

    def prepare_train_features(self, examples: Dict) -> Dict:
        """
        Tokenize the examples and prepare the features for training.

        Args:
            examples (dict): A dictionary of examples.

        Returns:
            dict: The processed features.
        """
        try:
            if not self.tokenizer:
                raise Exception("Tokenizer not initialized")

            # Tokenize the examples
            tokenized_inputs = self.tokenizer(
                examples["premise"],
                examples["hypothesis"],
                truncation=True,
                padding=False,
            )

            # Prepare the labels
            tokenized_inputs["labels"] = examples["label"]

            return tokenized_inputs
        except Exception as e:
            print(f"Error preparing train features: {e}")
            raise

    def data_collator(self, examples: Dict) -> Dict:
        """
        Customize the data collator.

        Args:
            examples: The examples to collate.

        Returns:
            dict: The collated data.
        """
        try:
            return DataCollatorWithPadding(self.tokenizer)(examples)

        except Exception as e:
            print(f"Error in data collation: {e}")
            raise
