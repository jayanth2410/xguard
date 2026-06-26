"""Script Manager Service - Create, store, and execute scripts remotely"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import os
import structlog

from app.core.config import settings
from app.services.remote_executor import RemoteExecutor, ConnectionConfig, ExecutionResult

logger = structlog.get_logger()


class ScriptManager:
    """Manages script creation, storage, and execution"""

    def __init__(self):
        self.storage_path_linux = settings.SCRIPT_STORAGE_PATH
        self.storage_path_windows = settings.SCRIPT_STORAGE_PATH_WINDOWS
        self.timeout = settings.EXECUTION_TIMEOUT

    def generate_script_filename(
        self,
        work_package_id: str,
        change_type: str,
        extension: str = "sh"
    ) -> str:
        """Generate unique script filename"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"mc_{change_type}_{work_package_id[:8]}_{timestamp}.{extension}"

    def get_storage_path(self, connection_type: str) -> str:
        """Get storage path based on connection type"""
        if connection_type == "winrm":
            return self.storage_path_windows
        return self.storage_path_linux

    def prepare_script_content(
        self,
        script: str,
        change_type: str,
        variables: Dict[str, Any] = None,
        connection_type: str = "ssh"
    ) -> str:
        """Prepare script content with variables and headers"""
        if connection_type == "winrm":
            # PowerShell script
            header = f"""# Maker-Checker Generated Script
# Generated: {datetime.utcnow().isoformat()}
# Change Type: {change_type}

$ErrorActionPreference = "Stop"

"""
            # Replace variables
            if variables:
                for key, value in variables.items():
                    header += f'${key} = "{value}"\n'
                header += "\n"

            return header + script

        else:
            # Bash script
            header = f"""#!/bin/bash
# Maker-Checker Generated Script
# Generated: {datetime.utcnow().isoformat()}
# Change Type: {change_type}

set -e

"""
            # Replace variables
            if variables:
                for key, value in variables.items():
                    header += f'{key}="{value}"\n'
                header += "\n"

            return header + script

    async def create_remote_script(
        self,
        connection: ConnectionConfig,
        script_content: str,
        filename: str
    ) -> Dict[str, Any]:
        """Create script file on remote host"""
        executor = RemoteExecutor(connection)

        try:
            if not executor.connect():
                return {
                    "success": False,
                    "error": f"Failed to connect to {connection.host}"
                }

            storage_path = self.get_storage_path(connection.connection_type)
            script_path = f"{storage_path}/{filename}" if connection.connection_type == "ssh" else f"{storage_path}\\{filename}"

            if connection.connection_type == "winrm":
                # Create directory and write file using PowerShell
                commands = f"""
$scriptPath = "{storage_path}"
if (-not (Test-Path $scriptPath)) {{
    New-Item -ItemType Directory -Path $scriptPath -Force | Out-Null
}}

$content = @'
{script_content}
'@

Set-Content -Path "{script_path}" -Value $content -Encoding UTF8
Write-Output "Script created at {script_path}"
"""
                result = executor.execute(commands, timeout=60)

            else:
                # Create directory and write file using bash
                # Escape single quotes in script content
                escaped_content = script_content.replace("'", "'\\''")
                commands = f"""
mkdir -p {storage_path}
cat > {script_path} << 'SCRIPT_EOF'
{script_content}
SCRIPT_EOF
chmod +x {script_path}
echo "Script created at {script_path}"
"""
                result = executor.execute(commands, timeout=60)

            if result.success:
                logger.info("script_created_remotely", path=script_path, host=connection.host)
                return {
                    "success": True,
                    "script_path": script_path,
                    "host": connection.host,
                    "output": result.stdout
                }
            else:
                logger.error("script_creation_failed", error=result.stderr)
                return {
                    "success": False,
                    "error": result.stderr or "Failed to create script"
                }

        except Exception as e:
            logger.exception("script_creation_error", error=str(e))
            return {"success": False, "error": str(e)}

        finally:
            executor.disconnect()

    async def execute_remote_script(
        self,
        connection: ConnectionConfig,
        script_path: str,
        timeout: int = None
    ) -> Dict[str, Any]:
        """Execute script on remote host"""
        executor = RemoteExecutor(connection)
        timeout = timeout or self.timeout

        try:
            if not executor.connect():
                return {
                    "success": False,
                    "error": f"Failed to connect to {connection.host}"
                }

            if connection.connection_type == "winrm":
                # Execute PowerShell script
                command = f"powershell.exe -ExecutionPolicy Bypass -File \"{script_path}\""
            else:
                # Execute bash script
                command = f"bash {script_path}"

            logger.info("executing_remote_script", path=script_path, host=connection.host)
            result = executor.execute(command, timeout=timeout)

            return {
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "script_path": script_path,
                "host": connection.host
            }

        except Exception as e:
            logger.exception("script_execution_error", error=str(e))
            return {"success": False, "error": str(e)}

        finally:
            executor.disconnect()

    async def create_and_execute(
        self,
        connection: ConnectionConfig,
        script_content: str,
        work_package_id: str,
        change_type: str,
        variables: Dict[str, Any] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Create script on remote host and execute it"""
        # Determine file extension
        extension = "ps1" if connection.connection_type == "winrm" else "sh"

        # Generate filename
        filename = self.generate_script_filename(work_package_id, change_type, extension)

        # Prepare script content
        prepared_script = self.prepare_script_content(
            script_content,
            change_type,
            variables,
            connection.connection_type
        )

        # Create script on remote host
        create_result = await self.create_remote_script(connection, prepared_script, filename)

        if not create_result["success"]:
            return create_result

        script_path = create_result["script_path"]

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "script_path": script_path,
                "message": "Script created but not executed (dry run)",
                "script_content": prepared_script
            }

        # Execute the script
        exec_result = await self.execute_remote_script(connection, script_path)

        return {
            **exec_result,
            "script_path": script_path,
            "script_content": prepared_script
        }

    async def cleanup_remote_script(
        self,
        connection: ConnectionConfig,
        script_path: str
    ) -> Dict[str, Any]:
        """Remove script from remote host after execution"""
        executor = RemoteExecutor(connection)

        try:
            if not executor.connect():
                return {"success": False, "error": "Connection failed"}

            if connection.connection_type == "winrm":
                command = f'Remove-Item -Path "{script_path}" -Force'
            else:
                command = f'rm -f {script_path}'

            result = executor.execute(command, timeout=30)

            return {
                "success": result.success,
                "message": f"Script {script_path} removed" if result.success else result.stderr
            }

        finally:
            executor.disconnect()


# Singleton instance
script_manager = ScriptManager()
