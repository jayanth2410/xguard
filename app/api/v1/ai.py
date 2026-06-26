"""AI Generation API endpoints"""
from typing import Optional, List
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
import re

router = APIRouter()


class GenerateScriptRequest(BaseModel):
    """Request to generate a script"""
    change_type: str
    title: str = ""
    description: str = ""
    target_hosts: List[str] = []
    target_host: str = ""


class GenerateScriptResponse(BaseModel):
    """Response with generated script"""
    script: str
    rollback: str
    language: str = "bash"


def extract_path(text: str, direction: str) -> Optional[str]:
    """Extract path after 'from' or 'to' keyword"""
    pattern = rf'{direction}\s+([/\w\-\.<>]+)'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def extract_time_schedule(text: str) -> dict:
    """Extract scheduling information from text"""
    schedule = {}

    days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    for day in days:
        if day in text.lower():
            schedule['day'] = day.capitalize()
            break

    time_pattern = r'(\d{1,2})[:\.](\d{2})\s*(AM|PM|am|pm)?'
    time_match = re.search(time_pattern, text)
    if time_match:
        hour = int(time_match.group(1))
        minute = time_match.group(2)
        meridiem = time_match.group(3)
        if meridiem and meridiem.upper() == 'PM' and hour < 12:
            hour += 12
        schedule['time'] = f"{hour:02d}:{minute}"

    return schedule


def wrap_with_file_creation(script_content: str, script_path: str, description: str = "") -> str:
    """Wrap script content with file creation and execution commands"""
    return f'''# ============================================
# Complete Execution Script
# Description: {description}
# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# ============================================

# Step 1: Create script directory
echo "Creating script directory..."
mkdir -p /tmp/makerchecker/scripts

# Step 2: Create the script file
echo "Creating script file: {script_path}"
cat > {script_path} << 'SCRIPT_EOF'
{script_content}
SCRIPT_EOF

# Step 3: Make script executable
echo "Making script executable..."
chmod +x {script_path}

# Step 4: Verify script was created
echo "Verifying script..."
ls -la {script_path}

# Step 5: Execute the script
echo "============================================"
echo "Executing script: {script_path}"
echo "============================================"
{script_path}

# Step 6: Capture exit code
EXIT_CODE=$?
echo "============================================"
echo "Script execution completed with exit code: $EXIT_CODE"
echo "Script location: {script_path}"
echo "============================================"

exit $EXIT_CODE
'''


