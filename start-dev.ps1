$ErrorActionPreference = "Stop"

docker compose -f docker-compose.yml up -d postgres redis temporal temporal-ui
Set-Location "$PSScriptRoot\frontend"
npm run dev:mock
