# Ring Zero 
**Predictive Memory Orchestration for Hybrid App + AI Workloads**

> Modern devices are running browsers, messaging apps, and on-device LLMs in the same memory budget. The OS treats them identically. Ring Zero doesn't.

Traditional memory managers are reactive — they evict after pressure builds. Ring Zero is predictive: it anticipates which apps will be launched next, scores them by launch cost and memory footprint, and prewarms them before the user ever taps. When memory pressure rises (via Linux PSI telemetry), it throttles aggression automatically to avoid making things worse.

**At 200 MB budget: 60% warm launch rate vs LRU's 50% — a 20% relative improvement, with 16% lower average latency.**

---

## How It Works

Ring Zero wraps a standard memory backend with a three-stage orchestration loop:

```
┌──────────────────────────────────────────────────────────────────┐
│                         Ring Zero                                │
│                                                                  │
│  ┌────────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │  SASRec    │──▶│   Scoring    │──▶│   Policy Manager       │  │
│  │  Predictor │   │   Engine     │   │  (Prewarm / Evict)     │  │
│  └────────────┘   └──────────────┘   └───────────┬────────────┘  │
│       │                  ▲                       │               │
│       │            ┌─────┴──────┐          ┌─────▼──────┐        │
│       │            │  PSI       │          │  Budget    │        │
│       │            │  Monitor   │          │  Manager   │        │
│       │            └────────────┘          └────────────┘        │
│       │                                          │               │
│  ┌────▼──────────────────────────────────────────▼────────┐      │
│  │              Memory Backend                            │      │
│  │   MockBackend (Simulation)  |  LinuxBackend (cgroup v2)│      │
│  └────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

**Stage 1 — Predict**: A SASRec transformer (93.57% Hit@3 on LSApp dataset) predicts the top-5 apps the user will open next, given their session history, hour of day, and day of week.

**Stage 2 — Score**: Each prediction is scored as `P(app) × launch_cost / memory_footprint`, producing a priority signal that accounts for both likelihood and economic value of prewarming.

**Stage 3 — Act with PSI awareness**: The Policy Manager prewarms high-score apps and evicts low-score ones. When `/proc/pressure/memory` reports elevated stall time, it throttles automatically:
- Top-K candidates: 5 → 2 → 1
- Effective budget: ×0.8 → ×0.6 → ×0.4
- Score multiplier: 0.9× applied to dampen aggression

This prevents the classic failure mode where predictive prewarming amplifies pressure instead of relieving it.

---

## Results

Benchmark sweep across constrained budgets (1000 events, simulation backend):

| Policy | Budget | Warm Rate | Avg Latency | Page Faults | Prewarms |
|:---|:---:|:---:|:---:|:---:|:---:|
| LRU (baseline) | 400 MB | 86.0% | 216.6 ms | 577K | — |
| Prediction + Cost | 400 MB | 90.0% | 192.2 ms | 847K | 14 |
| **Full Ring Zero** | **400 MB** | **90.0%** | **192.2 ms** | **720K** | **7** |
| LRU (baseline) | 300 MB | 80.0% | 263.0 ms | 768K | — |
| Prediction + Cost | 300 MB | 84.0% | 241.1 ms | 1,143K | 17 |
| **Full Ring Zero** | **300 MB** | **83.0%** | **242.6 ms** | **1,143K** | **16** |
| LRU (baseline) | 200 MB | 50.0% | 557.2 ms | 2,425K | — |
| Prediction + Cost | 200 MB | 61.0% | 468.9 ms | 3,278K | 44 |
| **Full Ring Zero** | **200 MB** | **60.0%** | **470.4 ms** | **3,226K** | **37** |
| LRU (baseline) | 100 MB | 2.0% | 1002.1 ms | 3,867K | — |
| Prediction + Cost | 100 MB | 5.0% | 997.7 ms | 4,206K | 42 |
| **Full Ring Zero** | **100 MB** | **3.0%** | **1000.6 ms** | **3,989K** | **15** |

**Key findings:**

- Ring Zero beats LRU at every budget level. The gap is largest at moderate pressure (200–400 MB), where prediction actually has room to help.
- PSI throttling earns its place: at 400 MB, Full Ring Zero matches Prediction + Cost on warm rate (90%) while using **50% fewer prewarm actions** (7 vs 14) and generating **15% fewer page faults** (720K vs 847K). It prefers not to prewarm over prewarming into pressure.
- At extreme starvation (100 MB), all policies converge to near-cold behavior. This is expected and correct — there is no memory to prewarm into. Graceful degradation, not thrashing.

---

## Components

| Component | Path | Description |
|:---|:---|:---|
| SASRec Predictor | `predictor/sasrec.py` | Transformer-based next-app prediction (93.57% Hit@3) |
| Scoring Engine | `orchestrator/scoring_engine.py` | `P(app) × launch_cost / memory_footprint` with PSI modifier |
| Policy Manager | `orchestrator/policy_manager.py` | Prewarm/evict/keep decisions with PSI-aware Top-K throttling |
| Budget Manager | `orchestrator/budget_manager.py` | Memory allocation tracking, budget enforcement, LRU eviction |
| PSI Monitor | `simulator/psi_monitor.py` | Reads `/proc/pressure/memory` for real-time stall telemetry |
| Linux Backend | `memory/linux_backend.py` | cgroup v2 + anonymous mmap allocator (requires root) |
| Mock Backend | `simulator/memory_simulator.py` | Simulation backend — no root, no cgroups required |
| Workload Generator | `simulator/workload_generator.py` | Replays app usage sequences from the LSApp dataset |

---

## Orchestration Policies

Three modes are benchmarked:

**LRU** — Reactive eviction only. No prediction. This is the OS default behavior and serves as the baseline.

**Prediction + Cost** — SASRec predictions weighted by launch cost and memory footprint drive prewarm/evict decisions. No pressure awareness — it will prewarm regardless of system state.

**Full Ring Zero** — Adds PSI-aware throttling on top of Prediction + Cost. Backs off automatically under memory pressure. This is the target policy.

---

## Getting Started

### Prerequisites

```
Python 3.8+
PyTorch
PyYAML
matplotlib
```

### Dataset

Ring Zero uses the [LSApp dataset](https://github.com/nicholasRenworworthy/lsapp) for app launch sequences. Preprocessed data lives in `datasets/`:
- `train_seqs.json` — Training sequences
- `test_seqs.json` — Test sequences
- `app2id.json` — App name → integer ID mapping

### Train the Predictor

```bash
python predictor/train.py
```

### Run Benchmarks

Simulation (no root required):
```bash
python benchmark_linux.py --limit 1000 --simulate
```

Linux with real cgroup v2 (requires root):
```bash
sudo python benchmark_linux.py --limit 1000
```

Full benchmark suite with plots:
```bash
python benchmarking/benchmark_runner.py --limit 1000
```

Ablation studies:
```bash
python benchmarking/ablation_runner.py --limit 1000
```

---

## Project Structure

```
ring_zero/
├── predictor/              # SASRec model, training, evaluation
│   ├── sasrec.py           # Transformer model definition
│   ├── train.py            # Training script
│   ├── evaluate.py         # Hit@K, NDCG metrics
│   ├── baselines.py        # MFU and Last-App baselines
│   └── sasrec_model.pt     # Trained weights
├── orchestrator/           # Core orchestration logic
│   ├── policy_manager.py   # Prewarm / evict / keep decisions
│   ├── scoring_engine.py   # Multi-signal scoring function
│   ├── budget_manager.py   # Memory tracking + LRU
│   └── constants.py        # PSI thresholds
├── simulator/              # Simulation support
│   ├── memory_simulator.py # Mock memory backend
│   ├── psi_monitor.py      # /proc/pressure/memory reader
│   ├── kernel_metrics.py   # cgroup memory.stat reader
│   ├── workload_generator.py
│   └── cleanup.py          # Signal + cgroup cleanup handlers
├── memory/                 # Backend abstraction
│   ├── backend.py          # Abstract interface
│   ├── linux_backend.py    # Real Linux cgroup v2 backend
│   └── mock_backend.py     # Lightweight mock
├── config/
│   ├── apps.yaml           # Per-app memory and latency profiles
│   ├── predictor.yaml      # Model hyperparameters
│   └── simulator.yaml      # Simulation settings
├── datasets/               # Preprocessed LSApp data
├── benchmarking/           # Runners and results
│   ├── benchmark_runner.py
│   ├── ablation_runner.py
│   └── plots/
└── benchmark_linux.py      # Primary benchmark entry point
```

---

## Limitations

- The Linux backend targets cgroup v2 on standard desktop/server kernels. Android deployment (the original motivation) requires kernel-level access not available via Knox — the production demo runs as a Linux cgroup simulation.
- Benchmarks use the LSApp dataset, which reflects general smartphone usage patterns. Results on AI-heavy workloads (concurrent LLM inference + apps) are not yet validated.
- The SASRec predictor is trained on sequences of up to 20 apps. Very long or highly irregular sessions may see lower Hit@3.

---

## License

Research prototype. No license specified.
