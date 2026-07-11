#!/usr/bin/env bash
#
# One-command podman deployment for the trading automator.
#
#   Fresh machine (clones the repo for you, then deploys):
#     curl -fsSL https://raw.githubusercontent.com/mglaeser/trading-automator/HEAD/deploy.sh | bash
#
#   From an existing checkout:
#     ./deploy.sh              build image + (re)start the container
#     ./deploy.sh update       git pull, rebuild, restart
#     ./deploy.sh logs         follow container logs
#     ./deploy.sh status       show container state + app health
#     ./deploy.sh stop         stop the container (stays stopped across reboots)
#     ./deploy.sh uninstall    remove container + image (config is kept)
#
# Overridable via environment variables (for the curl|bash form put them on
# the bash side of the pipe: `curl ... | PORT=9000 bash`):
#   REPO_URL     git remote            (default: https://github.com/mglaeser/trading-automator.git)
#   BRANCH       branch to clone       (default: remote default branch)
#   INSTALL_DIR  bootstrap checkout    (default: ~/trading-automator)
#   PORT         host port for the UI  (default: 8000)
#   BIND_ADDR    host bind address     (default: 127.0.0.1 -- the API has no
#                auth; only set 0.0.0.0 behind a reverse proxy with auth)
#
# The whole script runs from main() so that `curl | bash` executes it only
# after it has been read completely (no partial-execution or stdin-eating
# hazards from commands inside).

set -euo pipefail

IMAGE="localhost/trading-automator:latest"
CONTAINER="trading-automator"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- locate the checkout, or bootstrap one (curl | bash mode) -----------------
#
# When executed as a file, deploy itself from the directory it lives in.
# When piped (BASH_SOURCE unset), NEVER guess from the current directory --
# always clone/update INSTALL_DIR. This prevents accidentally "deploying"
# an unrelated project that happens to contain a Dockerfile.
locate_repo() {
    local script_path="${BASH_SOURCE[0]:-}"
    if [ -n "$script_path" ] && [ -f "$script_path" ]; then
        repo_dir="$(cd "$(dirname "$script_path")" && pwd)"
        [ -f "$repo_dir/Dockerfile" ] \
            || die "no Dockerfile next to deploy.sh in $repo_dir -- corrupted checkout?"
        return
    fi
    command -v git >/dev/null 2>&1 || die "git is not installed"
    if [ -d "$INSTALL_DIR/.git" ]; then
        log "Updating existing checkout in $INSTALL_DIR"
        git -C "$INSTALL_DIR" pull --ff-only < /dev/null
    else
        log "Cloning $REPO_URL into $INSTALL_DIR"
        git clone ${BRANCH:+--branch "$BRANCH"} "$REPO_URL" "$INSTALL_DIR" < /dev/null
    fi
    repo_dir="$INSTALL_DIR"
}

# --- actions -------------------------------------------------------------------

build() {
    log "Building image $IMAGE"
    # --format=docker: the default OCI format silently drops the Dockerfile
    # HEALTHCHECK; the docker format keeps it so `podman ps` shows health.
    podman build --format=docker -t "$IMAGE" "$repo_dir"
}

run() {
    if podman container exists "$CONTAINER" 2>/dev/null; then
        log "Replacing existing container"
        podman rm -f "$CONTAINER" >/dev/null
    fi
    mkdir -p "$repo_dir/config" "$repo_dir/artifacts"

    local env_file_args=()
    [ -f "$repo_dir/.env" ] && env_file_args=(--env-file "$repo_dir/.env")

    log "Starting container $CONTAINER (web UI on ${BIND_ADDR}:${PORT})"
    # -e flags after --env-file win: WEB_HOST/WEB_PORT are pinned so a .env
    # meant for bare-metal runs cannot break the container's port mapping.
    podman run -d --name "$CONTAINER" \
        --restart=always \
        -p "${BIND_ADDR}:${PORT}:8000" \
        -v "$repo_dir/config:/app/config:Z" \
        -v "$repo_dir/artifacts:/app/artifacts:Z" \
        ${env_file_args[@]+"${env_file_args[@]}"} \
        -e AUTOSTART=true \
        -e WEB_HOST=0.0.0.0 \
        -e WEB_PORT=8000 \
        "$IMAGE" >/dev/null
}

