import customtkinter as ctk
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import threading
import time

# --- Scraper Logic ---

class EmailScraper:
    """
    A class to handle the email scraping logic.
    It runs in a separate thread to avoid freezing the UI.
    """
    def __init__(self, base_url, status_callback, result_callback):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.emails_found = set()
        self.visited_urls = set()
        self.urls_to_visit = {base_url}
        self.status_callback = status_callback
        self.result_callback = result_callback
        self.is_scraping = True
        self.max_pages = 50 # Limit to prevent scraping forever

    def _is_valid_url(self, url):
        """Check if the URL is within the same domain and hasn't been visited."""
        try:
            parsed_url = urlparse(url)
            is_same_domain = parsed_url.netloc == self.domain
            is_http_or_https = parsed_url.scheme in ['http', 'https']
            is_not_visited = url not in self.visited_urls
            return is_same_domain and is_http_or_https and is_not_visited
        except:
            return False

    def _find_emails_on_page(self, soup):
        """Extract all email addresses from the page's text."""
        # Regex for finding email addresses
        email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        page_text = soup.get_text()
        found_emails = re.findall(email_regex, page_text)
        return found_emails

    def _crawl_page(self, url):
        """Crawl a single page, find emails, and add new links to the queue."""
        try:
            self.status_callback(f"Visiting: {url}")
            response = requests.get(url, timeout=5, headers={'User-Agent': 'MyCoolEmailScraper'})
            response.raise_for_status() # Raise an exception for bad status codes

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find emails on the current page
            new_emails = self._find_emails_on_page(soup)
            for email in new_emails:
                if email not in self.emails_found:
                    self.emails_found.add(email)
                    self.status_callback(f"Found Email: {email}")

            # Find all links on the page
            for link in soup.find_all('a', href=True):
                absolute_url = urljoin(self.base_url, link['href'])
                if self._is_valid_url(absolute_url):
                    self.urls_to_visit.add(absolute_url)
        
        except requests.exceptions.RequestException as e:
            self.status_callback(f"Error visiting {url}: {e}")
        except Exception as e:
            self.status_callback(f"An unexpected error occurred: {e}")

    def start_scraping(self):
        """Main method to start the scraping process."""
        pages_crawled = 0
        while self.urls_to_visit and pages_crawled < self.max_pages and self.is_scraping:
            current_url = self.urls_to_visit.pop()
            if current_url not in self.visited_urls:
                self.visited_urls.add(current_url)
                self._crawl_page(current_url)
                pages_crawled += 1
                time.sleep(1) # Be polite to the server

        self.is_scraping = False
        self.status_callback("Scraping finished.")
        self.result_callback(list(self.emails_found))

    def stop_scraping(self):
        """Method to signal the scraper to stop."""
        self.is_scraping = False


# --- User Interface ---

class EmailScraperUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Configuration ---
        self.title("Email Scraper")
        self.geometry("600x500")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Set appearance mode and color theme
        ctk.set_appearance_mode("dark")  # Options: "dark", "light", "system"
        ctk.set_default_color_theme("blue")  # Options: "blue", "green", "dark-blue"

        # --- UI Elements ---
        self.scraper_thread = None

        # Title Label
        self.title_label = ctk.CTkLabel(self, text="Domain Email Scraper", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Input Frame
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.domain_entry = ctk.CTkEntry(self.input_frame, placeholder_text="e.g., example.com", font=ctk.CTkFont(size=14))
        self.domain_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.extract_button = ctk.CTkButton(self.input_frame, text="Extract Emails", command=self.start_extraction)
        self.extract_button.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Results Textbox
        self.results_textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(size=12))
        self.results_textbox.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="nsew")
        
        # Status Label
        self.status_label = ctk.CTkLabel(self, text="Enter a domain and click 'Extract Emails'", text_color="gray")
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 10))

    def start_extraction(self):
        """Handles the button click to start the scraping process."""
        domain = self.domain_entry.get().strip()
        if not domain:
            self.status_label.configure(text="Please enter a domain.")
            return

        # Ensure the URL has a scheme
        if not domain.startswith(('http://', 'https://')):
            base_url = f"https://{domain}"
        else:
            base_url = domain

        # Clear previous results
        self.results_textbox.delete("1.0", "end")
        self.status_label.configure(text="Starting scraper...")
        self.extract_button.configure(state="disabled")
        
        # Create and start the scraper thread
        self.scraper_thread = threading.Thread(
            target=self.run_scraper,
            args=(base_url,),
            daemon=True
        )
        self.scraper_thread.start()
        
        # Start checking the thread status periodically
        self.after(100, self.check_thread)

    def run_scraper(self, base_url):
        """Initializes and runs the EmailScraper."""
        scraper = EmailScraper(
            base_url=base_url,
            status_callback=self.update_status,
            result_callback=self.display_results
        )
        scraper.start_scraping()

    def update_status(self, message):
        """Safely updates the status label from a different thread."""
        self.status_label.configure(text=message)

    def display_results(self, emails):
        """Displays the final list of emails in the textbox."""
        self.results_textbox.delete("1.0", "end")
        if emails:
            self.results_textbox.insert("0.0", f"Found {len(emails)} unique email(s):\n\n")
            for email in sorted(emails):
                self.results_textbox.insert("end", f"{email}\n")
        else:
            self.results_textbox.insert("0.0", "No emails found.")
        
        self.extract_button.configure(state="normal")

    def check_thread(self):
        """Checks if the scraper thread is still running."""
        if self.scraper_thread and self.scraper_thread.is_alive():
            self.after(100, self.check_thread)
        else:
            # Re-enable button once thread is finished
            self.extract_button.configure(state="normal")
            if "Scraping finished" not in self.status_label.cget("text"):
                 self.update_status("Scraping finished or stopped.")


if __name__ == "__main__":
    app = EmailScraperUI()
    app.mainloop()