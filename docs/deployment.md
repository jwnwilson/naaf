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
  `kubectl rollout undo deployment/naaf-api` (and `.../naaf-temporal-worker`).
- UI: re-run `Deploy UI` from an earlier commit (S3 sync + invalidation).

## Known follow-ups (out of scope here)

Auth0 wiring (API ships in `dev` auth mode = single shared owner), Temporal Web
UI exposure, managed Postgres (RDS), staging environment.
