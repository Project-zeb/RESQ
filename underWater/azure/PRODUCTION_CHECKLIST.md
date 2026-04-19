# ProjectZ Production Checklist (Azure Container Apps)

## 1) Use production deploy profile
```bash
cd "/Users/matrika/Downloads/projectz_v5 3"
cp azure/.env.production.example azure/.env.production
# edit azure/.env.production with your real values
./azure/deploy_container_apps.sh azure/.env.production
```

## 2) Must use managed DB for real production
Using `PRIMARY_DB=sqlite` on Container Apps can lose data on restart/revision changes.
Set in `azure/.env.production`:
- `APP_PRIMARY_DB=mysql`
- `DB_HOST`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

## 3) DNS + custom domain
1. Buy/use your domain.
2. Add CNAME to your Container App FQDN.
3. Bind custom domain and managed certificate in Azure Container Apps.
4. Update `GOOGLE_REDIRECT_URI` to your real domain callback URL.

## 4) Security posture now enforced by deploy script
- `SECURE_PASSWORD_MODE=true`
- `STORE_PLAIN_PASSWORDS=false`
- `EXPOSE_PLAIN_PASSWORDS=false`
- main app replicas default to `1..3` in production profile

## 5) Monitoring
Run logs:
```bash
az containerapp logs show -n projectz-main -g rg-projectz-student --follow
az containerapp logs show -n projectz-internal -g rg-projectz-student --follow
```

## 6) Post-deploy smoke tests
- Signup/login works
- Report disaster appears in admin incidents tab
- Live alerts endpoint returns `success: true`
- Google login callback works from your production domain
