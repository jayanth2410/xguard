"""Flask routes for web UI"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
import httpx
from app.core.config import settings

main_bp = Blueprint('main', __name__)
workflow_bp = Blueprint('workflow', __name__)
api_bp = Blueprint('api', __name__)

API_BASE_URL = "http://127.0.0.1:8000"


@api_bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy_api(path):
    """Proxy API requests to FastAPI backend"""
    url = f"{API_BASE_URL}/api/v1/{path}"

    # Forward the request
    try:
        with httpx.Client(timeout=30.0) as client:
            if request.method == 'GET':
                resp = client.get(url, params=request.args)
            elif request.method == 'POST':
                resp = client.post(url, json=request.get_json(silent=True), params=request.args)
            elif request.method == 'PUT':
                resp = client.put(url, json=request.get_json(silent=True), params=request.args)
            elif request.method == 'DELETE':
                resp = client.delete(url, params=request.args)
            elif request.method == 'PATCH':
                resp = client.patch(url, json=request.get_json(silent=True), params=request.args)
            else:
                return jsonify({"error": "Method not allowed"}), 405

            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get('content-type', 'application/json')
            )
    except httpx.ConnectError:
        return jsonify({"error": "API server not available"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main_bp.route('/')
def index():
    """Dashboard page"""
    return render_template('index.html')


@main_bp.route('/work-packages')
def work_packages():
    """List work packages"""
    return render_template('work_packages/list.html')


@main_bp.route('/work-packages/new')
def new_work_package():
    """Create new work package form"""
    return render_template('work_packages/new.html')


@main_bp.route('/work-packages/<work_package_id>')
def view_work_package(work_package_id):
    """View work package details"""
    return render_template('work_packages/view.html', work_package_id=work_package_id)


@main_bp.route('/work-packages/<work_package_id>/edit')
def edit_work_package(work_package_id):
    """Edit work package"""
    return render_template('work_packages/edit.html', work_package_id=work_package_id)


@workflow_bp.route('/review')
def review_queue():
    """Review queue page"""
    return render_template('workflow/review.html')


@workflow_bp.route('/validation-queue')
def validation_queue():
    """Validation queue page - shows work packages in validation"""
    return render_template('workflow/validation_queue.html')


@workflow_bp.route('/review/<work_package_id>')
def review_work_package(work_package_id):
    """Review a specific work package"""
    return render_template('workflow/review_detail.html', work_package_id=work_package_id)


@workflow_bp.route('/validation/<work_package_id>')
def validation_session(work_package_id):
    """Validation session page"""
    return render_template('workflow/validation.html', work_package_id=work_package_id)


@workflow_bp.route('/execute/<work_package_id>')
def execution_page(work_package_id):
    """Execution page"""
    return render_template('workflow/execution.html', work_package_id=work_package_id)


@workflow_bp.route('/audit/<work_package_id>')
def audit_trail(work_package_id):
    """Audit trail page"""
    return render_template('workflow/audit.html', work_package_id=work_package_id)


@main_bp.route('/servicenow')
def servicenow_page():
    """ServiceNow integration page"""
    return render_template('servicenow/index.html')


@main_bp.route('/servicenow/import/<incident_number>')
def servicenow_import(incident_number):
    """Import incident from ServiceNow"""
    return render_template('servicenow/import.html', incident_number=incident_number)
