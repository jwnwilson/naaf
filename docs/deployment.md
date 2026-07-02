# NAAF Deployment Runbook

Production deploy: UI on S3+CloudFront, backend on the shared K8s cluster
(`default` namespace, every object prefixed `naaf-`).

## One-time bootstrap

1. **Terraform state bucket** (out-of-band):
   ```bash
   aws s3 mb s3://naaf-terraform-state --region us-east-1
   aws s3api put-bucket-versioning --bucket naaf-terraform-state \
     --versioning-configuration Status=Enabled
   ```
2. **Apply Terraform:**
   ```bash
   cd infra/terraform
   terraform init
   terraform apply -var github_repo=<owner/name> -var cluster_ip=<ingress public IP>
   ```
   If the account already has a GitHub OIDC provider, import it first:
   `terraform import module.iam.aws_iam_openid_connect_provider.github <arn>`.
3. **Record outputs** and set them as GitHub repo secrets:
   `terraform output` -> `AWS_ROLE_ARN`, `UI_BUCKET`, `UI_CF_DISTRIBUTION_ID`.
4. **Set the remaining GitHub secrets** (see the plan's secrets table):
   `KUBE_CONFIG` (base64), `naaf_DB_PASSWORD`, `naaf_SECRET_KEY`,
   `ANTHROPIC_API_KEY`, `LITELLM_MASTER_KEY`, and the `naaf_GITHUB_*` set.
5. **Confirm the cluster prerequisites** (already present from llm_api):
   `kubectl get clusterissuer` (issuer name matches the ingress annotation),
   `kubectl -n default get secret ecr-credentials` (refresher is populating it).

## Routine deploys

Push to `main`. `Test` runs; on success `Deploy Backend` and `Deploy UI` fire
automatically. Manual re-deploy: run either workflow via `workflow_dispatch`.

## Rollback

- Backend: re-run `Deploy Backend` against an earlier commit, or
  `kubectl rollout undo deployment/naaf-api`.
- UI: re-run `Deploy UI` from an earlier commit (S3 sync + invalidation).

## LiteLLM gateway (local dev — provider-swap route)

Set these env vars to route the agent runtime through a LiteLLM gateway instead of
calling Anthropic directly:

```bash
naaf_llm_provider=litellm
naaf_litellm_base_url=http://localhost:4000
naaf_litellm_key=<your-litellm-master-key>
```

Start the gateway (see the commented-out `litellm` service in `docker-compose.yml`
— pin a specific `ghcr.io/berriai/litellm:main-v1.x.y` tag before use):

```bash
docker compose up -d litellm
```

The gateway proxies OpenAI-compatible `/chat/completions` calls to any backend
(Anthropic, OpenAI, Azure, Ollama, etc.) via `litellm.config.yaml`.

## Known follow-ups (out of scope here)

Auth0 wiring (API ships in `dev` auth mode = single shared owner), managed
Postgres (RDS), staging environment.
