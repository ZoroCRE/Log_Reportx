import json
import os
import datetime
import requests
import smtplib
import shutil
from pathlib import Path
from email.mime.text import MIMEText

def get_current_date():
    """Get current date in YYYY-MM-DD format."""
    return datetime.datetime.now().strftime("%Y-%m-%d")

def aggregate_logs(logs_dir="C:\\Logs"):
    """Aggregate .log and .txt files for today into a dated folder and merge into current_date_error.txt."""
    try:
        logs_dir = Path(logs_dir)
        if not logs_dir.exists():
            raise FileNotFoundError(f"Logs directory {logs_dir} does not exist")

        current_date = get_current_date()
        date_folder = logs_dir / current_date
        date_folder.mkdir(exist_ok=True)
        summary_file = date_folder / f"{current_date}_error.txt"

        # Clear previous summary file if it exists
        if summary_file.exists():
            summary_file.unlink()

        processed_files = []
        # Iterate through server subdirectories, excluding the date folder
        for server_dir in logs_dir.iterdir():
            if server_dir.is_dir() and server_dir.name != current_date:
                # Look for both .log and .txt files with today's date
                for ext in ('*.log', '*.txt'):
                    for log_file in server_dir.glob(f"{current_date}{ext}"):
                        if log_file.is_file():
                            # Copy file to date folder
                            dest_file = date_folder / f"{server_dir.name}_{log_file.name}"
                            shutil.copy(log_file, dest_file)
                            processed_files.append(str(dest_file))

        # Merge files into current_date_error.txt
        if processed_files:
            with open(summary_file, 'w', encoding='utf-8') as dest:
                for log_file in sorted(processed_files):
                    with open(log_file, 'r', encoding='utf-8') as src:
                        dest.write(src.read() + '\n')

        return str(summary_file), date_folder, processed_files

    except Exception as e:
        print(f"Error during log aggregation: {str(e)}")
        return None, None, []

def analyze_logs(summary_file, date_folder):
    """Analyze current_date_error.txt and create errorless.txt with error/warning lines."""
    try:
        if not Path(summary_file).exists():
            raise FileNotFoundError(f"Summary file {summary_file} not found")

        error_count = 0
        warning_count = 0
        error_lines = []

        with open(summary_file, 'r', encoding='utf-8') as f:
            for line in f:
                line_lower = line.lower()
                if "error" in line_lower or "warning" in line_lower:
                    error_lines.append(line.strip())
                    if "error" in line_lower:
                        error_count += 1
                    if "warning" in line_lower:
                        warning_count += 1

        # Write to errorless.txt
        with open(date_folder / "errorless.txt", 'w', encoding='utf-8') as errorless:
            for line in error_lines:
                errorless.write(line + '\n')

        print(f"Found {error_count} lines with 'ERROR' and {warning_count} lines with 'WARNING'")
        return error_lines, error_count, warning_count

    except Exception as e:
        print(f"Error during log analysis: {str(e)}")
        return [], 0, 0

def process_errorless(logs_dir, date_folder, processed_files, error_lines, error_count, warning_count):
    """Process errorless.txt, post to ShareText.io if lines > 10, and send email."""
    try:
        current_date = get_current_date()
        errorless_file = date_folder / "errorless.txt"
        if not errorless_file.exists():
            raise FileNotFoundError(f"Errorless file {errorless_file} not found")

        # Count lines in errorless.txt
        with open(errorless_file, 'r', encoding='utf-8') as f:
            line_count = sum(1 for line in f)

        # Prepare report data
        report = {
            "report_date": current_date,
            "total_files_processed": len(processed_files),
            "error_count": error_count,
            "warning_count": warning_count,
            "critical_errors": [f"{current_date} ERROR: {line}" for line in error_lines if "error" in line.lower()]
        }

        share_url = None
        # Post to ShareText.io if line count > 10
        if line_count > 10:
            # Convert report to text for ShareText.io
            report_text = json.dumps(report, indent=4, ensure_ascii=False)
            try:
                # Hypothetical ShareText.io API endpoint
                response = requests.post(
                    "https://sharetext.io/api/share",
                    headers={"Content-Type": "text/plain"},
                    data=report_text.encode('utf-8')
                )
                if response.status_code == 200:
                    share_url = response.json().get("url", "unknown")
                    print(f"Report shared successfully, URL: {share_url}")
                else:
                    print(f"Failed to share report: {response.status_code}")
            except requests.RequestException as e:
                print(f"Error posting to ShareText.io: {str(e)}")

        # Send email
        send_email(share_url, current_date)

        return share_url

    except Exception as e:
        print(f"Error in error processing: {str(e)}")
        return None

def send_email(share_url, current_date):
    """Send email notification with report details."""
    try:
        msg = MIMEText(
            f"Hello Dev,\n\n"
            f"This is reported today {current_date}\n\n"
            f"Reported link: {share_url if share_url else 'unknown'}"
        )
        msg['Subject'] = f"Daily Log Report - {current_date}"
        msg['From'] = ""  # Replace with your email
        msg['To'] = "salah.mahmoud.dev@gmail.com"  # Replace with company email

        # Configure SMTP server (example using Gmail)
        with smtplib.SMTP('', 587) as server:
            server.starttls()
            server.login("", "")  # Replace with your credentials
            server.send_message(msg)
        print("Email sent successfully")

    except Exception as e:
        print(f"Error sending email: {str(e)}")

def main():
    """Main function to orchestrate log processing and error handling."""
    try:
        # Step 1: Aggregate logs
        summary_file, date_folder, processed_files = aggregate_logs()
        if not summary_file or not date_folder:
            raise RuntimeError("Log aggregation failed")

        # Step 2: Analyze logs
        error_lines, error_count, warning_count = analyze_logs(summary_file, date_folder)

        # Step 3: Process errorless.txt and send alerts
        share_url = process_errorless("C:\\Logs", date_folder, processed_files, error_lines, error_count, warning_count)

        print(f"Processing complete. Share URL: {share_url if share_url else 'None'}")

    except Exception as e:
        print(f"Fatal error in main process: {str(e)}")

if __name__ == "__main__":
    main()