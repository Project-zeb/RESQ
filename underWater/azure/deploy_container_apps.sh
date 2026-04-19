#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MAIN_DIR="${PROJECT_ROOT}/projectz_v5"
INTERNAL_DIR="${PROJECT_ROOT}/internal api"
DEFAULT_CONFIG_FILE="${SCRIPT_DIR}/.env"

log() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

run_with_retry() {
  local attempts="$1"
  local delay_seconds="$2"
  shift 2

  local attempt=1
  local output=""
  while (( attempt <= attempts )); do
    if output="$("$@" 2>&1)"; then
      return 0
    fi
    log "Command failed (attempt ${attempt}/${attempts}): $*"
    log "Error: ${output}"
    if (( attempt == attempts )); then
      return 1
    fi
    sleep "${delay_seconds}"
    attempt=$((attempt + 1))
  done
}

docker_login_with_retry() {
  local attempts="$1"
  local delay_seconds="$2"
  local server="$3"
  local username="$4"
  local password="$5"

  local attempt=1
  local output=""
  while (( attempt <= attempts )); do
    if output="$(
      printf '%s' "${password}" | docker login "${server}" --username "${username}" --password-stdin 2>&1
    )"; then
      return 0
    fi
    log "Docker login failed (attempt ${attempt}/${attempts})"
    log "Error: ${output}"
    if (( attempt == attempts )); then
      return 1
    fi
    sleep "${delay_seconds}"
    attempt=$((attempt + 1))
  done
}

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi
  if command -v uuidgen >/dev/null 2>&1; then
    uuidgen | tr -d '-' | tr '[:upper:]' '[:lower:]'
    return
  fi
  die "Need either openssl or uuidgen to generate secrets."
}

validate_containerapp_name() {
  local name="$1"
  if [[ ! "${name}" =~ ^[a-z][a-z0-9-]{0,30}[a-z0-9]$ ]]; then
    die "Invalid container app name '${name}'. Use lowercase letters, numbers, '-', max 32 chars."
  fi
  if [[ "${name}" == *--* ]]; then
    die "Invalid container app name '${name}'. Consecutive '--' is not allowed."
  fi
}

CONFIG_FILE="${1:-${DEFAULT_CONFIG_FILE}}"
if [[ -n "${1:-}" && ! -f "${CONFIG_FILE}" ]]; then
  die "Config file not found: ${CONFIG_FILE}"
fi

if [[ -f "${CONFIG_FILE}" ]]; then
  log "Loading config: ${CONFIG_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
  set +a
fi

[[ -d "${MAIN_DIR}" ]] || die "Main app directory missing: ${MAIN_DIR}"
[[ -d "${INTERNAL_DIR}" ]] || die "Internal API directory missing: ${INTERNAL_DIR}"

require_cmd az
require_cmd docker

export AZURE_CONFIG_DIR="${AZURE_CONFIG_DIR:-${PROJECT_ROOT}/.azure}"
mkdir -p "${AZURE_CONFIG_DIR}"

: "${AZURE_LOCATION:=eastus}"
: "${AZURE_RESOURCE_GROUP:=rg-projectz-student}"
: "${AZURE_CONTAINERAPPS_ENV:=cae-projectz-student}"
: "${AZURE_MAIN_APP_NAME:=projectz-main}"
: "${AZURE_INTERNAL_APP_NAME:=projectz-internal}"
: "${AZURE_MAIN_IMAGE_REPO:=projectz-main}"
: "${AZURE_INTERNAL_IMAGE_REPO:=projectz-internal}"
: "${AZURE_IMAGE_TAG:=$(date +%Y%m%d%H%M%S)}"
: "${AZURE_LOCATION_FALLBACKS:=westus2 centralus southeastasia northeurope westeurope centralindia australiaeast japaneast uksouth canadacentral}"
: "${AZURE_DEPLOY_PROFILE:=production}"
: "${AZURE_USE_ACR_BUILD:=auto}"
: "${APP_PRIMARY_DB:=sqlite}"
: "${INTERNAL_POLL_INTERVAL_SECONDS:=300}"
: "${INTERNAL_HTTP_TIMEOUT_SECONDS:=20}"
: "${INTERNAL_REQUEST_RETRIES:=5}"
: "${INTERNAL_REQUEST_BACKOFF_SECONDS:=1.0}"
: "${INTERNAL_SOURCE_STAGGER_SECONDS:=2.0}"
: "${ENABLE_COLLECTOR_SNAPSHOT:=false}"
: "${COLLECTOR_ALERT_JSON:=}"
: "${OGD_DATASET_URL:=}"
: "${OGD_API_KEY:=}"
: "${MOSDAC_ENDPOINT_URL:=}"
: "${MOSDAC_API_TOKEN:=}"
: "${AZURE_ENABLE_STORAGE:=true}"
: "${AZURE_STORAGE_ACCOUNT:=}"
: "${AZURE_STORAGE_SHARE:=projectzdata}"
: "${AZURE_STORAGE_ENV_NAME:=projectzfiles}"
: "${AZURE_STORAGE_MOUNT_PATH:=/mnt/projectz}"
: "${AZURE_STORAGE_SKU:=Standard_LRS}"
: "${AZURE_STORAGE_QUOTA_GB:=5}"

