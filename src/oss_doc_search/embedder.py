import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from .config import MODELS_DIR

MODEL_REPO = "onnx-models/all-MiniLM-L6-v2-onnx"
TOKENIZER_REPO = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class Embedder:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        model_path = MODELS_DIR / "all-MiniLM-L6-v2" / "model.onnx"
        tokenizer_path = MODELS_DIR / "all-MiniLM-L6-v2-tokenizer" / "tokenizer.json"

        if not model_path.exists():
            hf_hub_download(
                repo_id=MODEL_REPO,
                filename="model.onnx",
                local_dir=MODELS_DIR / "all-MiniLM-L6-v2",
            )

        if not tokenizer_path.exists():
            hf_hub_download(
                repo_id=TOKENIZER_REPO,
                filename="tokenizer.json",
                local_dir=MODELS_DIR / "all-MiniLM-L6-v2-tokenizer",
            )

        self.model_path = model_path
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.session = ort.InferenceSession(str(self.model_path))

    def embed(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        max_len = input_ids.shape[1]
        if max_len < 128:
            pad_len = 128 - max_len
            input_ids = np.pad(input_ids, ((0, 0), (0, pad_len)), constant_values=0)
            attention_mask = np.pad(
                attention_mask, ((0, 0), (0, pad_len)), constant_values=0
            )
            token_type_ids = np.pad(
                token_type_ids, ((0, 0), (0, pad_len)), constant_values=0
            )

        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        output_array = outputs[0]
        if not isinstance(output_array, np.ndarray):
            output_array = np.array(output_array)
        mask = np.expand_dims(attention_mask, -1).repeat(output_array.shape[-1], -1)
        embeddings = (output_array * mask).sum(1) / np.clip(mask.sum(1), 1e-9, None)
        return embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)


def get_embedder() -> Embedder:
    return Embedder()
