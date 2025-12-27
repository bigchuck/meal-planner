# meal_planner/data/email_manager.py
"""
Email manager for sending staged meal plans.

Handles SMTP configuration, rate limiting, and send logging.
"""
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime, timedelta


class EmailManager:
    """
    Manages email sending for staged meal plans.
    
    Provides SMTP email delivery with rate limiting and logging.
    """
    
    def __init__(self, config_file: Path, log_file: Path):
        """
        Initialize email manager.
        
        Args:
            config_file: Path to email_config.json
            log_file: Path to send log file
        """
        self.config_file = config_file
        self.log_file = log_file
        self._config: Optional[dict] = None
        self._validation_errors: List[str] = []
    
    def load_config(self) -> bool:
        """
        Load and validate email configuration.
        
        Returns:
            True if config loaded successfully
        """
        self._validation_errors.clear()
        self._config = None
        
        if not self.config_file.exists():
            self._validation_errors.append(
                f"Email config not found: {self.config_file}\n"
                f"Create it with your Gmail app password.\n"
                f"See documentation for setup instructions."
            )
            return False
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except json.JSONDecodeError as e:
            self._validation_errors.append(f"Invalid JSON in email config: {e}")
            return False
        except Exception as e:
            self._validation_errors.append(f"Error reading email config: {e}")
            return False
        
        # Validate required fields
        required = ['smtp_server', 'smtp_port', 'email_address', 'app_password']
        missing = [f for f in required if f not in self._config]
        
        if missing:
            self._validation_errors.append(
                f"Email config missing required fields: {', '.join(missing)}"
            )
            return False
        
        return True
    
    def get_error_message(self) -> str:
        """Get formatted error message."""
        return "\n".join(self._validation_errors)
    
    def send(self, subject: str, body_lines: List[str]) -> Tuple[bool, str]:
        """
        Send email with staged content.
        
        Args:
            subject: Email subject line
            body_lines: List of body content lines
        
        Returns:
            (success, message) tuple
        """
        if not self._config:
            return False, "Email not configured"
        
        # Check rate limit
        allowed, reason = self._check_rate_limit()
        if not allowed:
            return False, reason
        
        # Build email
        msg = MIMEText('\n'.join(body_lines), 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = self._config['email_address']
        msg['To'] = self._config['email_address']
        
        # Send via SMTP
        try:
            with smtplib.SMTP(self._config['smtp_server'], 
                            self._config['smtp_port']) as server:
                server.starttls()
                server.login(self._config['email_address'], 
                           self._config['app_password'])
                server.send_message(msg)
            
            # Log successful send
            self._log_send(subject, len(body_lines), success=True)
            
            return True, "Email sent successfully"
            
        except smtplib.SMTPAuthenticationError:
            error = "SMTP authentication failed. Check app password."
            self._log_send(subject, len(body_lines), success=False, error=error)
            return False, error
        except smtplib.SMTPException as e:
            error = f"SMTP error: {e}"
            self._log_send(subject, len(body_lines), success=False, error=error)
            return False, error
        except Exception as e:
            error = f"Unexpected error: {e}"
            self._log_send(subject, len(body_lines), success=False, error=error)
            return False, error
    
    def _check_rate_limit(self) -> Tuple[bool, str]:
        """
        Check if sending is allowed based on rate limit.
        
        Returns:
            (allowed, reason) tuple
        """
        rate_limit = self._config.get('rate_limit_per_hour', 10)
        
        # Get recent sends from log
        recent_sends = self._get_recent_sends(hours=1)
        
        if len(recent_sends) >= rate_limit:
            return False, (
                f"Rate limit exceeded: {len(recent_sends)}/{rate_limit} emails "
                f"sent in the last hour. Please wait."
            )
        
        return True, ""
    
    def _get_recent_sends(self, hours: int) -> List[dict]:
        """
        Get send log entries from the last N hours.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            List of send log entries
        """
        if not self.log_file.exists():
            return []
        
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry = json.loads(line)
                        timestamp = datetime.fromisoformat(entry['timestamp'])
                        
                        if timestamp > cutoff and entry.get('success'):
                            recent.append(entry)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        # Skip malformed entries
                        continue
        except Exception:
            # If can't read log, allow send (fail open)
            return []
        
        return recent
    
    def _log_send(self, subject: str, line_count: int, success: bool, 
                  error: str = None) -> None:
        """
        Log send attempt to file.
        
        Args:
            subject: Email subject
            line_count: Number of body lines
            success: Whether send succeeded
            error: Error message if failed
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'subject': subject,
            'line_count': line_count,
            'success': success,
            'recipient': self._config['email_address']
        }
        
        if error:
            entry['error'] = error
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            # Log failure shouldn't block send
            pass
    
    def get_configured_address(self) -> Optional[str]:
        """Get configured email address."""
        if self._config:
            return self._config.get('email_address')
        return None
    
    def get_rate_limit_status(self) -> Tuple[int, int]:
        """
        Get current rate limit status.
        
        Returns:
            (sent_count, limit) tuple for last hour
        """
        limit = self._config.get('rate_limit_per_hour', 10) if self._config else 10
        recent = self._get_recent_sends(hours=1)
        return len(recent), limit