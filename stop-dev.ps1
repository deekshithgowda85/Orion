$ErrorActionPreference = "Stop"

docker compose -f "$PSScriptRoot\docker-compose.yml" down
