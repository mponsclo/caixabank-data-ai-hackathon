# Blog Post 4: End-to-End Pipeline Overview

## Metadata

- **Title:** "From CSV to Real-Time Fraud Scoring: An End-to-End ML Pipeline on GCP"
- **Subtitle:** "1.2GB of transactions, 60 SQL features, a LightGBM model, a FastAPI endpoint -- all deployed with Terraform and zero service account keys."
- **Target length:** 1,800--2,000 words (8-10 minute read)
- **Tags:** mlops, data-engineering, gcp, terraform, fraud-detection
- **Publish:** Week 4 (capstone, links to all 3 previous posts)

## Hook

"This project started as a hackathon submission and ended as a production-grade pipeline: streaming ingestion through Pub/Sub, 60 features engineered in pure SQL, a LightGBM model with focal loss, and a FastAPI endpoint on Cloud Run -- all managed by Terraform with keyless GitHub Actions authentication. Here's the architecture and the decisions behind it."

## Outline

### 1. Architecture at a glance (300 words)
- **Diagram placeholder: Full architecture** (Excalidraw Diagram 1 -- the main one)
- 6 layers: Ingestion → Transformation → ML → Serving → Infrastructure → CI/CD
- Each layer links to its deep-dive post or repo doc
- "The goal was to demonstrate full-stack ML engineering, not just modeling"

### 2. Ingestion: streaming 1.2GB through Pub/Sub (300 words)
- Cloud Scheduler → Producer Cloud Function → Pub/Sub (Protobuf) → Consumer → BigQuery
- Key decision: Protobuf for schema contracts, time-based chunking to avoid OOM
- Lesson learned: 512MB Cloud Function crashed on blob.download_as_text(); switched to streaming reads
- Link to Post 1 (leakage) for the downstream data quality story
- **Diagram placeholder: Ingestion detail** (Excalidraw Diagram 2)

### 3. Transformation: 60 features in pure SQL (300 words)
- dbt on BigQuery: staging → intermediate → marts
- mart_fraud_features: 60+ features via window functions (velocity, behavioral, errors, geographic)
- **Diagram placeholder: dbt lineage** (Excalidraw Diagram 3)
- Key pattern: UNIX_SECONDS for RANGE windows, correlated subqueries for COUNT(DISTINCT)
- "Feature engineering was more impactful than model selection -- errors column alone jumped AUPRC from near-zero to 0.43"

### 4. ML: focal loss + honest metrics (300 words)
- Summary of the 9-experiment journey (table: baseline → final)
- **Diagram placeholder: Experiment timeline** (Excalidraw Diagram 5)
- Two key stories (link to Posts 1 and 2):
  - Focal loss beat class weights by 19%
  - Caught data leakage via ablation study
- Expense forecasting: R2=0.76 ceiling analysis (link to Post 3)

### 5. Serving: FastAPI on Cloud Run (200 words)
- Lifespan model loading, sigmoid correction for focal loss logits
- Target encoding at serving time with global mean fallback
- 3-layer LLM strategy for the agent endpoint (Vertex AI / Ollama / regex)
- Scale to zero for cost optimization

### 6. Infrastructure: Terraform + zero keys (300 words)
- Two-phase Terraform (bootstrap vs main)
- Workload Identity Federation: GitHub OIDC → GCP, no service account keys stored anywhere
- SOPS + KMS: encrypted secrets committed to repo, decryptable only by authorized identities
- 8 Terraform modules, total cost: $0/month (GCP Always Free tier)
- **Diagram placeholder: Infrastructure** (Excalidraw Diagram 9)

### 7. What I'd do differently (200 words)
- Feature store instead of dbt marts for real-time scoring
- Model registry instead of baking pkl files into Docker images
- Dead letter queue subscription (currently just the topic)
- Incremental dbt models for daily ingestion
- "These are the gaps between a portfolio project and a production system -- but the architecture supports extending to all of them"

### Closing
- Link to all 3 previous posts
- Link to GitHub repo
- "The project is open source. The experiment logs, the leaking CTE, the focal loss implementation -- it's all there."

## Diagrams Needed
1. **Full architecture** (Excalidraw Diagram 1) -- THE main diagram, used in README too
2. **Ingestion detail** (Excalidraw Diagram 2)
3. **dbt lineage** (Excalidraw Diagram 3)
4. **Experiment timeline** (Excalidraw Diagram 5)
5. **Infrastructure** (Excalidraw Diagram 9)

## Code Snippets to Include
- Makefile targets (show the interface: `make dbt-build`, `make export-models`, `make serve`, `make lint`)
- The focal_loss_objective function (3 lines, just the core: sigmoid, pt, focal_weight)
- The `generate_schema_name` macro (6 lines, from dbt/macros/)
