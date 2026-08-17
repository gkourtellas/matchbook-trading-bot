import os  
import sys  
from datetime import datetime  
  
class PrintLogger:  
    def __init__(self, log_file_path):  
        self.terminal = sys.stdout  
        self.log = open(log_file_path, "a", encoding="utf-8")  
  
    def write(self, message):  
        self.terminal.write(message)  
        self.log.write(message)  
        self.log.flush()  
  
    def flush(self):  
        self.terminal.flush()  
        self.log.flush()  
  
def setup_logging():  
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")  
    os.makedirs(log_dir, exist_ok=True)  
    date_str = datetime.now().strftime("%Y-%m-%d")  
    return os.path.join(log_dir, f"execution_{date_str}.log")  
  
def install_print_logger():  
    log_file = setup_logging()  
    logger = PrintLogger(log_file)  
    sys.stdout = logger  
    sys.stderr = logger