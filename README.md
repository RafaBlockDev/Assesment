# Amazon Stock Query Agent

An AI-powered agent that answers natural language questions about Amazon (AMZN) stock prices using real-time market data and financial documents (annual reports, earnings releases). Built with FastAPI, LangGraph, and deployed on AWS using ECS Fargate + Cognito for auth.

This was built as part of an AWS Agentcore assessment to demonstrate an end-to-end agentic RAG pipeline with observability.

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Deploy to AWS](#deploy-to-aws)
- [Run Locally](#run-locally)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI + Uvicorn |
| Agent | LangGraph (ReAct pattern) |
| LLM | Claude via AWS Bedrock |
| Auth | AWS Cognito |
| Knowledge Base | FAISS + sentence-transformers, PDF ingestion with LangChain |
| Market Data | yfinance |
| Observability | Langfuse |
| Infra | Terraform, ECS Fargate, S3 |
| Container | Docker |

## Prerequisites

- Python 3.11+ (3.13 works too)
- AWS account with Bedrock access enabled
- AWS CLI configured (`aws configure`)
- Terraform >= 1.0
- Docker (for containerized deployment)

## Getting Started

Clone and set up your environment:

```bash
git clone <repo-url> && cd Assesment
cp .env.example .env
```

Fill in `.env` with your values. At minimum you need:

```
AWS_REGION=us-east-2
AWS_ACCESS_KEY_ID=<your key>
AWS_SECRET_ACCESS_KEY=<your secret>
COGNITO_USER_POOL_ID=<from terraform output>
COGNITO_CLIENT_ID=<from terraform output>
COGNITO_DOMAIN=<from terraform output>
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0
LANGFUSE_PUBLIC_KEY=<your key>
LANGFUSE_SECRET_KEY=<your key>
```

> **Note:** `BEDROCK_MODEL_ID` must use an inference profile ID (prefixed with `us.`), not the raw model ID. Run `aws bedrock list-inference-profiles --region us-east-2` to see available options.

## Deploy to AWS

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with your container image URI and preferences
```

```bash
terraform init
terraform plan        # review what will be created
terraform apply       # type 'yes' to confirm
```

After apply you'll get:

```
cognito_user_pool_id = "us-east-2_xxxxxxx"
cognito_client_id    = "xxxxxxxxxxxxxxxxxxxxxxxxxx"
cognito_domain       = "https://stock-agent-dev-xxxx.auth.us-east-2.amazoncognito.com"
s3_documents_bucket  = "stock-agent-dev-documents-xxxx"
```

Create a test user:

```bash
aws cognito-idp admin-create-user \
  --region us-east-2 \
  --user-pool-id <POOL_ID> \
  --username testuser@example.com \
  --user-attributes Name=email,Value=testuser@example.com Name=name,Value="Test User" \
  --temporary-password 'TempPass123!'

aws cognito-idp admin-set-user-password \
  --region us-east-2 \
  --user-pool-id <POOL_ID> \
  --username testuser@example.com \
  --password 'TestPass123\!' \
  --permanent
```

## Run Locally

**Option 1: Python directly**

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn src.api.main:app --reload --port 8000
```

**Option 2: Docker**

```bash
docker compose up --build
```

Verify it's running:

```bash
curl http://localhost:8000/health
# {"status":"healthy","environment":"development","timestamp":"2026-..."}
```

## Usage

### Authenticate

```bash
# Get tokens
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser@example.com","password":"TestPass123\\!"}'
```

Save the `access_token` from the response.

### Query the agent

**Streaming (default):**

```bash
curl -N -X POST http://localhost:8000/query \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is Amazon stock price right now?","stream":true}'
```

Returns SSE events:

```
data: {"type":"thought","content":"...","trace_id":"abc-123"}
data: {"type":"action","content":"{\"tool\":\"retrieve_realtime_stock_price\",\"args\":{\"ticker\":\"AMZN\"}}","trace_id":"abc-123"}
data: {"type":"observation","content":"{\"ticker\":\"AMZN\",\"price\":186.42,...}","trace_id":"abc-123"}
data: {"type":"final_answer","content":"Amazon (AMZN) is currently trading at...","trace_id":"abc-123"}
data: {"type":"done","trace_id":"abc-123"}
```

**Non-streaming:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is Amazon stock price right now?","stream":false}'
```

```json
{
  "answer": "Amazon (AMZN) is currently trading at $186.42...",
  "sources": [],
  "trace_id": "abc-123"
}
```

### Demo notebook

There's a full demo notebook at `notebooks/demo_execution.ipynb` that runs 5 different queries (real-time, historical, RAG, combined) and plots the results.

## Project Structure

```
.
├── config.py                        # Pydantic settings, AWS clients, Langfuse
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
│
├── src/
│   ├── api/
│   │   ├── auth.py                  # CognitoAuth class, JWT validation, FastAPI deps
│   │   └── main.py                  # FastAPI app, routes, SSE streaming
│   ├── agent/
│   │   ├── tools.py                 # yfinance tools + document search
│   │   └── graph.py                 # LangGraph ReAct agent with streaming
│   └── knowledge_base/
│       ├── loader.py                # PDF download + chunking
│       └── retriever.py             # FAISS vector store + HuggingFace embeddings
│
├── terraform/
│   ├── main.tf                      # Provider, locals
│   ├── cognito.tf                   # User pool, app client, domain
│   ├── agentcore.tf                 # ECS Fargate, IAM, S3, CloudWatch, SG
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
│
├── notebooks/
│   ├── demo_execution.ipynb         # Full demo with 5 queries + charts
│   └── test_api.ipynb               # Quick API test
│
└── docs/documents/                  # Local fallback for Amazon PDFs
```

## Troubleshooting

**`zsh: command not found: uvicorn`** — You're not inside the venv. Run `source venv/bin/activate` first.

**Auth returns 401** — Make sure the Cognito user exists and the password has been changed from the temporary one. You can force-set it with:
```bash
aws cognito-idp admin-set-user-password \
  --user-pool-id <POOL_ID> --username testuser@example.com \
  --password 'NewPass123!' --permanent
```

**Knowledge base empty** — PDFs failed to download. Either check your internet connection or manually place the PDF files in `docs/documents/`.

**Bedrock access denied** — Make sure your AWS account has Bedrock model access enabled for Claude in us-east-2. Go to the Bedrock console > Model access > Request access.

**Bedrock ValidationException (on-demand throughput not supported)** — You need to use an inference profile ID, not the raw model ID. Use `us.anthropic.claude-sonnet-4-20250514-v1:0` instead of `anthropic.claude-sonnet-4-20250514-v1:0`. Run `aws bedrock list-inference-profiles --region us-east-2` to find available profiles.

**Auth returns 500 (secret hash received)** — Your Cognito App Client doesn't have a secret but `COGNITO_CLIENT_SECRET` is set in `.env`. Clear it: `COGNITO_CLIENT_SECRET=`.

**Docker build fails on pydantic-core** — You're probably on Python 3.14. The Dockerfile uses 3.11-slim which works fine, but for local dev use `python3.13 -m venv venv` instead.

**Langfuse traces not showing** — Verify `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set correctly. The app logs a warning at startup if Langfuse isn't reachable.

## License

MIT
