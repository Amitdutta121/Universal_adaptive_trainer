"""Download Docling's PDF models once into ``models/docling`` (gitignored).

    .\\.venv\\Scripts\\python.exe -m scripts.download_docling_models           # skip if present
    .\\.venv\\Scripts\\python.exe -m scripts.download_docling_models --force   # download again

Only what book import runs is fetched: the ``layout`` (docling-layout-heron) and
``tableformer`` models (``app.ingestion.parsing._docling_converter`` turns OCR off and table
structure on), and the chunker's tokenizer (``sentence-transformers/all-MiniLM-L6-v2``). Once
they are there, parsing loads them from ``Settings.docling_artifacts_path`` and never asks the
Hugging Face Hub, so a missing network or a bad stored HF token cannot fail an
import. The models are public, so the download is anonymous: a stored token is ignored here,
because an invalid one makes the Hub answer 401 even for public models.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="download even if present")
    args = parser.parse_args(argv)

    # Before huggingface_hub is imported: send no token, stored or in the environment.
    os.environ.pop("HF_TOKEN", None)
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

    from docling.utils.model_downloader import download_models
    from huggingface_hub import snapshot_download

    from app.config import get_settings
    from app.ingestion.parsing import _CHUNKER_TOKENIZER

    target = get_settings().docling_artifacts_path
    tokenizer_dir = target / _CHUNKER_TOKENIZER.replace("/", "--")
    if tokenizer_dir.is_dir() and any(target.glob("docling-project--*")) and not args.force:
        print(f"Docling models already in {target}; pass --force to download again.")
        return 0
    download_models(
        output_dir=target,
        force=args.force,
        progress=True,
        with_layout=True,
        with_tableformer=True,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=False,
    )
    # The tokenizer only: the chunker counts tokens, it never runs the model's weights.
    snapshot_download(
        repo_id=_CHUNKER_TOKENIZER,
        local_dir=tokenizer_dir,
        allow_patterns=["*.json", "*.txt"],
        force_download=args.force,
        token=False,
    )
    print(f"Docling models are in {target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
