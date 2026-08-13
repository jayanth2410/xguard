"""Flask routes for web UI"""
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, Response
import httpx
from app.core.config import settings

main_bp = Blueprint('main', __name__)
workflow_bp = Blueprint('workflow', __name__)
api_bp = Blueprint('api', __name__)

API_BASE_URL = f"http://{settings.FASTAPI_HOST}:{settings.FASTAPI_PORT}"


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Create a Flask session after the API verifies credentials."""
    if request.method == 'GET':
        if session.get('user'):
            return redirect(url_for('main.index'))
        return render_template('auth/login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{API_BASE_URL}/api/v1/users/login",
                json={"username": username, "password": password},
            )
        if response.status_code == 200:
            user = response.json()
            session.clear()
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'full_name': user.get('full_name') or user['username'],
                'role': user['role'],
            }
            destination = request.args.get('next', '/')
            if not destination.startswith('/') or destination.startswith('//'):
                destination = '/'
            return redirect(destination)
        error = response.json().get('detail', 'Invalid username or password')
    except httpx.RequestError:
        error = 'The XGuard API is unavailable. Start the API server and try again.'
    return render_template('auth/login.html', error=error, username=username), 401


@main_bp.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))


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


@workflow_bp.route('/review/<work_package_id>')
def review_work_package(work_package_id):
    """Review a specific work package"""
    return render_template('workflow/review_detail.html', work_package_id=work_package_id)


@workflow_bp.route('/execute/<work_package_id>')
def execution_page(work_package_id):
    """Execution page"""
    return render_template('workflow/execution.html', work_package_id=work_package_id)


@workflow_bp.route('/execute')
def execution_queue():
    """Approved work packages available for execution."""
    return render_template('workflow/execution_queue.html')


@workflow_bp.route('/audit/<work_package_id>')
def audit_trail(work_package_id):
    """Audit trail page"""
    return render_template('workflow/audit.html', work_package_id=work_package_id)


@main_bp.route('/servicenow')
def servicenow_page():
    """ServiceNow integration page"""
    return render_template('servicenow/index.html')


