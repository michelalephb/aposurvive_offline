# Aposurvive Offline

Offline AI survival assistant. iPhone first, no network needed once installed.

**Design rule:** the model never answers from memory. Every answer is built from passages retrieved out of public domain military survival manuals on the phone, and cites them. If no passage covers the question, it says `NOT IN LIBRARY`. When the model can't run (low battery, phone too hot, not downloaded), the app still serves the matching passages and static field cards verbatim.

```
manuals (PDF) ─▶ pipeline ─▶ library.sqlite (FTS5 BM25) ─┬─▶ iOS app (retrieval + Qwen3 4B via MLX)
                                                       └─▶ DeepSeek teacher ─▶ dataset ─▶ LoRA (mlx-lm) ─▶ fused model ─▶ iOS app
```

## Status (v0.1)

| Part | State |
|---|---|
| Corpus pipeline: fetch, extract, chunk, build library | Done, tested on generated PDFs. Real manuals not yet run. |
| Dataset generator (DeepSeek teacher) and validator with human review gate | Done, tested with a fake teacher. No API calls made yet. |
| LoRA config | Written. Key names unverified against your installed mlx-lm. |
| iOS shell: triage home, sourced answer, field cards, SOS torch, readiness gate | Written. **Not compiled yet** (no Xcode where it was written). |
| WikiMed medical corpus | Deferred to v02 (ZIM parsing and license check). |
| Embedding search | Deferred to v02. v01 uses BM25 so phone and training share one retriever with no extra model. |

## Quickstart (Apple Silicon Mac)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                    # 18 tests

# 1. Library
python -m pipeline.fetch               # downloads ATP 3-50.21 and FM 21-76-1 into corpus/raw/
python -m pipeline.extract             # per page text into corpus/work/
python -m pipeline.build_library       # build/library.sqlite + manifest
python -m pipeline.search "deep cut on my arm, bleeding won't stop"   # sanity check

# 2. App
brew install xcodegen
scripts/sync_ios_resources.sh
cd ios && xcodegen generate && open AposurviveOffline.xcodeproj
# set your signing team, enable "Increased Memory Limit" on the App ID, run on an iPhone 15 Pro or newer
# first launch: tap "Download model" on wifi (about 2.3 GB). After that it works in airplane mode.

# 3. Dataset (spends DeepSeek credit, so it needs --yes)
export DEEPSEEK_API_KEY=...            # keep out of the repo
python -m training.gen_dataset --seeds 40          # dry run, prints call count
python -m training.gen_dataset --seeds 40 --yes
python -m training.validate_dataset training/out/aposurvive_dataset_raw_<date>_v01.jsonl
# review training/review/review_queue.csv, add approved ids to training/review/approved_ids.txt, rerun validate

# 4. Fine tune and fuse
pip install mlx-lm
mlx_lm.lora --config training/lora_config.yaml
mlx_lm.fuse --model mlx-community/Qwen3-4B-Instruct-2507-4bit --adapter-path adapters --save-path build/aposurvive_qwen3_4b_fused
# upload the fused folder to your own Hugging Face repo, set ModelService.modelID to it
```

## Layout

| Path | What |
|---|---|
| `corpus/sources.yaml` | Source manuals with URLs and license notes |
| `corpus/cards.yaml` | Field card definitions. Text is always copied verbatim from the manuals, never written |
| `pipeline/` | fetch, extract, chunk, build_library, search (BM25 query builder shared with Swift) |
| `training/prompts/runtime_system.txt` | The one system prompt, used in training and bundled in the app |
| `training/gen_dataset.py` | Teacher pipeline: questions from a seed passage, same retrieval as the phone, ideal reply |
| `training/validate_dataset.py` | Format checks, source reference checks, dedupe, review gate, train/valid split |
| `ios/` | XcodeGen spec and SwiftUI app |
| `tests/` | Pipeline, training and Swift/Python prompt parity tests |

## Rules that keep it safe

1. Phone and training build the prompt identically (`tests/test_swift_parity.py` fails if they drift).
2. Answers with medical, plant or water content stay out of training until a person approves them.
3. Field cards show an "Unreviewed" badge until a person pins their pages and sets `reviewed: true`.
4. Builds never overwrite: old libraries move to `build/_archive/`, datasets get a new `_vNN` file.
5. `Offline OK` only shows when the library checksum, the prompt and the model files are all verified on the phone.

## Known risks

- `mlx-swift-lm` 2.30.3 API calls in `ModelService.swift` (`ModelConfiguration(directory:)`, `ChatSession(instructions:generateParameters:)`, `GenerateParameters(maxTokens:temperature:)`) were written from docs, not compiled. Fix any mismatch at first build.
- The model cache path assumes the default Hugging Face layout `Documents/huggingface/models/<repo>`. Check it on the first device run.
- PDF page numbers are PDF indexes, not printed folios. The source sheet always shows the passage text so a reader can check.
- Increased memory limit entitlement: one developer reported it worked in local builds and not in their App Store build. Test on TestFlight early.
