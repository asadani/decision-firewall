# Windows and low-memory model setup

Target: Python 3.12, GTX 1650 4 GB, approximately 8 GB system RAM. The initial environment's system `python` was 3.9; explicitly use a 3.12 interpreter. This workstation also has the bundled interpreter at `C:\Users\anuj_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.

Create `.venv` with that interpreter if `py -3.12` is unavailable. Install core/dev locks and the editable package as shown in the README. Do not put credentials or model weights in Git.

## GPU

In the activated Python 3.12 environment, after core installation:

```powershell
python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r requirements-model.lock
firewall assess "Please refund the duplicate charge" --provider laya
```

Install PyTorch 2.6.0 from the CUDA 12.4 wheel index before the model lock. Only one checkpoint is loaded. The adapter disables AMP and compilation, runs FP32, serializes inference, and uses a 256-token state cap with 512-token model sequences. It reports actual device/fallback and refuses to silently truncate long evidence.

## CPU

For a CPU-only machine, install `torch==2.6.0` from `https://download.pytorch.org/whl/cpu`, then the model lock. Pass `--device cpu`. CPU execution may be slower and still needs enough RAM for the model. No performance number is promised before measurement.

## Reproducibility

Laya SDK 0.3.20 is pinned. Its published `load` helper lacks a revision parameter, so the adapter first calls Hugging Face snapshot download with the pinned commit, then loads the local snapshot. Only required checkpoint files are downloaded. TensorFlow probing is disabled with `USE_TF=0`.

The model card warns that confidence is uncalibrated. The framework records that status and does not use confidence to bypass hard controls. No fine-tuning or calibration fitting is performed.

