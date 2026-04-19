#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_CONFIG_FILE="${SCRIPT_DIR}/.env"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

CONFIG_FILE="${1:-${DEFAULT_CONFIG_FILE}}"
if [[ -n "${1:-}" && ! -f "${CONFIG_FILE}" ]]; then
  die "Config file not found: ${CONFIG_FILE}"
fi

if [[ -f "${CONFIG_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
  set +a
fi

export AZURE_CONFIG_DIR="${AZURE_CONFIG_DIR:-${PROJECT_ROOT}/.azure}"
mkdir -p "${AZURE_CONFIG_DIR}"

: "${AZURE_RESOURCE_GROUP:=rg-projectz-student}"

if ! command -v az >/dev/null 2>&1; then
  die "Azure CLI (az) is not installed."
fi

if ! az account show --only-show-errors >/dev/null 2>&1; then
  az login --use-device-code --output none
fi

if [[ -n "${AZURE_SUBSCRIPTION_ID:-}" ]]; then
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --only-show-errors
fi

printf "Deleting resource group '%s'...\n" "${AZURE_RESOURCE_GROUP}"
az group delete \
  --name "${AZURE_RESOURCE_GROUP}" \
  --yes \
  --no-wait \
  --only-show-errors

echo "Delete started in background. This removes apps, registry, and related resources."

