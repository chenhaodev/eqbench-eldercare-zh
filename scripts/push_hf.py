#!/usr/bin/env python3
"""推送数据集到 HuggingFace（chenhaodev/eqbench-eldercare-zh）。

做三件事：建 repo（存在则跳过）、上传数据与文档、README 前置 dataset_card.yaml
为 YAML frontmatter（HF Dataset Viewer 需要；GitHub 版 README 保持无 frontmatter）。
"""
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
REPO_ID = "chenhaodev/eqbench-eldercare-zh"

UPLOAD = [
    "data", "eval", "reference", "scripts",
    "drafts/roster.yaml", "drafts/WRITING_SPEC.md",
    "LICENSE", "LITE_PLAN.md", "HARNESS_PLAN.md", ".env.example",
]


def main():
    api = HfApi()
    print("user:", api.whoami()["name"])
    api.create_repo(REPO_ID, repo_type="dataset", exist_ok=True)

    card = (ROOT / "dataset_card.yaml").read_text(encoding="utf-8")
    card_body = "\n".join(l for l in card.splitlines() if not l.startswith("#"))
    readme_hf = f"---\n{card_body.strip()}\n---\n\n" + (ROOT / "README.md").read_text(encoding="utf-8")
    api.upload_file(path_or_fileobj=readme_hf.encode(), path_in_repo="README.md",
                    repo_id=REPO_ID, repo_type="dataset")

    for item in UPLOAD:
        p = ROOT / item
        if p.is_dir():
            api.upload_folder(folder_path=str(p), path_in_repo=item,
                              repo_id=REPO_ID, repo_type="dataset",
                              ignore_patterns=["__pycache__/*", "*.pyc"])
        elif p.exists():
            api.upload_file(path_or_fileobj=str(p), path_in_repo=item,
                            repo_id=REPO_ID, repo_type="dataset")
    print(f"done → https://huggingface.co/datasets/{REPO_ID}")


if __name__ == "__main__":
    main()