AZURE_DEPLOY_PROFILE="$(printf '%s' "${AZURE_DEPLOY_PROFILE}" | tr '[:upper:]' '[:lower:]')"
AZURE_USE_ACR_BUILD="$(printf '%s' "${AZURE_USE_ACR_BUILD}" | tr '[:upper:]' '[:lower:]')"
APP_PRIMARY_DB="$(printf '%s' "${APP_PRIMARY_DB}" | tr '[:upper:]' '[:lower:]')"
AZURE_ENABLE_STORAGE="$(printf '%s' "${AZURE_ENABLE_STORAGE}" | tr '[:upper:]' '[:lower:]')"

if [[ "${AZURE_DEPLOY_PROFILE}" != "student" && "${AZURE_DEPLOY_PROFILE}" != "production" ]]; then
  die "AZURE_DEPLOY_PROFILE must be either 'student' or 'production'."
fi

if [[ "${APP_PRIMARY_DB}" != "sqlite" && "${APP_PRIMARY_DB}" != "mysql" ]]; then
  die "APP_PRIMARY_DB must be either 'sqlite' or 'mysql'."
fi

if [[ "${AZURE_DEPLOY_PROFILE}" == "production" ]]; then
  : "${AZURE_MAIN_MIN_REPLICAS:=1}"
  : "${AZURE_INTERNAL_MIN_REPLICAS:=1}"
  : "${AZURE_MAIN_MAX_REPLICAS:=3}"
  : "${AZURE_INTERNAL_MAX_REPLICAS:=2}"
else
  : "${AZURE_MAIN_MIN_REPLICAS:=0}"
  : "${AZURE_INTERNAL_MIN_REPLICAS:=1}"
  : "${AZURE_MAIN_MAX_REPLICAS:=1}"
  : "${AZURE_INTERNAL_MAX_REPLICAS:=1}"
fi

if [[ "${APP_PRIMARY_DB}" == "sqlite" ]]; then
  if [[ "${AZURE_MAIN_MAX_REPLICAS}" -gt 1 ]]; then
    log "SQLite selected for main app; forcing AZURE_MAIN_MAX_REPLICAS=1 to avoid DB locking."
    AZURE_MAIN_MAX_REPLICAS=1
  fi
  if [[ "${AZURE_INTERNAL_MAX_REPLICAS}" -gt 1 ]]; then
    log "SQLite selected for internal API; forcing AZURE_INTERNAL_MAX_REPLICAS=1 to avoid DB locking."
    AZURE_INTERNAL_MAX_REPLICAS=1
  fi
fi

if [[ "${APP_PRIMARY_DB}" == "mysql" ]]; then
  [[ -n "${DB_HOST:-}" ]] || die "Set DB_HOST when APP_PRIMARY_DB=mysql"
  [[ -n "${DB_USER:-}" ]] || die "Set DB_USER when APP_PRIMARY_DB=mysql"
  [[ -n "${DB_NAME:-}" ]] || die "Set DB_NAME when APP_PRIMARY_DB=mysql"
  [[ -n "${DB_PASSWORD:-}" ]] || die "Set DB_PASSWORD when APP_PRIMARY_DB=mysql"
fi

validate_containerapp_name "${AZURE_MAIN_APP_NAME}"
validate_containerapp_name "${AZURE_INTERNAL_APP_NAME}"

if [[ -z "${AZURE_ACR_NAME:-}" ]]; then
  user_part="$(printf '%s' "${USER:-student}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
  user_part="${user_part:0:10}"
  [[ -n "${user_part}" ]] || user_part="student"
  AZURE_ACR_NAME="projectz${user_part}$(generate_secret | cut -c1-6)"
fi

