"""Remote Execution Service - SSH and WinRM execution"""
from typing import Optional, Dict, Any, Generator
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class ConnectionConfig:
    """Remote connection configuration"""
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    private_key: Optional[str] = None
    connection_type: str = "ssh"  # ssh or winrm


@dataclass
class ExecutionResult:
    """Result of remote command execution"""
    exit_code: int
    stdout: str
    stderr: str
    success: bool


class RemoteExecutor:
    """Execute commands on remote hosts via SSH or WinRM"""

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._ssh_client = None
        self._winrm_session = None

    def connect(self) -> bool:
        """Establish connection to remote host"""
        if self.config.connection_type == "ssh":
            return self._connect_ssh()
        elif self.config.connection_type == "winrm":
            return self._connect_winrm()
        return False

    def _connect_ssh(self) -> bool:
        """Connect via SSH"""
        try:
            import paramiko
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
            }

            if self.config.private_key:
                from io import StringIO
                pkey = paramiko.RSAKey.from_private_key(StringIO(self.config.private_key))
                connect_kwargs["pkey"] = pkey
            elif self.config.password:
                connect_kwargs["password"] = self.config.password

            self._ssh_client.connect(**connect_kwargs, timeout=30)
            logger.info("ssh_connected", host=self.config.host)
            return True

        except Exception as e:
            logger.error("ssh_connection_failed", host=self.config.host, error=str(e))
            return False

    def _connect_winrm(self) -> bool:
        """Connect via WinRM"""
        try:
            import winrm
            self._winrm_session = winrm.Session(
                f"http://{self.config.host}:{self.config.port}/wsman",
                auth=(self.config.username, self.config.password),
                transport="ntlm"
            )
            # Test connection
            result = self._winrm_session.run_cmd("echo", ["connected"])
            logger.info("winrm_connected", host=self.config.host)
            return result.status_code == 0

        except Exception as e:
            logger.error("winrm_connection_failed", host=self.config.host, error=str(e))
            return False

    def execute(self, command: str, timeout: int = 300) -> ExecutionResult:
        """Execute a command on the remote host"""
        if self.config.connection_type == "ssh":
            return self._execute_ssh(command, timeout)
        elif self.config.connection_type == "winrm":
            return self._execute_winrm(command, timeout)
        return ExecutionResult(exit_code=-1, stdout="", stderr="Invalid connection type", success=False)

    def _execute_ssh(self, command: str, timeout: int) -> ExecutionResult:
        """Execute command via SSH"""
        if not self._ssh_client:
            return ExecutionResult(exit_code=-1, stdout="", stderr="Not connected", success=False)

        try:
            stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_str = stdout.read().decode("utf-8", errors="replace")
            stderr_str = stderr.read().decode("utf-8", errors="replace")

            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                success=(exit_code == 0)
            )
        except Exception as e:
            return ExecutionResult(exit_code=-1, stdout="", stderr=str(e), success=False)

    def _execute_winrm(self, command: str, timeout: int) -> ExecutionResult:
        """Execute command via WinRM"""
        if not self._winrm_session:
            return ExecutionResult(exit_code=-1, stdout="", stderr="Not connected", success=False)

        try:
            # Determine if it's PowerShell or CMD
            if command.strip().startswith("powershell") or "$" in command:
                result = self._winrm_session.run_ps(command)
            else:
                result = self._winrm_session.run_cmd(command)

            return ExecutionResult(
                exit_code=result.status_code,
                stdout=result.std_out.decode("utf-8", errors="replace") if result.std_out else "",
                stderr=result.std_err.decode("utf-8", errors="replace") if result.std_err else "",
                success=(result.status_code == 0)
            )
        except Exception as e:
            return ExecutionResult(exit_code=-1, stdout="", stderr=str(e), success=False)

    def execute_script(self, script: str, timeout: int = 600) -> ExecutionResult:
        """Execute a multi-line script"""
        if self.config.connection_type == "ssh":
            # For SSH, execute as a single command with bash
            command = f"bash -c '{script}'" if not script.startswith("#!") else script
            return self._execute_ssh(command, timeout)
        elif self.config.connection_type == "winrm":
            # For WinRM, use PowerShell
            return self._execute_winrm(script, timeout)
        return ExecutionResult(exit_code=-1, stdout="", stderr="Invalid connection type", success=False)

    def disconnect(self):
        """Close the connection"""
        if self._ssh_client:
            try:
                self._ssh_client.close()
                logger.info("ssh_disconnected", host=self.config.host)
            except:
                pass
            self._ssh_client = None

        self._winrm_session = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class LocalExecutor:
    """Execute commands locally (for testing/simulation)"""

    def execute(self, command: str, timeout: int = 300) -> ExecutionResult:
        """Execute command locally"""
        import subprocess
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                text=True
            )
            return ExecutionResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                success=(result.returncode == 0)
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(exit_code=-1, stdout="", stderr="Command timed out", success=False)
        except Exception as e:
            return ExecutionResult(exit_code=-1, stdout="", stderr=str(e), success=False)
