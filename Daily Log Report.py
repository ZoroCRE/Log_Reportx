import json
import os
import datetime
import smtplib
import shutil
import socket
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Constants
LOGS_DIR = "C:\\Logs"
ERROR_KEYWORDS = ["error", "warning", "critical", "failure"]  # Extendable list of keywords to search
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "EMAIL@gmail.com"
SMTP_PASSWORD = "PASS_SMTP"  # Gmail App Password
RECIPIENT_EMAIL = "Email To Receiving the report"
EMAIL_LINE_THRESHOLD = 10  # Threshold for sending email and generating JSON report

def get_current_date():
    """Get current date in YYYY-MM-DD format."""
    return datetime.datetime.now().strftime("%Y-%m-%d")

def aggregate_logs(logs_dir=LOGS_DIR):
    """
    Aggregate .log and .txt files for today into a dated folder and merge into current_date_error.txt.
    Returns: (summary_file_path, date_folder_path, processed_files_list, server_file_mapping)
    """
    try:
        logs_dir = Path(logs_dir)
        if not logs_dir.exists():
            raise FileNotFoundError(f"Logs directory {logs_dir} does not exist")
        print(f"Processing logs directory: {logs_dir}")

        current_date = get_current_date()
        date_folder = logs_dir / current_date
        date_folder.mkdir(exist_ok=True)
        print(f"Created/using date folder: {date_folder}")
        summary_file = date_folder / f"{current_date}_error.txt"

        # Clear previous summary file if it exists
        if summary_file.exists():
            summary_file.unlink()
            print(f"Cleared existing summary file: {summary_file}")

        processed_files = []
        server_file_map = {}
        # Iterate through server subdirectories, excluding the date folder
        for server_dir in logs_dir.iterdir():
            if server_dir.is_dir() and server_dir.name != current_date:
                print(f"Checking server directory: {server_dir}")
                for ext in ('*.log', '*.txt'):
                    for log_file in server_dir.glob(f"{current_date}{ext}"):
                        if log_file.is_file():
                            dest_file = date_folder / f"{server_dir.name}_{log_file.name}"
                            shutil.copy(log_file, dest_file)
                            processed_files.append(str(dest_file))
                            server_file_map[str(dest_file)] = server_dir.name
                            print(f"Copied {log_file} to {dest_file}")

        if not processed_files:
            print("No .log or .txt files found for today in any server directories")
            return None, date_folder, [], {}

        # Merge files into current_date_error.txt
        with open(summary_file, 'w', encoding='utf-8') as dest:
            for log_file in sorted(processed_files):
                with open(log_file, 'r', encoding='utf-8') as src:
                    dest.write(src.read() + '\n')
                print(f"Merged {log_file} into {summary_file}")

        return str(summary_file), date_folder, processed_files, server_file_map

    except Exception as e:
        print(f"Error during log aggregation: {str(e)}")
        return None, None, [], {}

def analyze_logs(summary_file, date_folder, processed_files, server_file_map):
    """
    Analyze current_date_error.txt and create errorless.txt with server prefix for lines containing specified keywords.
    Counts occurrences of each keyword in ERROR_KEYWORDS.
    Returns: (error_lines_list, keyword_counts_dict)
    """
    try:
        if not summary_file or not Path(summary_file).exists():
            raise FileNotFoundError(f"Summary file {summary_file} not found")
        print(f"Analyzing summary file: {summary_file}")

        keyword_counts = {keyword: 0 for keyword in ERROR_KEYWORDS}
        error_lines = []

        # Read each processed file to associate lines with server names
        for log_file in sorted(processed_files):
            server_name = server_file_map.get(log_file, "Unknown")
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in ERROR_KEYWORDS):
                        error_lines.append((server_name, line.strip()))
                        for keyword in ERROR_KEYWORDS:
                            if keyword in line_lower:
                                keyword_counts[keyword] += 1

        # Write to errorless.txt with server prefix
        errorless_file = date_folder / "errorless.txt"
        with open(errorless_file, 'w', encoding='utf-8') as errorless:
            for server_name, line in error_lines:
                errorless.write(f"{server_name}: {line}\n")
        print(f"Created errorless.txt at: {errorless_file}")

        # Clean up: Delete copied files and summary file
        for log_file in processed_files:
            try:
                Path(log_file).unlink()
                print(f"Deleted copied file: {log_file}")
            except Exception as e:
                print(f"Error deleting {log_file}: {str(e)}")
        try:
            Path(summary_file).unlink()
            print(f"Deleted summary file: {summary_file}")
        except Exception as e:
            print(f"Error deleting {summary_file}: {str(e)}")

        print(f"Keyword counts: {', '.join(f'{k}: {v}' for k, v in keyword_counts.items())}")
        return error_lines, keyword_counts

    except Exception as e:
        print(f"Error during log analysis: {str(e)}")
        return [], {keyword: 0 for keyword in ERROR_KEYWORDS}