AZURE_ACR_NAME="$(printf '%s' "${AZURE_ACR_NAME}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
if [[ ${#AZURE_ACR_NAME} -lt 5 || ${#AZURE_ACR_NAME} -gt 50 ]]; then
  die "AZURE_ACR_NAME must be 5-50 chars after normalization. Current: '${AZURE_ACR_NAME}'"
fi

: "${MAIN_SECRET_KEY:=$(generate_secret)}"
: "${INTERNAL_API_KEY:=$(generate_secret)}"
: "${ADMIN_API_KEY:=$(generate_secret)}"

if ! az account show --only-show-errors >/dev/null 2>&1; then
  log "Azure login required. Starting device-code login..."
  az login --use-device-code --output none
fi

if [[ -n "${AZURE_SUBSCRIPTION_ID:-}" ]]; then
  log "Setting subscription: ${AZURE_SUBSCRIPTION_ID}"
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --only-show-errors
fi

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
log "Subscription: ${SUBSCRIPTION_ID}"
log "Resource Group: ${AZURE_RESOURCE_GROUP}"
log "Location: ${AZURE_LOCATION}"
log "Container Apps Environment: ${AZURE_CONTAINERAPPS_ENV}"
log "Main App: ${AZURE_MAIN_APP_NAME}"
log "Internal App: ${AZURE_INTERNAL_APP_NAME}"
log "ACR: ${AZURE_ACR_NAME}"
log "Image Tag: ${AZURE_IMAGE_TAG}"
log "Deploy profile: ${AZURE_DEPLOY_PROFILE}"
log "Primary DB: ${APP_PRIMARY_DB}"
log "Main min replicas: ${AZURE_MAIN_MIN_REPLICAS}"
log "Internal min replicas: ${AZURE_INTERNAL_MIN_REPLICAS}"
log "Main max replicas: ${AZURE_MAIN_MAX_REPLICAS}"
log "Internal max replicas: ${AZURE_INTERNAL_MAX_REPLICAS}"
log "Internal extra sources: OGD=$( [[ -n "${OGD_DATASET_URL}" ]] && printf 'on' || printf 'off' ), MOSDAC=$( [[ -n "${MOSDAC_ENDPOINT_URL}" ]] && printf 'on' || printf 'off' )"
if [[ "${AZURE_ENABLE_STORAGE}" == "true" ]]; then
  log "Azure Files storage: enabled (account=$( [[ -n "${AZURE_STORAGE_ACCOUNT}" ]] && printf '%s' "${AZURE_STORAGE_ACCOUNT}" || printf 'auto' ), share=${AZURE_STORAGE_SHARE}, mount=${AZURE_STORAGE_MOUNT_PATH})"
else
  log "Azure Files storage: disabled"
fi

for namespace in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry Microsoft.Storage; do
  log "Registering provider: ${namespace}"
  run_with_retry 5 4 az provider register \
    --namespace "${namespace}" \
    --wait \
    --only-show-errors \
    --output none || die "Provider registration failed for '${namespace}' after retries."
done

existing_rg_location="$(
  az group show \
    --name "${AZURE_RESOURCE_GROUP}" \
    --query location \
    -o tsv \
    --only-show-errors 2>/dev/null || true
)"

if [[ -n "${existing_rg_location}" ]]; then
  log "Reusing existing resource group '${AZURE_RESOURCE_GROUP}' in location: ${existing_rg_location}"
else
  log "Creating resource group '${AZURE_RESOURCE_GROUP}' in location: ${AZURE_LOCATION}"
  az group create \
    --name "${AZURE_RESOURCE_GROUP}" \
    --location "${AZURE_LOCATION}" \
    --only-show-errors \
    --output none
fi

if az acr show --name "${AZURE_ACR_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
  log "Reusing existing ACR: ${AZURE_ACR_NAME}"
  AZURE_LOCATION="$(az acr show --name "${AZURE_ACR_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --query location -o tsv)"
else
  log "Creating ACR: ${AZURE_ACR_NAME}"
  candidates="${AZURE_LOCATION} ${AZURE_LOCATION_FALLBACKS}"
  tried_regions=""
  acr_created=false
  selected_region=""

  for region in ${candidates}; do
    if [[ " ${tried_regions} " == *" ${region} "* ]]; then
      continue
    fi
    tried_regions="${tried_regions} ${region}"

    log "Trying ACR region: ${region}"
    if create_output="$(
      az acr create \
        --name "${AZURE_ACR_NAME}" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --location "${region}" \
        --sku Basic \
        --admin-enabled true \
        --only-show-errors \
        --output none 2>&1
    )"; then
      acr_created=true
      selected_region="${region}"
      break
    fi

    if printf '%s' "${create_output}" | grep -Eq "RequestDisallowedByAzure|LocationNotAvailableForResourceType"; then
      log "Region ${region} denied by policy or unavailable for ACR, trying next."
      continue
    fi

    if printf '%s' "${create_output}" | grep -Ei "already taken|already in use|not available|NameNotAvailable" >/dev/null; then
      die "ACR name '${AZURE_ACR_NAME}' is unavailable. Set AZURE_ACR_NAME to a unique value in azure/.env and rerun."
    fi

    die "ACR creation failed in region '${region}': ${create_output}"
  done

  if [[ "${acr_created}" != "true" ]]; then
    die "ACR creation was denied in all tried regions (${tried_regions}). Set AZURE_LOCATION to an allowed region in azure/.env and rerun."
  fi

  AZURE_LOCATION="${selected_region}"
  log "Selected deployment region after policy checks: ${AZURE_LOCATION}"
fi

az acr update \
  --name "${AZURE_ACR_NAME}" \
  --admin-enabled true \
  --only-show-errors \
  --output none

ACR_LOGIN_SERVER="$(az acr show --name "${AZURE_ACR_NAME}" --query loginServer -o tsv)"
ACR_USERNAME="$(az acr credential show --name "${AZURE_ACR_NAME}" --query username -o tsv)"
ACR_PASSWORD="$(az acr credential show --name "${AZURE_ACR_NAME}" --query 'passwords[0].value' -o tsv)"
ACR_SERVER_KEY="$(printf '%s' "${ACR_LOGIN_SERVER}" | tr -cd 'a-z0-9')"
ACR_USER_KEY="$(printf '%s' "${ACR_USERNAME}" | tr -cd 'a-z0-9')"
ACR_SECRET_NAME="${ACR_SERVER_KEY}-${ACR_USER_KEY}"

MAIN_IMAGE="${ACR_LOGIN_SERVER}/${AZURE_MAIN_IMAGE_REPO}:${AZURE_IMAGE_TAG}"
INTERNAL_IMAGE="${ACR_LOGIN_SERVER}/${AZURE_INTERNAL_IMAGE_REPO}:${AZURE_IMAGE_TAG}"

USE_ACR_BUILD="false"
case "${AZURE_USE_ACR_BUILD}" in
  1|true|yes|on)
    USE_ACR_BUILD="true"
    ;;
  0|false|no|off)
    USE_ACR_BUILD="false"
    ;;
  auto)
    if ! docker info >/dev/null 2>&1; then
      USE_ACR_BUILD="true"
    fi
    ;;
  *)
    die "AZURE_USE_ACR_BUILD must be 'auto', 'true', or 'false'. Got: '${AZURE_USE_ACR_BUILD}'"
    ;;
