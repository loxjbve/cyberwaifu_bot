#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
IMAGE_NAME="${IMAGE_NAME:-cyber-waifu-bot}"
CONTAINER_NAME="${CONTAINER_NAME:-cyber-waifu-bot}"
HOST_PORT="${HOST_PORT:-8081}"
CONTAINER_PORT="${CONTAINER_PORT:-8081}"
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_DIR/backups}"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/reboot_update.log}"

PERSIST_PATHS=(
  "config"
  "data"
  "characters"
  "prompts"
  "agent/docs"
  ".env"
  "bot.log"
)

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required command not found: $1"
    exit 1
  fi
}

copy_path() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "$target")"
  cp -a "$source" "$target"
}

main() {
  exec >>"$LOG_FILE" 2>&1

  cd "$PROJECT_DIR"
  require_command git
  require_command docker
  require_command cp

  local timestamp backup_dir backup_archive
  timestamp="$(date '+%Y%m%d_%H%M%S')"
  backup_dir="$BACKUP_ROOT/$timestamp"
  backup_archive="$BACKUP_ROOT/cyberwaifu_backup_$timestamp.tar.gz"

  log "Starting reboot update in $PROJECT_DIR"
  mkdir -p "$backup_dir"

  log "Backing up persistent files"
  local path
  for path in "${PERSIST_PATHS[@]}"; do
    if [ -e "$path" ]; then
      copy_path "$path" "$backup_dir/$path"
      log "Backed up $path"
    else
      log "Skipped missing path: $path"
    fi
  done

  if command -v tar >/dev/null 2>&1; then
    tar -C "$backup_dir" -czf "$backup_archive" .
    log "Backup archive created: $backup_archive"
  else
    log "tar not found; directory backup kept at: $backup_dir"
  fi

  log "Fetching latest code from GitHub"
  git fetch --prune
  git pull --ff-only

  log "Restoring persistent files after git update"
  for path in "${PERSIST_PATHS[@]}"; do
    if [ -e "$backup_dir/$path" ]; then
      rm -rf -- "$path"
      copy_path "$backup_dir/$path" "$path"
      log "Restored $path"
    fi
  done

  mkdir -p config data characters prompts agent/docs

  log "Building Docker image without cache: $IMAGE_NAME"
  docker build --pull --no-cache -t "$IMAGE_NAME" .

  log "Replacing Docker container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "$HOST_PORT:$CONTAINER_PORT" \
    -v "$PROJECT_DIR/config:/app/config" \
    -v "$PROJECT_DIR/data:/app/data" \
    -v "$PROJECT_DIR/characters:/app/characters" \
    -v "$PROJECT_DIR/prompts:/app/prompts" \
    -v "$PROJECT_DIR/agent/docs:/app/agent/docs" \
    "$IMAGE_NAME"

  log "Pruning Docker build cache"
  docker builder prune -af

  log "Update complete. Container status:"
  docker ps --filter "name=^/${CONTAINER_NAME}$"
}

main "$@"
