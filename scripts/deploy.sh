#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
config_python=${SKILLSCENTRAL_PYTHON:-.venv/bin/python}
read -r project zone instance host_port < <("$config_python" scripts/deployment_config.py)
archive=$(mktemp /tmp/skillscentral-deploy.XXXXXX.tgz)
trap 'rm -f "$archive"' EXIT
chmod 600 "$archive"
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$archive" --exclude=.env.local --exclude=.venv --exclude=.git --exclude=__pycache__ --exclude=.pytest_cache --exclude=SkillsCentral.txt app demo docs scripts requirements.txt Dockerfile .dockerignore .env
gcloud compute scp "$archive" "$instance:/tmp/skillscentral-deploy.tgz" --project "$project" --zone "$zone" --quiet
gcloud compute ssh "$instance" --project "$project" --zone "$zone" --quiet --command "bash -s -- $host_port" <<'REMOTE'
set -euo pipefail
host_port=$1
sudo install -d -o "$(id -u)" -g "$(id -g)" /opt/skillscentral
tar -xzf /tmp/skillscentral-deploy.tgz -C /opt/skillscentral
rm /tmp/skillscentral-deploy.tgz
cd /opt/skillscentral
chmod 600 .env
sudo docker build --label owner=lionel_giavelli --label skip_deletion=yes -t skillscentral:local .
if sudo docker container inspect skillscentral >/dev/null 2>&1; then
  sudo docker stop skillscentral
  sudo docker rm skillscentral
fi
sudo docker run -d --name skillscentral --restart unless-stopped --label owner=lionel_giavelli --label skip_deletion=yes --mount type=bind,source=/opt/skillscentral/.env,target=/app/.env,readonly -p "$host_port:8084" skillscentral:local
for attempt in $(seq 1 20); do
  if curl --fail --silent "http://127.0.0.1:$host_port/api/health"; then exit 0; fi
  sleep 2
done
sudo docker logs --tail 40 skillscentral
exit 1
REMOTE
