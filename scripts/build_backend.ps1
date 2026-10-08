$ErrorActionPreference = "Stop"

Write-Host "Installing PyInstaller..."
pip install pyinstaller

Write-Host "Building Assembly Backend with PyInstaller..."

# PyInstaller command
# -y: yes to all
# --onedir: single folder (better startup time)
# --name: assembly_backend
# --add-data: include models.yaml
# --hidden-import: include uvicorn, fastapi, sqlalchemy, pydantic, and other dynamic imports

pyinstaller -y --name "assembly_backend" `
    --add-data "models.yaml;." `
    --hidden-import "uvicorn.logging" `
    --hidden-import "uvicorn.loops" `
    --hidden-import "uvicorn.loops.auto" `
    --hidden-import "uvicorn.protocols" `
    --hidden-import "uvicorn.protocols.http" `
    --hidden-import "uvicorn.protocols.http.auto" `
    --hidden-import "uvicorn.protocols.websockets" `
    --hidden-import "uvicorn.protocols.websockets.auto" `
    --hidden-import "uvicorn.lifespan" `
    --hidden-import "uvicorn.lifespan.on" `
    --hidden-import "sqlalchemy.ext.asyncio" `
    --hidden-import "sqlalchemy.sql.default_comparator" `
    --hidden-import "pydantic" `
    --hidden-import "sqlite3" `
    --hidden-import "keyring.backends.Windows" `
    src/main.py

Write-Host "Build Complete!"
