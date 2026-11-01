"""Real numbers for the 'Fine-tuning' lesson. A small model (polynomial features + linear head)
is pretrained on plenty of data from task A, then adapted to task B, which has only 12 examples.
Compares, per epoch of gradient descent on task B's 12 examples:
  scratch  - start from random weights
  finetune - start from the pretrained weights
  head     - start from pretrained weights, update only the last 3 weights (a 'frozen body')
Validation loss is measured on 200 held-out points from task B.
Writes JSON for assets/lesson-finetuning.js."""
import json, sys
import numpy as np

rng = np.random.default_rng(7)
DEG = 9
def feats(x):
    return np.stack([x ** k for k in range(DEG + 1)], axis=1)
task_a = lambda x: np.sin(3 * x)
task_b = lambda x: np.sin(3 * x) + 0.4 * x + 0.2          # related, shifted task

# pretraining on task A: lots of data, closed-form least squares (ridge)
xa = rng.uniform(-1, 1, 400); ya = task_a(xa) + rng.normal(0, 0.05, 400)
Xa = feats(xa)
w_pre = np.linalg.solve(Xa.T @ Xa + 1e-3 * np.eye(DEG + 1), Xa.T @ ya)

# task B: 12 noisy training points, 200 validation points
xb = np.sort(rng.uniform(-1, 1, 12)); yb = task_b(xb) + rng.normal(0, 0.08, 12)
xv = np.linspace(-1, 1, 200); yv = task_b(xv)
Xb, Xv = feats(xb), feats(xv)
mse = lambda w, X, y: float(np.mean((X @ w - y) ** 2))

def run(w0, lr, epochs, mask=None):
    w = w0.copy(); tr, va = [], []
    for _ in range(epochs + 1):
        tr.append(mse(w, Xb, yb)); va.append(mse(w, Xv, yv))
        g = 2 * Xb.T @ (Xb @ w - yb) / len(yb)
        if mask is not None: g = g * mask
        w -= lr * g
    return tr, va, w

EPOCHS = 300
w_rand = rng.normal(0, 0.5, DEG + 1)
head = np.zeros(DEG + 1); head[:3] = 1        # only the 3 lowest-order weights update
out = {"epochs": EPOCHS, "runs": {}}
for lr in [0.05, 0.2, 0.6]:
    for name, w0, mask in [("scratch", w_rand, None), ("finetune", w_pre, None), ("head", w_pre, head)]:
        tr, va, w = run(w0, lr, EPOCHS, mask)
        out["runs"][f"{name}@{lr}"] = {"train": [round(v, 4) for v in tr[::5]], "val": [round(v, 4) for v in va[::5]],
                                      "best_val": round(min(va), 4), "best_epoch": int(np.argmin(va)), "final_val": round(va[-1], 4)}
out["every"] = 5
out["pretrained_val_on_b"] = round(mse(w_pre, Xv, yv), 4)
# LoRA parameter count for one 4096x4096 weight matrix
d = k = 4096
out["lora"] = {"d": d, "k": k, "full": d * k, "r8": 8 * (d + k), "share_r8": round(8 * (d + k) / (d * k) * 100, 2)}
json.dump(out, open(sys.argv[1], "w"), indent=1)
for key, r in out["runs"].items():
    print(f"{key:14s} start_val={r['val'][0]:.3f} best_val={r['best_val']:.4f} @ {r['best_epoch']:3d} final_val={r['final_val']:.4f} final_train={r['train'][-1]:.4f}")
print("pretrained model on task B before tuning:", out["pretrained_val_on_b"])
print(out["lora"])
