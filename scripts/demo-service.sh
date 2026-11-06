#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
config_python=${SKILLSCENTRAL_PYTHON:-.venv/bin/python}
read -r project zone instance host_port < <("$config_python" scripts/deployment_config.py)
action=${1:-status}
case "$action" in
  start|stop|restart) command="sudo docker $action skillscentral" ;;
  status) command='sudo docker ps -a --filter name=^/skillscentral$ --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"' ;;
  logs) command='sudo docker logs --tail 80 skillscentral' ;;
  *) echo 'Usage: scripts/demo-service.sh start|stop|restart|status|logs' >&2; exit 2 ;;
esac
gcloud compute ssh "$instance" --project "$project" --zone "$zone" --quiet --command "$command"
