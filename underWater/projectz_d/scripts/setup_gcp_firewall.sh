#!/usr/bin/env bash
set -euo pipefail

# Open HTTP/HTTPS firewall rules in Google Cloud for ProjectZ VM.
# Run from any machine where gcloud CLI is authenticated.

RULE_NAME="${RULE_NAME:-projectz-allow-web}"
NETWORK="${NETWORK:-default}"
TARGET_TAG="${TARGET_TAG:-projectz-web}"
PROJECT_ID="${PROJECT_ID:-}"
APPLY_TAG="${APPLY_TAG:-true}"
INSTANCE_NAME="${INSTANCE_NAME:-}"
INSTANCE_ZONE="${INSTANCE_ZONE:-}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required. Install Google Cloud SDK first."
  exit 1
fi

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "PROJECT_ID not set."
  echo "Use: PROJECT_ID=<your-project-id> ./scripts/setup_gcp_firewall.sh"
  exit 1
fi

echo "Using project: $PROJECT_ID"
echo "Ensuring firewall rule: $RULE_NAME"

if gcloud compute firewall-rules describe "$RULE_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute firewall-rules update "$RULE_NAME" \
    --project "$PROJECT_ID" \
    --network "$NETWORK" \
    --allow tcp:80,tcp:443 \
    --target-tags "$TARGET_TAG" \
    --direction INGRESS \
    --priority 1000 \
    --source-ranges 0.0.0.0/0
  echo "Updated existing firewall rule: $RULE_NAME"
else
  gcloud compute firewall-rules create "$RULE_NAME" \
    --project "$PROJECT_ID" \
    --network "$NETWORK" \
    --allow tcp:80,tcp:443 \
    --target-tags "$TARGET_TAG" \
    --direction INGRESS \
    --priority 1000 \
    --source-ranges 0.0.0.0/0
  echo "Created firewall rule: $RULE_NAME"
fi

if [[ "$APPLY_TAG" == "true" ]]; then
  if [[ -z "$INSTANCE_NAME" || -z "$INSTANCE_ZONE" ]]; then
    echo "Skipping VM tag apply (INSTANCE_NAME or INSTANCE_ZONE missing)."
    echo "To apply tag automatically run with:"
    echo "  INSTANCE_NAME=<vm-name> INSTANCE_ZONE=<zone> ./scripts/setup_gcp_firewall.sh"
  else
    echo "Applying network tag '$TARGET_TAG' to VM '$INSTANCE_NAME'"

    EXISTING_TAGS="$(gcloud compute instances describe "$INSTANCE_NAME" \
      --zone "$INSTANCE_ZONE" \
      --project "$PROJECT_ID" \
      --format='value(tags.items)' 2>/dev/null || true)"

    if [[ -n "$EXISTING_TAGS" ]]; then
      if [[ ",$EXISTING_TAGS," == *",$TARGET_TAG,"* ]]; then
        NEW_TAGS="$EXISTING_TAGS"
      else
        NEW_TAGS="$EXISTING_TAGS,$TARGET_TAG"
      fi
    else
      NEW_TAGS="$TARGET_TAG"
    fi

    gcloud compute instances add-tags "$INSTANCE_NAME" \
      --zone "$INSTANCE_ZONE" \
      --project "$PROJECT_ID" \
      --tags "$NEW_TAGS"

    echo "Tag applied."
  fi
fi

echo ""
echo "Firewall setup complete."
echo "Rule: $RULE_NAME"
echo "Ports: 80, 443"
echo "Target tag: $TARGET_TAG"
