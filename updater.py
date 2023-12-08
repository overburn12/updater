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



#--------------------------------------------------------------------------------------
# functions
#--------------------------------------------------------------------------------------

# Function to prepend content to a file
def prepend_to_file(filename, content):
    with open(filename, 'r+') as f:
        current_content = f.read()
        f.seek(0, 0)
        f.write(content + current_content)

# Get current timestamp
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def update_server(server):
    with open('data/update.log', 'a') as logfile:
        result = subprocess.run(
            'git pull',
            shell=True,
            capture_output=True,  # Capture the command output
            text=True
        )

        # Construct the log content
        log_content = "---------------------------------------------------------\n"
        log_content += f"Timestamp: {timestamp}\n"
        log_content += result.stdout
        log_content += result.stderr

        # Prepend the log content to the file
        prepend_to_file('data/update.log', log_content)

    subprocess.run('sudo systemctl restart tuftedfox', shell=True, text=True)

#--------------------------------------------------------------------------------------
# routes
#--------------------------------------------------------------------------------------

@app.route('/')
@admin_required
def admin_dashboard():
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'POST'])
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

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

#--------------------------------------------------------------------------------------

if __name__ == '__main__':
    host = os.environ.get('HOST')
    port = int(os.environ.get('PORT'))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.debug = debug
    app.run(host=host, port=port)
