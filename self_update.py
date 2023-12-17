import subprocess
from datetime import datetime

# Function to prepend content to a file
def prepend_to_file(filename, content):
    with open(filename, 'r+') as f:
        current_content = f.read()
        f.seek(0, 0)
        f.write(content + current_content)

# Get current timestamp
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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

subprocess.run('sudo systemctl restart updater', shell=True, text=True)