@router.post("/generate-script", response_model=GenerateScriptResponse)
async def generate_script(request: GenerateScriptRequest):
    """Generate implementation script with file creation and execution steps"""

    desc = (request.description or "").lower()
    title = (request.title or "").lower()
    combined = f"{desc} {title}"

    script_content = ""
    rollback = ""
    language = "bash"

    # Generate script filename and path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_filename = f"mc_{request.change_type}_{timestamp}.sh"
    script_path = f"/tmp/makerchecker/scripts/{script_filename}"

    # Backup script detection
    if 'backup' in combined or 'archive' in combined:
        source_path = extract_path(request.description, 'from') or '/var/log'
        dest_path = extract_path(request.description, 'to') or '/backup'
        schedule = extract_time_schedule(request.description)

        script_content = f'''#!/bin/bash
# Backup Script
# Description: {request.description}
# Schedule: {schedule.get('day', 'N/A')} at {schedule.get('time', 'N/A')}

set -e

# Configuration
SOURCE_PATH="{source_path}"
BACKUP_BASE="{dest_path}"
WEEK_NUM=$(date +%V)
YEAR=$(date +%Y)
BACKUP_DIR="${{BACKUP_BASE}}/${{WEEK_NUM}}_${{YEAR}}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Starting backup process at $(date)"
echo "Source: $SOURCE_PATH"
echo "Destination: $BACKUP_DIR"

# Pre-checks
if [ ! -d "$SOURCE_PATH" ]; then
    echo "ERROR: Source path does not exist: $SOURCE_PATH"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Calculate source size
SOURCE_SIZE=$(du -sh "$SOURCE_PATH" 2>/dev/null | cut -f1 || echo "unknown")
echo "Source size: $SOURCE_SIZE"

# Perform backup with compression
echo "Creating backup archive..."
tar -czvf "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" "$SOURCE_PATH"

# Verify backup
if [ -f "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" ]; then
    BACKUP_SIZE=$(ls -lh "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" | awk '{{print $5}}')
    echo "Backup completed successfully"
    echo "Backup file: $BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
    echo "Backup size: $BACKUP_SIZE"
else
    echo "ERROR: Backup file not created!"
    exit 1
fi

# Cleanup old backups (keep last 4 weeks)
echo "Cleaning up old backups (older than 28 days)..."
find "$BACKUP_BASE" -name "backup_*.tar.gz" -mtime +28 -delete 2>/dev/null || true

echo "Backup process completed at $(date)"
'''

        rollback = f'''# Rollback Procedure for Backup

# To restore from backup:

1. List available backups:
   ls -la {dest_path}/

2. Extract the backup:
   tar -xzvf {dest_path}/WeekNo_Year/backup_timestamp.tar.gz -C /

3. Verify restored files:
   ls -la {source_path}

4. Check file permissions and ownership
5. Restart any dependent services if needed
'''

    # Service restart detection
    elif 'restart' in combined or 'service' in combined:
        services = ['nginx', 'apache', 'httpd', 'mysql', 'postgresql', 'redis', 'docker', 'tomcat']
        service_name = next((s for s in services if s in combined), 'nginx')

        script_content = f'''#!/bin/bash
# Service Management Script
# Description: {request.description}

set -e

SERVICE="{service_name}"

echo "=== Service Management: $SERVICE ==="
echo "Time: $(date)"

# Pre-check
echo "Current status:"
systemctl status $SERVICE --no-pager || true

# Restart service
echo "Restarting $SERVICE..."
systemctl restart $SERVICE

# Wait for service to stabilize
sleep 3

# Post-check
echo "Service status after restart:"
systemctl status $SERVICE --no-pager

echo "Service restart completed"
'''
        rollback = f'''# Rollback Procedure
1. Check service logs: journalctl -u {service_name} -n 50
2. If config was changed, restore previous config
3. Restart service: systemctl restart {service_name}
4. Verify service health
'''

    # Database changes
    elif request.change_type == 'database' or 'database' in combined or 'sql' in combined:
        language = "sql"
        script_content = f'''-- Database Change Script
-- Description: {request.description}

BEGIN TRANSACTION;

-- Your changes here

COMMIT;
'''
        rollback = '''-- Rollback Script
BEGIN TRANSACTION;
-- Reverse the changes
COMMIT;
'''
        # For database, return without file wrapper
        return GenerateScriptResponse(
            script=script_content.strip(),
            rollback=rollback.strip(),
            language=language
        )

    # Network/Firewall changes
    elif request.change_type == 'network' or 'firewall' in combined:
        script_content = f'''#!/bin/bash
# Network/Firewall Change Script
# Description: {request.description}

set -e

echo "=== Network Change Script ==="
echo "Time: $(date)"

# Pre-checks
echo "Current firewall rules:"
iptables -L -n --line-numbers 2>/dev/null || firewall-cmd --list-all 2>/dev/null || echo "No firewall detected"

# Apply changes here
# Example: firewall-cmd --add-port=8080/tcp --permanent
# Example: iptables -A INPUT -p tcp --dport 8080 -j ACCEPT

# Post-verification
echo "Network change completed"
'''
        rollback = '''# Rollback Procedure
1. Remove the added rules
2. firewall-cmd --reload or iptables -F
3. Verify connectivity is restored
'''

    # Default/Generic script
    else:
        script_content = f'''#!/bin/bash
# {request.change_type.capitalize()} Change Script
# Title: {request.title}
# Description: {request.description}

set -e

echo "=== Starting {request.change_type} change ==="
echo "Time: $(date)"

# Pre-checks
echo "Running pre-checks..."

# Implementation
echo "Applying changes..."
# TODO: Add implementation here

# Post-checks
echo "Running post-checks..."

echo "Change completed successfully at $(date)"
'''
        rollback = '''# Rollback Procedure
1. Identify what was changed
2. Restore previous configuration/state
3. Restart affected services
4. Verify system functionality
'''

    # Wrap the script content with file creation and execution
    full_script = wrap_with_file_creation(script_content.strip(), script_path, request.description)

    return GenerateScriptResponse(
        script=full_script.strip(),
        rollback=rollback.strip(),
        language=language
    )
