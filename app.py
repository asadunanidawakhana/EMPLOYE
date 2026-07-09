from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from functools import wraps
import jwt

load_dotenv()

app = Flask(__name__)
CORS(app)

# Supabase Setup
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Mock data for demo - UPDATED CREDENTIALS
DEMO_USER = {
    'id': '1',
    'email': 'admin@macdigital.hr',
    'name': 'Admin User',
    'password': 'ADMIN123'
}

# Auth Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Invalid token format'}), 401

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_email = data['email']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401

        return f(*args, **kwargs)
    return decorated

# Health Check
@app.route('/healthz', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# Authentication
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    # Check against demo credentials
    if email == DEMO_USER['email'] and password == DEMO_USER['password']:
        token = jwt.encode({
            'user_id': DEMO_USER['id'],
            'email': DEMO_USER['email'],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, JWT_SECRET, algorithm='HS256')

        return jsonify({
            'token': token,
            'user': {
                'id': DEMO_USER['id'],
                'email': DEMO_USER['email'],
                'name': DEMO_USER['name']
            }
        }), 200

    return jsonify({'message': 'Invalid credentials'}), 401

# Dashboard Stats
@app.route('/api/dashboard/stats', methods=['GET'])
@token_required
def get_dashboard_stats():
    try:
        if not supabase:
            return get_mock_dashboard_stats()

        # Fetch all data
        employees = supabase.table('employees').select('*').execute().data
        departments = supabase.table('departments').select('*').execute().data
        positions = supabase.table('positions').select('*').execute().data
        attendance = supabase.table('attendance').select('*').execute().data

        # Calculate stats
        total_employees = len(employees)
        active_employees = len([e for e in employees if e.get('status') == 'active'])
        total_departments = len(departments)
        open_positions = len([p for p in positions if not p.get('filled', False)])

        today = datetime.now().date().isoformat()
        absent_today = len([a for a in attendance if a.get('date') == today and a.get('status') == 'absent'])

        # Department distribution
        dept_dist = {}
        for emp in employees:
            dept_id = emp.get('department_id')
            if dept_id:
                dept = next((d for d in departments if d['id'] == dept_id), None)
                if dept:
                    dept_name = dept['name']
                    dept_dist[dept_name] = dept_dist.get(dept_name, 0) + 1

        department_distribution = [{'name': name, 'count': count} for name, count in dept_dist.items()]

        # Employees by position
        employees_by_position = []
        for emp in employees[:10]:
            position = next((p for p in positions if p['id'] == emp.get('position_id')), None)
            employees_by_position.append({
                'id': emp['id'],
                'name': emp.get('name', 'Unknown'),
                'position': position['title'] if position else 'Unassigned',
                'profile_pic': emp.get('profile_pic')
            })

        return jsonify({
            'total_employees': total_employees,
            'active_employees': active_employees,
            'total_departments': total_departments,
            'open_positions': open_positions,
            'absent_today': absent_today,
            'department_distribution': department_distribution,
            'employees_by_position': employees_by_position
        }), 200

    except Exception as e:
        return get_mock_dashboard_stats()

def get_mock_dashboard_stats():
    return jsonify({
        'total_employees': 145,
        'active_employees': 138,
        'total_departments': 8,
        'open_positions': 12,
        'absent_today': 5,
        'department_distribution': [
            {'name': 'Engineering', 'count': 45},
            {'name': 'Sales', 'count': 35},
            {'name': 'Marketing', 'count': 20},
            {'name': 'HR', 'count': 15},
            {'name': 'Finance', 'count': 30}
        ],
        'employees_by_position': [
            {'id': '1', 'name': 'John Smith', 'position': 'Senior Developer', 'profile_pic': None},
            {'id': '2', 'name': 'Sarah Johnson', 'position': 'Product Manager', 'profile_pic': None},
            {'id': '3', 'name': 'Mike Chen', 'position': 'Designer', 'profile_pic': None}
        ]
    }), 200

# EMPLOYEES ROUTES
@app.route('/api/employees', methods=['GET'])
@token_required
def get_employees():
    try:
        if not supabase:
            return jsonify([]), 200
        response = supabase.table('employees').select('*').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/employees', methods=['POST'])
@token_required
def create_employee():
    try:
        if not supabase:
            data = request.get_json()
            data['id'] = int(datetime.now().timestamp() * 1000)
            return jsonify(data), 201

        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('email'):
            return jsonify({'error': 'Name and email are required'}), 400
        
        response = supabase.table('employees').insert(data).execute()
        return jsonify(response.data[0] if response.data else {}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/employees/<int:id>', methods=['PUT'])
@token_required
def update_employee(id):
    try:
        if not supabase:
            return jsonify({}), 200

        data = request.get_json()
        
        # Remove empty/null values to allow partial updates
        data = {k: v for k, v in data.items() if v is not None and v != ''}
        
        response = supabase.table('employees').update(data).eq('id', id).execute()
        return jsonify(response.data[0] if response.data else {}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/employees/<int:id>', methods=['DELETE'])
@token_required
def delete_employee(id):
    try:
        if not supabase:
            return jsonify({'deleted': True}), 200

        supabase.table('employees').delete().eq('id', id).execute()
        return jsonify({'deleted': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# DEPARTMENTS ROUTES
@app.route('/api/departments', methods=['GET'])
@token_required
def get_departments():
    try:
        if not supabase:
            return jsonify([]), 200
        response = supabase.table('departments').select('*').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/departments', methods=['POST'])
@token_required
def create_department():
    try:
        if not supabase:
            data = request.get_json()
            data['id'] = int(datetime.now().timestamp() * 1000)
            return jsonify(data), 201

        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Department name is required'}), 400
        
        response = supabase.table('departments').insert(data).execute()
        return jsonify(response.data[0] if response.data else {}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/departments/<int:id>', methods=['PUT'])
@token_required
def update_department(id):
    try:
        if not supabase:
            return jsonify({}), 200

        data = request.get_json()
        
        # Remove empty/null values to allow partial updates
        data = {k: v for k, v in data.items() if v is not None and v != ''}
        
        response = supabase.table('departments').update(data).eq('id', id).execute()
        return jsonify(response.data[0] if response.data else {}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/departments/<int:id>', methods=['DELETE'])
@token_required
def delete_department(id):
    try:
        if not supabase:
            return jsonify({'deleted': True}), 200

        supabase.table('departments').delete().eq('id', id).execute()
        return jsonify({'deleted': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POSITIONS ROUTES
@app.route('/api/positions', methods=['GET'])
@token_required
def get_positions():
    try:
        if not supabase:
            return jsonify([]), 200
        response = supabase.table('positions').select('*').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions', methods=['POST'])
@token_required
def create_position():
    try:
        if not supabase:
            data = request.get_json()
            data['id'] = int(datetime.now().timestamp() * 1000)
            return jsonify(data), 201

        data = request.get_json()
        
        # Validate required fields
        if not data.get('title'):
            return jsonify({'error': 'Position title is required'}), 400
        
        response = supabase.table('positions').insert(data).execute()
        return jsonify(response.data[0] if response.data else {}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions/<int:id>', methods=['PUT'])
@token_required
def update_position(id):
    try:
        if not supabase:
            return jsonify({}), 200

        data = request.get_json()
        
        # Remove empty/null values to allow partial updates
        data = {k: v for k, v in data.items() if v is not None and v != ''}
        
        response = supabase.table('positions').update(data).eq('id', id).execute()
        return jsonify(response.data[0] if response.data else {}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions/<int:id>', methods=['DELETE'])
@token_required
def delete_position(id):
    try:
        if not supabase:
            return jsonify({'deleted': True}), 200

        supabase.table('positions').delete().eq('id', id).execute()
        return jsonify({'deleted': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ATTENDANCE ROUTES
@app.route('/api/attendance', methods=['GET'])
@token_required
def get_attendance():
    try:
        if not supabase:
            return jsonify([]), 200
        response = supabase.table('attendance').select('*').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/attendance', methods=['POST'])
@token_required
def create_attendance():
    try:
        if not supabase:
            data = request.get_json()
            data['id'] = int(datetime.now().timestamp() * 1000)
            return jsonify(data), 201

        data = request.get_json()
        
        # Validate required fields
        if not data.get('employee_id') or not data.get('date'):
            return jsonify({'error': 'Employee ID and date are required'}), 400
        
        response = supabase.table('attendance').insert(data).execute()
        return jsonify(response.data[0] if response.data else {}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/attendance/<int:id>', methods=['PUT'])
@token_required
def update_attendance(id):
    try:
        if not supabase:
            return jsonify({}), 200

        data = request.get_json()
        
        # Remove empty/null values to allow partial updates
        data = {k: v for k, v in data.items() if v is not None and v != ''}
        
        response = supabase.table('attendance').update(data).eq('id', id).execute()
        return jsonify(response.data[0] if response.data else {}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/attendance/<int:id>', methods=['DELETE'])
@token_required
def delete_attendance(id):
    try:
        if not supabase:
            return jsonify({'deleted': True}), 200

        supabase.table('attendance').delete().eq('id', id).execute()
        return jsonify({'deleted': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# LEAVES ROUTES
@app.route('/api/leaves', methods=['GET'])
@token_required
def get_leaves():
    try:
        if not supabase:
            return jsonify([]), 200
        response = supabase.table('leaves').select('*').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/leaves', methods=['POST'])
@token_required
def create_leave():
    try:
        if not supabase:
            data = request.get_json()
            data['id'] = int(datetime.now().timestamp() * 1000)
            return jsonify(data), 201

        data = request.get_json()
        
        # Validate required fields
        if not data.get('employee_id') or not data.get('start_date') or not data.get('end_date'):
            return jsonify({'error': 'Employee ID, start date, and end date are required'}), 400
        
        response = supabase.table('leaves').insert(data).execute()
        return jsonify(response.data[0] if response.data else {}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/leaves/<int:id>', methods=['PUT'])
@token_required
def update_leave(id):
    try:
        if not supabase:
            return jsonify({}), 200

        data = request.get_json()
        
        # Remove empty/null values to allow partial updates
        data = {k: v for k, v in data.items() if v is not None and v != ''}
        
        response = supabase.table('leaves').update(data).eq('id', id).execute()
        return jsonify(response.data[0] if response.data else {}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/leaves/<int:id>', methods=['DELETE'])
@token_required
def delete_leave(id):
    try:
        if not supabase:
            return jsonify({'deleted': True}), 200

        supabase.table('leaves').delete().eq('id', id).execute()
        return jsonify({'deleted': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# PAYROLL ROUTES
@app.route('/api/payroll', methods=['GET'])
@token_required
def get_payroll():
    try:
        if not supabase:
            return jsonify([]), 200
        response = supabase.table('payroll').select('*').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payroll', methods=['POST'])
@token_required
def create_payroll():
    try:
        if not supabase:
            data = request.get_json()
            data['id'] = int(datetime.now().timestamp() * 1000)
            return jsonify(data), 201

        data = request.get_json()
        
        # Validate required fields
        if not data.get('employee_id') or not data.get('month'):
            return jsonify({'error': 'Employee ID and month are required'}), 400
        
        response = supabase.table('payroll').insert(data).execute()
        return jsonify(response.data[0] if response.data else {}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payroll/<int:id>', methods=['PUT'])
@token_required
def update_payroll(id):
    try:
        if not supabase:
            return jsonify({}), 200

        data = request.get_json()
        
        # Remove empty/null values to allow partial updates
        data = {k: v for k, v in data.items() if v is not None and v != ''}
        
        response = supabase.table('payroll').update(data).eq('id', id).execute()
        return jsonify(response.data[0] if response.data else {}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payroll/<int:id>', methods=['DELETE'])
@token_required
def delete_payroll(id):
    try:
        if not supabase:
            return jsonify({'deleted': True}), 200

        supabase.table('payroll').delete().eq('id', id).execute()
        return jsonify({'deleted': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Serve frontend
@app.route('/')
def index():
    from flask import send_from_directory
    return send_from_directory('templates', 'index.html')

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
