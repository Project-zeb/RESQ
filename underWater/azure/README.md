# Azure Deployment (Docker + Student Credits)

This project deploys as two Docker containers on **Azure Container Apps**:

- `projectz-main` from `projectz_v5/`
- `projectz-internal` from `internal api/`

The deploy script is tuned for student credits:

- `min replicas = 0` on main app, `min replicas = 1` on internal API (to keep scheduler running)
- small CPU/memory limits
- Container Apps environment logs set to `none`
- automatic region fallback if a location is blocked by subscription policy

## 1) Prerequisites

- Azure CLI (`az`)
- Docker Desktop running
- An active Azure subscription (Azure for Students is fine)

## 2) Configure (optional)

```bash
cd "/Users/matrika/Downloads/projectz_v5 3"
cp azure/.env.example azure/.env
```

Edit `azure/.env` only if you want custom names/region/secrets.

## 3) Deploy

```bash
cd "/Users/matrika/Downloads/projectz_v5 3"
chmod +x azure/deploy_container_apps.sh azure/destroy_resources.sh
./azure/deploy_container_apps.sh
```

If you want to use a non-default config file:

```bash
./azure/deploy_container_apps.sh /absolute/path/to/your.env
```

## 4) Logs

```bash
az containerapp logs show -n projectz-main -g rg-projectz-student --follow
az containerapp logs show -n projectz-internal -g rg-projectz-student --follow
```

## 5) Re-deploy after code changes

Run deploy script again. It rebuilds, pushes, and updates both apps:

```bash
./azure/deploy_container_apps.sh
```

## 6) Stop all charges

```bash
./azure/destroy_resources.sh
```

## Notes

- SQLite files are stored inside container filesystem, so data is not durable across restarts/revisions.
- For durable production data, move to Azure Database or attach persistent storage.