def process_errorless(logs_dir, date_folder, processed_files, error_lines, keyword_counts):
    """
    Process errorless.txt, save report as JSON if > 10 lines, and send email with JSON attached.
    Returns: report_file_path or None
    """
    try:
        current_date = get_current_date()
        errorless_file = date_folder / "errorless.txt"
        if not errorless_file.exists():
            raise FileNotFoundError(f"Errorless file {errorless_file} not found")
        print(f"Processing errorless file: {errorless_file}")

        # Count lines in errorless.txt
        with open(errorless_file, 'r', encoding='utf-8') as f:
            line_count = sum(1 for line in f)
        print(f"Errorless.txt contains {line_count} lines")

        # Prepare report data
        report = {
            "report_date": current_date,
            "total_files_processed": len(processed_files),
            "keyword_counts": keyword_counts,
            "critical_errors": [f"{server_name}: {line}" for server_name, line in error_lines if "error" in line.lower()]
        }

        # Save report as JSON file if errorless.txt has more than 10 lines
        report_file = None
        if line_count > EMAIL_LINE_THRESHOLD:
            report_file = date_folder / f"{current_date}_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=4, ensure_ascii=False)
            print(f"Saved report to: {report_file}")
            # Send email with JSON file attached
            send_email(report_file, current_date, keyword_counts.get("error", 0))
        else:
            print(f"No email sent (less than or equal to {EMAIL_LINE_THRESHOLD} error/warning lines)")

        return str(report_file) if report_file else None

    except Exception as e:
        print(f"Error in error processing: {str(e)}")
        return None

def send_email(report_file, current_date, error_count):
    """Send email with the JSON report file attached, including error_count in the subject."""
    try:
        # Create a multipart message
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = f"Daily Log Report - {current_date} - {error_count} Errors"

        # Add body to email
        body = f"Hello Dev,\n\nThis is the log report for {current_date}.\nThe report is attached as a JSON file.\n\nBest regards,\nYour Log Processor"
        msg.attach(MIMEText(body, 'plain'))

        # Attach the JSON file
        if report_file and Path(report_file).exists():
            with open(report_file, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={Path(report_file).name}'
            )
            msg.attach(part)
            print(f"Attached {report_file} to email")
        else:
            print(f"Warning: Report file {report_file} not found for attachment")

        # Configure SMTP server with timeout and retry
        for attempt in range(1, 4):  # Try up to 3 times
            try:
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(msg)
                print(f"Email sent successfully on attempt {attempt}")
                return
            except socket.timeout:
                print(f"SMTP connection timed out on attempt {attempt}")
                if attempt == 3:
                    raise Exception("Failed to connect to SMTP server after 3 attempts")
            except smtplib.SMTPAuthenticationError:
                raise Exception("SMTP authentication failed. Check your email and App Password.")
            except Exception as e:
                print(f"SMTP error on attempt {attempt}: {str(e)}")
                if attempt == 3:
                    raise Exception(f"Failed to send email after 3 attempts: {str(e)}")

    except Exception as e:
        print(f"Error sending email: {str(e)}")

def main():
    """Main function to orchestrate log processing and error handling."""
    try:
        # Step 1: Aggregate logs
        summary_file, date_folder, processed_files, server_file_map = aggregate_logs()
        if not summary_file or not date_folder:
            print("Skipping analysis and error processing due to aggregation failure")
            return

        # Step 2: Analyze logs and clean up
        error_lines, keyword_counts = analyze_logs(summary_file, date_folder, processed_files, server_file_map)

        # Step 3: Process errorless.txt and send alerts
        report_path = process_errorless(LOGS_DIR, date_folder, processed_files, error_lines, keyword_counts)

        print(f"Processing complete. Report saved at: {report_path if report_path else 'None'}")

    except Exception as e:
        print(f"Fatal error in main process: {str(e)}")

if __name__ == "__main__":
    main()
