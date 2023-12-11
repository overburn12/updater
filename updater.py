import subprocess, json, os, random, re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, abort, Response, g, send_from_directory, redirect, url_for, session, flash
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

app = Flask(__name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('logged_in'):
            return f(*args, **kwargs)
        else:
            flash('You need to be logged in to view this page.')
            return redirect(url_for('admin_login'))
    return decorated_function

load_dotenv()
app.secret_key = os.getenv('SECRET_KEY')
admin_username = os.getenv('ADMIN_NAME')
admin_password = os.getenv('ADMIN_PASSWORD')
admin_password_hash = generate_password_hash(admin_password)  

servers = []
with open('servers.json', 'r') as file:
    servers = json.load(file)

#--------------------------------------------------------------------------------------
# functions
#--------------------------------------------------------------------------------------

def is_valid_server(server):
    return server in servers

def read_log(server):
    log_file_path = os.path.expanduser(f'~/{server}/data/update.log')
    try:
        with open(log_file_path, 'r') as file:
            return file.read()
    except FileNotFoundError:
        return f"Log file for server '{server}' not found."

def prepend_to_log(file_path, content):
    with open(file_path, 'r+') as file:
        existing_content = file.read()
        file.seek(0, 0)
        file.write(content + '\n' + existing_content)

def update_server(server):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    working_directory = os.path.expanduser(f'~/{server}')  # Constructs the path ~/server

    result = subprocess.run(
        'git pull',
        shell=True,
        capture_output=True,
        text=True,
        cwd=working_directory
    )

    log_content = "---------------------------------------------------------\n"
    log_content += f"Timestamp: {timestamp}\n"
    log_content += result.stdout
    log_content += result.stderr

    log_file_path = os.path.join(working_directory, 'data', 'update.log')  # Full path to the log file
    prepend_to_log(log_file_path, log_content)

    subprocess.run(f"sudo systemctl restart {server}", shell=True, text=True)

    return "success!"

#--------------------------------------------------------------------------------------
# admin routes
#--------------------------------------------------------------------------------------

@app.route('/')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == admin_username and check_password_hash(admin_password_hash, password):
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('admin_login.html')  # Your login page template

@app.route('/sql')
@admin_required
def sql_page():
    return render_template("admin_sql.html")

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

#--------------------------------------------------------------------------------------
# server api
#--------------------------------------------------------------------------------------

@app.route('/read_log', methods=['GET', 'POST'])
@admin_required
def get_server_log(server_name):
    return read_log(server_name)
    
@app.route('/execute-query', methods=['POST', 'GET'])
@admin_required
def execute_query():
    query_data = request.get_json()
    query = query_data['query']

    with db.engine.connect() as connection:
        result = connection.execute(text(query))
        columns = list(result.keys())  # Convert columns to a list

        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return jsonify({'columns': columns, 'rows': rows})

#--------------------------------------------------------------------------------------
# systemctl controls
#--------------------------------------------------------------------------------------

@app.route('/restart/<server>')
@admin_required
def restart_server(server):
    if not is_valid_server(server):
        return "Invalid server name.", 400

    try:
        subprocess.run(f'sudo systemctl restart {server}', shell=True, check=True)
        return "Server restarted successfully!"
    except subprocess.CalledProcessError:
        return "Failed to restart the server."

@app.route('/stop/<server>')
@admin_required
def stop_server(server):
    if not is_valid_server(server):
        return "Invalid server name.", 400

    try:
        subprocess.run(f'sudo systemctl stop {server}', shell=True, check=True)
        return "Server stopped successfully!"
    except subprocess.CalledProcessError:
        return "Failed to stop the server."

@app.route('/start/<server>')
@admin_required
def start_server(server):
    if not is_valid_server(server):
        return "Invalid server name.", 400

    try:
        subprocess.run(f'sudo systemctl start {server}', shell=True, check=True)
        return "Server started successfully!"
    except subprocess.CalledProcessError:
        return "Failed to start the server."

@app.route('/status/<server>')
@admin_required
def status_server(server):
    if not is_valid_server(server):
        return "Invalid server name.", 400
    try:
        result = subprocess.run(
            f'sudo systemctl status {server}',
            shell=True,
            capture_output=True,
            text=True
        )
        systemctl_status_log = result.stdout
        return render_template("admin_dashboard.html", log_content=systemctl_status_log)
    except subprocess.CalledProcessError:
        systemctl_status_log = "Failed to load the server status."
        return render_template("admin_dashboard.html", log_content=systemctl_status_log)                

#--------------------------------------------------------------------------------------

if __name__ == '__main__':
    host = os.environ.get('HOST')
    port = int(os.environ.get('PORT'))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.debug = debug
    app.run(host=host, port=port)
