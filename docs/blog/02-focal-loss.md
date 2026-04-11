# Blog Post 2: Focal Loss for Fraud Detection

## Metadata

- **Title:** "Why Focal Loss Beat Class Weights for 0.15% Fraud Detection"
- **Subtitle:** "At 665 legitimate transactions per fraud, scale_pos_weight uniformly upweights all positives. Focal loss does something smarter."
- **Target length:** 1,400--1,600 words (6-7 minute read)
- **Tags:** machine-learning, deep-learning, class-imbalance, lightgbm, fraud-detection
- **Publish:** Week 2

## Hook

"At a 0.15% fraud rate, there are 665 legitimate transactions for every fraudulent one. I spent three experiments tuning `scale_pos_weight` and capped out at AUPRC=0.49. Switching to focal loss -- a loss function from computer vision -- jumped it to 0.58. Here's why."

## Outline

### 1. The class imbalance problem (200 words)
- 0.15% fraud rate in 13M transactions
- Why accuracy is meaningless (99.85% by predicting "no fraud")
- AUPRC as the right metric (baseline = 0.0015)
- Standard solution: `scale_pos_weight` in LightGBM

### 2. Why scale_pos_weight plateaus (300 words)
- What it does: multiplies the loss for positive samples by a constant (e.g., 10x)
- The problem: an "easy" fraud (obvious pattern like $10K online at 3AM) gets the same 10x weight as a "hard" fraud (subtle pattern that looks legitimate)
- The gradient is dominated by easy examples -- both easy positives (upweighted but already correct) and easy negatives (vast majority)
- Result: AUPRC=0.49 after tuning weight from 1 to 100

### 3. Focal loss: the intuition (400 words)
- Originally from Lin et al. (2017) for object detection -- same class imbalance problem (background pixels >> object pixels)
- Core idea: multiply the loss by `(1 - pt)^gamma` where pt is the model's confidence
- When the model is confident and correct (pt → 1): weight → 0 (ignore this example)
- When the model is wrong (pt → 0): weight → 1 (full gradient)
- **Diagram placeholder: Focal Loss vs Class Weights comparison** (Excalidraw Diagram 7)
- gamma=2.0 is the sweet spot: aggressive enough to down-weight easy examples, not so aggressive that the model ignores everything

### 4. Implementation in LightGBM (300 words)
- LightGBM accepts custom objectives: return (gradient, hessian)
- Code snippet: the `focal_loss_objective` function (8 lines)
  - Reference: `src/models/train_model.py` (focal loss functions)
- Important gotcha: focal loss returns raw logits, not probabilities. Must apply sigmoid at serving time.
- alpha=0.25 controls the relative weight of positive vs negative class (separate from gamma)

### 5. Results: both precision AND recall improved (200 words)
- Before (scale_pos_weight): AUPRC=0.49, Precision=0.53, Recall=0.50
- After (focal loss): AUPRC=0.58, Precision=0.58, Recall=0.57
- "Both precision and recall improving simultaneously is rare. It usually means the model is learning better-calibrated scores, not just shifting the threshold."
- Feature importance became more evenly distributed -- "healthier" model
- Top feature still `mcc_te` but now user/demographic features entered top 20

### 6. When to use focal loss vs class weights (150 words)
- Focal loss: when the dataset has extreme imbalance AND varied difficulty among positive examples
- Class weights: simpler, fine when positive examples are uniformly difficult
- Focal loss is under-used in tabular ML -- most practitioners know it from vision but don't think to apply it to gradient boosting

### Closing
- Link to repo (full training code + experiment log)
- Link to Post 1 (leakage) and Post 3 (ceiling analysis) if published

## Diagrams Needed
1. **Focal Loss vs scale_pos_weight** (Excalidraw Diagram 7) -- side-by-side: flat gradient bar vs. curved gradient showing concentration on hard examples
2. **Before/after metrics** -- table or small bar chart showing precision+recall improvements

## Code Snippets to Include
- `focal_loss_objective` and `focal_loss_eval` (from `src/models/train_model.py`)
- Before/after metrics table (from `experiments.md:200-216`)
