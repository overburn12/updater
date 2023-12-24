import subprocess, json, os, random, re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, abort, Response, g, send_from_directory, redirect, url_for, session, flash, render_template_string
from functools import wraps
from werkzeug.utils import safe_join
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
import sqlite3
from sqlalchemy import text

app = Flask(__name__)
self_name = 'updater'

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
root_directory = os.getenv('ROOT_DIRECTORY')

servers = []
with open('servers.json', 'r') as file:
    servers = json.load(file)

for server in servers:
    server_name = server['servername']
    db_path = server['dbpath']
    print(f"Server loaded: {server_name}, DB Path: {db_path}")


#--------------------------------------------------------------------------------------
# database loading
#--------------------------------------------------------------------------------------

def get_db(server):
    # Create the database directory if it doesn't exist
    db_dir = os.path.join(root_directory, server, 'instance')
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    db_path = os.path.join(db_dir, f"{server}.db")
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(db_path)
    return db

#--------------------------------------------------------------------------------------
# functions
#--------------------------------------------------------------------------------------

def is_valid_task(taskname):
    valid_tasks = ["start", "stop", "restart", "status"]
    return taskname in valid_tasks

def is_valid_server(server_name):
    for server in servers:
        if server['servername'] == server_name:
            return True
    return False

def read_log(server):
    log_file_path = os.path.join(root_directory, server, 'data', 'update.log')
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
    working_directory = os.path.join(root_directory, server) 

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

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/login', methods=['GET', 'POST'])
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

@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

#--------------------------------------------------------------------------------------
# server api
#--------------------------------------------------------------------------------------

@app.route('/admin/log/<servername>')
@admin_required
def get_server_log(servername):
    if not is_valid_server(servername):
        return jsonify({'error': f"Server '{servername}' not found."}), 404

    log_content = read_log(servername)
    return jsonify({'log': log_content})

@app.route('/admin/update/<servername>', methods=['GET','POST'])
@admin_required
def run_update(servername):
    if not is_valid_server(servername):
        return jsonify({'error': f"Server '{servername}' not found."}), 404
    
    if(servername == self_name):
        subprocess.run('python3 self_update.py', shell=True, text=True)
        return jsonify({'result': 'something went wrong if you see this'})
    else:
        update_result = update_server(servername)
        return jsonify({'result': update_result})


@app.route('/admin/sql/<servername>', methods=['POST', 'GET'])
@admin_required
def execute_query(servername):
    if not is_valid_server(servername):
        return jsonify({'error': f"Server '{servername}' not found."}), 404
    
    if request.method == 'GET':
        return render_template("admin_sql.html", servername=servername)
    else:
        query_data = request.get_json()
        query = query_data['query']

        # Establish a new database connection for this query
        db = get_db(servername)
        cursor = db.cursor()

        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
            db.commit()  # Commit if necessary (for INSERT, UPDATE, DELETE)

            # Prepare the results to be sent as JSON
            result = {
                'columns': columns,
                'rows': [dict(zip(columns, row)) for row in rows]
            }
        except Exception as e:
            db.rollback()  # Rollback in case of error
            result = {'error': str(e)}
        finally:
            db.close()  # Close the connection

        return jsonify(result)



#--------------------------------------------------------------------------------------
# image routes
#--------------------------------------------------------------------------------------

@app.route('/admin/img/<image_name>', methods=['GET'])
def serve_image(image_name):
    # Base directory where images are stored
    base_dir = '/home/overburn/tuftedfox/saved'

    # Construct the absolute path for the image
    absolute_path = os.path.join(base_dir, image_name)
    
    # Check if the file exists
    if not os.path.isfile(absolute_path):
        abort(404)  # Return a 404 error if the file doesn't exist

    print('Serving image from path: ', absolute_path)
    
    # Serve the image using send_from_directory
    return send_from_directory(base_dir, image_name)

@app.route('/admin/saved', methods=['GET'])
def gallery_view():
    # Base directory where images are stored
    base_dir = '/home/overburn/tuftedfox/saved'
    
    print('Gallery path: ', base_dir)

    # Check if the directory exists
    if not os.path.isdir(base_dir):
        abort(404)  # Return a 404 error if the directory doesn't exist

    # Create an empty list to store the HTML image tags
    image_tags = []
    
    # Iterate over the files in the directory
    for filename in os.listdir(base_dir):
        # Check if the file is an image
        if filename.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            # Generate the image source URL
            image_src = f"/admin/img/{filename}"
            
            # Create the HTML image tag and add it to the list
            image_tag = f"<img src=\"{image_src}\"> <br>"
            image_tags.append(image_tag)
    
    # Render the HTML template with the image tags
    html = "<html><body><center>"
    html += "\n".join(image_tags)
    html += "</center></body></html>"
    
    return render_template_string(html)

#--------------------------------------------------------------------------------------
# systemctl controls
#--------------------------------------------------------------------------------------

@app.route('/admin/systemctl/<taskname>/<servername>', methods=['POST', 'GET'])
@admin_required
def run_server_cmd(taskname,servername):
    if not is_valid_server(servername):
        return "Invalid server name.", 400
        
    if not is_valid_task(taskname):
        return "Invalid task name.", 400
    if(taskname=='status'):
        try:
            result = subprocess.run(['sudo','systemctl','status', servername],
                shell=True,
                capture_output=True,
                text=True
            )
            systemctl_status_log = result.stdout
            return jsonify({"status": systemctl_status_log})
        except subprocess.CalledProcessError:
            return jsonify({"error": "Failed to load the server status."})              
    else:
        try:
            subprocess.run(["sudo", "systemctl", taskname, servername], check=True)
        except subprocess.CalledProcessError:
            return jsonify({"error": "Failed to run the server task."}) 
    return "Server task completed."

#--------------------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    path = request.path
    return f"404: The requested path '{path}' was not found.", 404

#--------------------------------------------------------------------------------------

if __name__ == '__main__':
    host = os.environ.get('HOST')
    port = int(os.environ.get('PORT'))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.debug = debug
    app.run(host=host, port=port)