esac

if [[ "${USE_ACR_BUILD}" == "true" ]]; then
  log "Docker daemon not available; building images in ACR (az acr build)..."
  run_with_retry 3 10 az acr build \
    --registry "${AZURE_ACR_NAME}" \
    --image "${AZURE_MAIN_IMAGE_REPO}:${AZURE_IMAGE_TAG}" \
    --platform linux/amd64 \
    --only-show-errors \
    --output none \
    "${MAIN_DIR}" || die "Failed to build main image in ACR."

  run_with_retry 3 10 az acr build \
    --registry "${AZURE_ACR_NAME}" \
    --image "${AZURE_INTERNAL_IMAGE_REPO}:${AZURE_IMAGE_TAG}" \
    --platform linux/amd64 \
    --only-show-errors \
    --output none \
    "${INTERNAL_DIR}" || die "Failed to build internal API image in ACR."
else
  log "Docker login to ACR..."
  docker_login_with_retry 6 6 "${ACR_LOGIN_SERVER}" "${ACR_USERNAME}" "${ACR_PASSWORD}" \
    || die "Docker login to ACR failed after retries."

  log "Building main image: ${MAIN_IMAGE}"
  docker build --platform linux/amd64 --tag "${MAIN_IMAGE}" "${MAIN_DIR}"
  log "Pushing main image..."
  run_with_retry 5 6 docker push "${MAIN_IMAGE}" || die "Failed to push main image after retries."

  log "Building internal API image: ${INTERNAL_IMAGE}"
  docker build --platform linux/amd64 --tag "${INTERNAL_IMAGE}" "${INTERNAL_DIR}"
  log "Pushing internal API image..."
  run_with_retry 5 6 docker push "${INTERNAL_IMAGE}" || die "Failed to push internal API image after retries."
fi

if az containerapp env show --name "${AZURE_CONTAINERAPPS_ENV}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
  log "Reusing existing Container Apps environment: ${AZURE_CONTAINERAPPS_ENV}"
  AZURE_LOCATION="$(az containerapp env show --name "${AZURE_CONTAINERAPPS_ENV}" --resource-group "${AZURE_RESOURCE_GROUP}" --query location -o tsv)"
else
  log "Creating Container Apps environment: ${AZURE_CONTAINERAPPS_ENV}"
  candidates="${AZURE_LOCATION} ${AZURE_LOCATION_FALLBACKS}"
  tried_regions=""
  env_created=false
  selected_env_region=""

  for region in ${candidates}; do
    if [[ " ${tried_regions} " == *" ${region} "* ]]; then
      continue
    fi
    tried_regions="${tried_regions} ${region}"

    log "Trying Container Apps environment region: ${region}"
    if env_output="$(
      az containerapp env create \
        --name "${AZURE_CONTAINERAPPS_ENV}" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --location "${region}" \
        --logs-destination none \
        --enable-workload-profiles false \
        --only-show-errors \
        --output none 2>&1
    )"; then
      env_created=true
      selected_env_region="${region}"
      break
    fi

    if printf '%s' "${env_output}" | grep -Eq "RequestDisallowedByAzure|LocationNotAvailableForResourceType|not available in this location|InvalidLocation"; then
      log "Region ${region} denied by policy or unavailable for Container Apps environment, trying next."
      continue
    fi

    die "Container Apps environment creation failed in region '${region}': ${env_output}"
  done

  if [[ "${env_created}" != "true" ]]; then
    die "Container Apps environment creation was denied in all tried regions (${tried_regions}). Set AZURE_LOCATION to an allowed region in azure/.env and rerun."
  fi

  AZURE_LOCATION="${selected_env_region}"
  log "Selected Container Apps environment region: ${AZURE_LOCATION}"