persist() {
    # Make --restart=always survive reboots. Rootless podman needs the user
    # podman-restart service plus lingering; rootful needs the system service.
    # Best-effort: the container still runs without it.
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemd not found; container will not auto-start after a reboot"
        return 0
    fi
    if [ "$(id -u)" -eq 0 ]; then
        if systemctl enable --now podman-restart.service >/dev/null 2>&1; then
            log "Boot persistence enabled (podman-restart.service)"
        else
            warn "Could not enable podman-restart.service (no auto-start after reboot)"
        fi
    elif systemctl --user enable --now podman-restart.service >/dev/null 2>&1; then
        loginctl enable-linger "$(id -un)" >/dev/null 2>&1 \
            || warn "Could not enable lingering; container starts only after you log in"
        log "Boot persistence enabled (user podman-restart.service + linger)"
    else
        warn "Could not enable user podman-restart.service (no auto-start after reboot)"
    fi
}

stop_container() {
    podman stop "$CONTAINER"
    # podman-restart.service would resurrect a stopped restart=always
    # container at the next boot -- for a trading bot an explicit stop must
    # stick. Drop the policy in place (podman >= 4.5); on older podman remove
    # the container entirely (image and config/ are kept, ./deploy.sh
    # recreates it).
    if podman update --restart=no "$CONTAINER" >/dev/null 2>&1; then
        log "Container stopped; it stays stopped across reboots (restart: ./deploy.sh)"
    else
        podman rm "$CONTAINER" >/dev/null
        log "Container stopped and removed; recreate with: ./deploy.sh"
    fi
}

health() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsS --noproxy '*' "http://127.0.0.1:${PORT}/api/health" 2>/dev/null
    else
        podman exec "$CONTAINER" python -c "
import urllib.request as u
print(u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8000/api/health', timeout=5).read().decode())
" 2>/dev/null
    fi
}

status() {
    podman ps -a --filter "name=^${CONTAINER}\$" \
        --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    echo
    local out
    if out="$(health)"; then
        log "App health: $out"
    else
        warn "App is not answering on port $PORT yet"
    fi
}

info() {
    echo
    log "Deployment complete"
    echo
    echo "   Web UI:     http://${BIND_ADDR}:${PORT}"
    echo "   Logs:       ./deploy.sh logs"
    echo "   Status:     ./deploy.sh status"
    echo "   Update:     ./deploy.sh update"
    echo
    if grep -qs '"dry_run"[[:space:]]*:[[:space:]]*false' "$repo_dir/config/config.json"; then
        warn "dry-run is DISABLED in config/config.json -- this deployment trades live!"
    else
        echo "   The app runs in DRY-RUN mode: open the web UI, enter your"
        echo "   exchange/LLM API keys under Settings and save -- the trading"
        echo "   engine then starts automatically, but no order leaves the"
        echo "   house until you switch dry-run off."
    fi
    echo
    echo "   The web UI has no authentication and is bound to ${BIND_ADDR}."
    echo "   Keep it on 127.0.0.1 or put a reverse proxy with auth in front."
    echo
}

main() {
    REPO_URL="${REPO_URL:-https://github.com/mglaeser/trading-automator.git}"
    BRANCH="${BRANCH:-}"
    INSTALL_DIR="${INSTALL_DIR:-$HOME/trading-automator}"
    PORT="${PORT:-8000}"
    BIND_ADDR="${BIND_ADDR:-127.0.0.1}"

    command -v podman >/dev/null 2>&1 \
        || die "podman is not installed (see https://podman.io/docs/installation)"

    locate_repo
    cd "$repo_dir"

    local cmd="${1:-up}"
    case "$cmd" in
        up|deploy|"")
            build
            run
            persist
            info
            ;;
        update)
            log "Pulling latest changes"
            git -C "$repo_dir" pull --ff-only < /dev/null
            build
            run
            info
            ;;
        logs)
            exec podman logs -f "$CONTAINER"
            ;;
        status)
            status
            ;;
        stop)
            stop_container
            ;;
        uninstall)
            podman rm -f "$CONTAINER" 2>/dev/null || true
            podman rmi "$IMAGE" 2>/dev/null || true
            log "Container and image removed (config/ kept in $repo_dir)"
            ;;
        *)
            die "Unknown command '$cmd' (use: up | update | logs | status | stop | uninstall)"
            ;;
    esac
}

main "$@"