fi

STORAGE_READY="false"
AZURE_STORAGE_KEY=""

configure_storage() {
  if [[ "${AZURE_ENABLE_STORAGE}" != "true" ]]; then
    return
  fi

  if [[ -z "${AZURE_STORAGE_ACCOUNT}" ]]; then
    storage_user="$(printf '%s' "${USER:-student}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
    storage_user="${storage_user:0:10}"
    [[ -n "${storage_user}" ]] || storage_user="student"
    AZURE_STORAGE_ACCOUNT="pz${storage_user}$(generate_secret | cut -c1-8)"
  fi

  AZURE_STORAGE_ACCOUNT="$(printf '%s' "${AZURE_STORAGE_ACCOUNT}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
  if [[ ${#AZURE_STORAGE_ACCOUNT} -lt 3 || ${#AZURE_STORAGE_ACCOUNT} -gt 24 ]]; then
    die "AZURE_STORAGE_ACCOUNT must be 3-24 lowercase letters/numbers after normalization. Current: '${AZURE_STORAGE_ACCOUNT}'"
  fi

  AZURE_STORAGE_SHARE="$(printf '%s' "${AZURE_STORAGE_SHARE}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')"
  AZURE_STORAGE_SHARE="${AZURE_STORAGE_SHARE#-}"
  AZURE_STORAGE_SHARE="${AZURE_STORAGE_SHARE%-}"
  if [[ ${#AZURE_STORAGE_SHARE} -lt 3 || ${#AZURE_STORAGE_SHARE} -gt 63 ]]; then
    die "AZURE_STORAGE_SHARE must be 3-63 chars (letters/numbers/hyphen). Current: '${AZURE_STORAGE_SHARE}'"
  fi

  AZURE_STORAGE_ENV_NAME="$(printf '%s' "${AZURE_STORAGE_ENV_NAME}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')"
  if [[ -z "${AZURE_STORAGE_ENV_NAME}" ]]; then
    AZURE_STORAGE_ENV_NAME="projectzfiles"
  fi

  if [[ "${AZURE_STORAGE_MOUNT_PATH}" != /* ]]; then
    die "AZURE_STORAGE_MOUNT_PATH must be an absolute path. Current: '${AZURE_STORAGE_MOUNT_PATH}'"
  fi
  AZURE_STORAGE_MOUNT_PATH="${AZURE_STORAGE_MOUNT_PATH%/}"

  existing_storage_account="$(
    az containerapp env storage show \
      --name "${AZURE_CONTAINERAPPS_ENV}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --storage-name "${AZURE_STORAGE_ENV_NAME}" \
      --query 'properties.azureFile.accountName' -o tsv 2>/dev/null || true
  )"
  if [[ -n "${existing_storage_account}" ]]; then
    existing_storage_share="$(
      az containerapp env storage show \
        --name "${AZURE_CONTAINERAPPS_ENV}" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --storage-name "${AZURE_STORAGE_ENV_NAME}" \
        --query 'properties.azureFile.shareName' -o tsv 2>/dev/null || true
    )"
    AZURE_STORAGE_ACCOUNT="${existing_storage_account}"
    if [[ -n "${existing_storage_share}" ]]; then
      AZURE_STORAGE_SHARE="${existing_storage_share}"
    fi
    log "Reusing existing env storage '${AZURE_STORAGE_ENV_NAME}' (account=${AZURE_STORAGE_ACCOUNT}, share=${AZURE_STORAGE_SHARE})."
    STORAGE_READY="true"
    return
  fi

  if az storage account show --name "${AZURE_STORAGE_ACCOUNT}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
    log "Reusing existing storage account: ${AZURE_STORAGE_ACCOUNT}"
  else
    log "Creating storage account: ${AZURE_STORAGE_ACCOUNT}"
    base_region="$(printf '%s' "${AZURE_LOCATION}" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
    candidates="${base_region} ${AZURE_LOCATION_FALLBACKS}"
    tried_regions=""
    storage_created=false
    selected_storage_region=""

    for region in ${candidates}; do
      if [[ " ${tried_regions} " == *" ${region} "* ]]; then
        continue
      fi
      tried_regions="${tried_regions} ${region}"

      log "Trying storage account region: ${region}"
      if storage_output="$(
        az storage account create \
          --name "${AZURE_STORAGE_ACCOUNT}" \
          --resource-group "${AZURE_RESOURCE_GROUP}" \
          --location "${region}" \
          --sku "${AZURE_STORAGE_SKU}" \
          --kind StorageV2 \
          --only-show-errors \
          --output none 2>&1
      )"; then
        storage_created=true
        selected_storage_region="${region}"
        break
      fi

      if printf '%s' "${storage_output}" | grep -Eq "RequestDisallowedByAzure|LocationNotAvailableForResourceType|InvalidLocation"; then
        log "Region ${region} denied by policy or unavailable for storage account, trying next."
        continue
      fi

      if printf '%s' "${storage_output}" | grep -Ei "already taken|AlreadyExists|StorageAccountAlreadyTaken" >/dev/null; then
        die "Storage account name '${AZURE_STORAGE_ACCOUNT}' is unavailable. Set AZURE_STORAGE_ACCOUNT to a unique value in azure/.env and rerun."
      fi

      die "Storage account creation failed in region '${region}': ${storage_output}"
    done

    if [[ "${storage_created}" != "true" ]]; then
      die "Storage account creation was denied in all tried regions (${tried_regions}). Set AZURE_LOCATION to an allowed region in azure/.env and rerun."
    fi

    log "Selected storage account region: ${selected_storage_region}"
  fi

  AZURE_STORAGE_KEY="$(az storage account keys list --resource-group "${AZURE_RESOURCE_GROUP}" --account-name "${AZURE_STORAGE_ACCOUNT}" --query '[0].value' -o tsv)"
  [[ -n "${AZURE_STORAGE_KEY}" ]] || die "Could not read storage account key for ${AZURE_STORAGE_ACCOUNT}."

  if [[ "$(az storage share exists --name "${AZURE_STORAGE_SHARE}" --account-name "${AZURE_STORAGE_ACCOUNT}" --account-key "${AZURE_STORAGE_KEY}" --query exists -o tsv)" != "true" ]]; then
    log "Creating Azure Files share: ${AZURE_STORAGE_SHARE}"
    az storage share create \
      --name "${AZURE_STORAGE_SHARE}" \
      --quota "${AZURE_STORAGE_QUOTA_GB}" \
      --account-name "${AZURE_STORAGE_ACCOUNT}" \
      --account-key "${AZURE_STORAGE_KEY}" \
      --only-show-errors \
      --output none
  else
    log "Reusing Azure Files share: ${AZURE_STORAGE_SHARE}"
  fi

  log "Registering Azure Files storage with Container Apps environment..."
  az containerapp env storage set \
    --name "${AZURE_CONTAINERAPPS_ENV}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --storage-name "${AZURE_STORAGE_ENV_NAME}" \
    --access-mode ReadWrite \
    --azure-file-account-name "${AZURE_STORAGE_ACCOUNT}" \
    --azure-file-account-key "${AZURE_STORAGE_KEY}" \
    --azure-file-share-name "${AZURE_STORAGE_SHARE}" \
    --only-show-errors \
    --output none

  STORAGE_READY="true"
}

attach_storage_volume() {
  local app_name="$1"
  local mount_path="$2"

  if [[ "${STORAGE_READY}" != "true" ]]; then
    return
  fi

  local volume_json
  local mount_json
  local app_id
  volume_json="$(printf '[{\"name\":\"%s\",\"storageType\":\"AzureFile\",\"storageName\":\"%s\"}]' "${AZURE_STORAGE_ENV_NAME}" "${AZURE_STORAGE_ENV_NAME}")"
  mount_json="$(printf '[{\"volumeName\":\"%s\",\"mountPath\":\"%s\"}]' "${AZURE_STORAGE_ENV_NAME}" "${mount_path}")"

  app_id="$(az containerapp show --name "${app_name}" --resource-group "${AZURE_RESOURCE_GROUP}" --query id -o tsv)"
  [[ -n "${app_id}" ]] || die "Could not resolve container app ID for ${app_name}."

  az resource update \
    --ids "${app_id}" \
    --set "properties.template.volumes=${volume_json}" \
    --set "properties.template.containers[0].volumeMounts=${mount_json}" \
    --only-show-errors \
    --output none
}

configure_storage

deploy_internal_app() {
  local internal_db_path="/app/database.db"
  if [[ "${STORAGE_READY}" == "true" ]]; then
    internal_db_path="${AZURE_STORAGE_MOUNT_PATH}/internal_api.db"
  fi
  local internal_db_url="sqlite:////${internal_db_path#/}"

  local -a internal_secrets=(
    "intkey=${INTERNAL_API_KEY}"
    "adminkey=${ADMIN_API_KEY}"
  )
  if [[ -n "${ACR_SECRET_NAME}" && -n "${ACR_PASSWORD}" ]]; then
    internal_secrets+=("${ACR_SECRET_NAME}=${ACR_PASSWORD}")
  fi
  local -a internal_env_vars=(
    DATABASE_URL="${internal_db_url}"
    DB_PATH="${internal_db_path}"
    NDMA_CAP_URL="https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
    HTTP_TIMEOUT_SECONDS="${INTERNAL_HTTP_TIMEOUT_SECONDS}"
    POLL_INTERVAL_SECONDS="${INTERNAL_POLL_INTERVAL_SECONDS}"
    REQUEST_RETRIES="${INTERNAL_REQUEST_RETRIES}"
    REQUEST_BACKOFF_SECONDS="${INTERNAL_REQUEST_BACKOFF_SECONDS}"
    SOURCE_STAGGER_SECONDS="${INTERNAL_SOURCE_STAGGER_SECONDS}"
    ENABLE_COLLECTOR_SNAPSHOT="${ENABLE_COLLECTOR_SNAPSHOT}"
    REQUIRE_API_KEY="true"
    API_KEY_HEADER="X-Internal-API-Key"
    ADMIN_API_KEY_HEADER="X-Admin-API-Key"
    INTERNAL_API_KEY="secretref:intkey"
    ADMIN_API_KEY="secretref:adminkey"
    ENABLE_SCHEDULER="true"
    RUN_SYNC_ON_STARTUP="true"
    INTERNAL_API_PORT="5000"
  )

  if [[ -n "${COLLECTOR_ALERT_JSON}" ]]; then
    internal_env_vars+=("COLLECTOR_ALERT_JSON=${COLLECTOR_ALERT_JSON}")
  fi

  if [[ -n "${OGD_DATASET_URL}" ]]; then
    internal_env_vars+=("OGD_DATASET_URL=${OGD_DATASET_URL}")
  fi
  if [[ -n "${OGD_API_KEY}" ]]; then
    internal_secrets+=("ogdapikey=${OGD_API_KEY}")
    internal_env_vars+=("OGD_API_KEY=secretref:ogdapikey")
  fi

  if [[ -n "${MOSDAC_ENDPOINT_URL}" ]]; then
    internal_env_vars+=("MOSDAC_ENDPOINT_URL=${MOSDAC_ENDPOINT_URL}")
  fi
  if [[ -n "${MOSDAC_API_TOKEN}" ]]; then
    internal_secrets+=("mosdactoken=${MOSDAC_API_TOKEN}")
    internal_env_vars+=("MOSDAC_API_TOKEN=secretref:mosdactoken")
  fi

  if az containerapp show --name "${AZURE_INTERNAL_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
    log "Updating internal API app: ${AZURE_INTERNAL_APP_NAME}"
    az containerapp update \
      --name "${AZURE_INTERNAL_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --image "${INTERNAL_IMAGE}" \
      --cpu 0.25 \
      --memory 0.5Gi \
      --min-replicas "${AZURE_INTERNAL_MIN_REPLICAS}" \
      --max-replicas "${AZURE_INTERNAL_MAX_REPLICAS}" \
      --set-env-vars "${internal_env_vars[@]}" \
      --only-show-errors \
      --output none
  else
    log "Creating internal API app: ${AZURE_INTERNAL_APP_NAME}"
    az containerapp create \
      --name "${AZURE_INTERNAL_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --environment "${AZURE_CONTAINERAPPS_ENV}" \
      --image "${INTERNAL_IMAGE}" \
      --ingress internal \
      --target-port 5000 \
      --registry-server "${ACR_LOGIN_SERVER}" \
      --registry-username "${ACR_USERNAME}" \
      --registry-password "${ACR_PASSWORD}" \
      --cpu 0.25 \
      --memory 0.5Gi \
      --min-replicas "${AZURE_INTERNAL_MIN_REPLICAS}" \
      --max-replicas "${AZURE_INTERNAL_MAX_REPLICAS}" \
      --secrets "${internal_secrets[@]}" \
      --env-vars "${internal_env_vars[@]}" \
      --only-show-errors \
      --output none
  fi

  if [[ "${STORAGE_READY}" == "true" ]]; then
    attach_storage_volume "${AZURE_INTERNAL_APP_NAME}" "${AZURE_STORAGE_MOUNT_PATH}"
  fi
}

deploy_main_app() {
  local internal_alerts_api_url="$1"
  local sqlite_db_path="/app/app.db"
  if [[ "${APP_PRIMARY_DB}" == "sqlite" && "${STORAGE_READY}" == "true" ]]; then
    sqlite_db_path="${AZURE_STORAGE_MOUNT_PATH}/app.db"
  fi
  local -a main_secrets=(
    "mainsecret=${MAIN_SECRET_KEY}"
    "intkey=${INTERNAL_API_KEY}"
  )
  if [[ -n "${ACR_SECRET_NAME}" && -n "${ACR_PASSWORD}" ]]; then
    main_secrets+=("${ACR_SECRET_NAME}=${ACR_PASSWORD}")
  fi
  local -a main_env_vars=(
    PORT="5000"
    APP_URL_SCHEME="https"
    APP_ENV="${AZURE_DEPLOY_PROFILE}"
    MOBILE_ALERTS_SOURCE_POLICY="auto_fallback"
    INTERNAL_API_SYNC_ON_ALERT_REQUEST="false"
    INTERNAL_API_AUTOSTART="false"
    INTERNAL_ALERTS_API_URL="${internal_alerts_api_url}"
    INTERNAL_ALERTS_API_KEY_HEADER="X-Internal-API-Key"
    INTERNAL_ALERTS_API_KEY="secretref:intkey"
    SECRET_KEY="secretref:mainsecret"
    SECURE_PASSWORD_MODE="true"
    STORE_PLAIN_PASSWORDS="false"
    EXPOSE_PLAIN_PASSWORDS="false"
  )

  if [[ -n "${GOOGLE_CLIENT_ID:-}" ]]; then
    main_env_vars+=("GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}")
  fi

  if [[ -n "${GOOGLE_REDIRECT_URI:-}" ]]; then
    main_env_vars+=("GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI}")
  fi

  if [[ -n "${GOOGLE_CLIENT_SECRET:-}" ]]; then
    main_secrets+=("googleclientsecret=${GOOGLE_CLIENT_SECRET}")
    main_env_vars+=("GOOGLE_CLIENT_SECRET=secretref:googleclientsecret")
  fi

  if [[ "${APP_PRIMARY_DB}" == "mysql" ]]; then
    main_secrets+=("dbpassword=${DB_PASSWORD}")
    main_env_vars+=(
      PRIMARY_DB="mysql"
      DB_HOST="${DB_HOST}"
      DB_USER="${DB_USER}"
      DB_NAME="${DB_NAME}"
      DB_PASSWORD="secretref:dbpassword"
      SQLITE_DB_PATH="/app/app.db"
    )
  else
    main_env_vars+=(
      PRIMARY_DB="sqlite"
      SQLITE_DB_PATH="${sqlite_db_path}"
    )
  fi

  if az containerapp show --name "${AZURE_MAIN_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
    log "Updating main app: ${AZURE_MAIN_APP_NAME}"
    az containerapp update \
      --name "${AZURE_MAIN_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --image "${MAIN_IMAGE}" \
      --cpu 0.25 \
      --memory 0.5Gi \
      --min-replicas "${AZURE_MAIN_MIN_REPLICAS}" \
      --max-replicas "${AZURE_MAIN_MAX_REPLICAS}" \
      --set-env-vars \
        "${main_env_vars[@]}" \
      --only-show-errors \
      --output none
  else
    log "Creating main app: ${AZURE_MAIN_APP_NAME}"
    az containerapp create \
      --name "${AZURE_MAIN_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --environment "${AZURE_CONTAINERAPPS_ENV}" \
      --image "${MAIN_IMAGE}" \
      --ingress external \
      --target-port 5000 \
      --registry-server "${ACR_LOGIN_SERVER}" \
      --registry-username "${ACR_USERNAME}" \
      --registry-password "${ACR_PASSWORD}" \
      --cpu 0.25 \
      --memory 0.5Gi \
      --min-replicas "${AZURE_MAIN_MIN_REPLICAS}" \
      --max-replicas "${AZURE_MAIN_MAX_REPLICAS}" \
      --secrets "${main_secrets[@]}" \
      --env-vars \
        "${main_env_vars[@]}" \
      --only-show-errors \
      --output none
  fi

  if [[ "${APP_PRIMARY_DB}" == "sqlite" && "${STORAGE_READY}" == "true" ]]; then
    attach_storage_volume "${AZURE_MAIN_APP_NAME}" "${AZURE_STORAGE_MOUNT_PATH}"
  fi
}

deploy_internal_app

INTERNAL_FQDN="$(az containerapp show --name "${AZURE_INTERNAL_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --query 'properties.configuration.ingress.fqdn' -o tsv)"
[[ -n "${INTERNAL_FQDN}" ]] || die "Could not read internal app FQDN."
INTERNAL_ALERTS_API_URL="https://${INTERNAL_FQDN}/api/alerts"

deploy_main_app "${INTERNAL_ALERTS_API_URL}"

MAIN_FQDN="$(az containerapp show --name "${AZURE_MAIN_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --query 'properties.configuration.ingress.fqdn' -o tsv)"
[[ -n "${MAIN_FQDN}" ]] || die "Could not read main app FQDN."

cat <<EOF

Deployment complete.

Main app URL:
  https://${MAIN_FQDN}

Internal API URL (private inside Container Apps environment):
  ${INTERNAL_ALERTS_API_URL}

Useful commands:
  az containerapp logs show -n ${AZURE_MAIN_APP_NAME} -g ${AZURE_RESOURCE_GROUP} --follow
  az containerapp logs show -n ${AZURE_INTERNAL_APP_NAME} -g ${AZURE_RESOURCE_GROUP} --follow

Replica profile:
  Main app min/max: ${AZURE_MAIN_MIN_REPLICAS}/${AZURE_MAIN_MAX_REPLICAS}
  Internal app min/max: ${AZURE_INTERNAL_MIN_REPLICAS}/${AZURE_INTERNAL_MAX_REPLICAS}
  Deploy profile: ${AZURE_DEPLOY_PROFILE}
EOF
