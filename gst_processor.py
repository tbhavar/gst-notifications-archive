import sys
import os
import re
import requests
from io import BytesIO
from pypdf import PdfReader
from datetime import datetime

# --- Configuration ---
PDF_OUTPUT_DIR = "notifications"

def download_and_read_pdf(url):
    """Downloads PDF content from a URL and extracts text from the first page."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
        
        # Read content into a BytesIO object (in-memory file)
        pdf_file = BytesIO(response.content)
        
        # Initialize PdfReader and extract text from the first page
        reader = PdfReader(pdf_file)
        if not reader.pages:
            print("Error: PDF has no pages.")
            return None
            
        first_page_text = reader.pages[0].extract_text()
        return first_page_text

    except requests.exceptions.RequestException as e:
        print(f"Error downloading the PDF: {e}")
        return None
    except Exception as e:
        print(f"Error reading the PDF content: {e}")
        # This might happen if the PDF is password protected or corrupted.
        return None

def parse_gst_details(text):
    """
    Parses the extracted text to find the Notification Date and Subject using more robust patterns.
    """
    raw_date = None
    subject = "Subject_Not_Found"
    
    print("Attempting automatic PDF parsing...")
    
    # --- 1. Robust Date Extraction ---
    date_pattern_1 = re.compile(r'(?:Dated|Date|No\.\s*)\s*[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})', re.IGNORECASE)
    date_pattern_2 = re.compile(r'(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December),\s+(\d{4})', re.IGNORECASE)
    
    date_match = date_pattern_1.search(text)
    if date_match:
        raw_date = date_match.group(1).strip()
    else:
        date_match_2 = date_pattern_2.search(text)
        if date_match_2:
            day, month_name, year = date_match_2.groups()
            month_number = datetime.strptime(month_name, '%B').month
            raw_date = f"{int(day):02d}/{month_number:02d}/{year}"


    # --- 2. Robust Subject/Purpose Extraction ---
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # 2a. Search for a line that is long and in ALL CAPS
    for line in lines[:10]:
        if len(line) > 30 and line == line.upper() and 'GOVERNMENT' not in line:
            subject = line
            break
            
    # 2b. Fallback: Take the text immediately following the main header
    if subject == "Subject_Not_Found":
        relevant_text = text.split("GOVERNMENT OF INDIA", 1)[-1] 
        fallback_lines = [
            line.strip() for line in relevant_text.split('\n') 
            if line.strip() and len(line) > 10 and 'Notification No.' not in line
        ][:3]
        
        if fallback_lines:
             subject = " ".join(fallback_lines)


    # --- 3. Clean and Format Filename Components ---
    if subject != "Subject_Not_Found":
        # Clean up the subject for use in a filename
        subject = re.sub(r'[^\w\s-]', '', subject).strip()
        subject = re.sub(r'\s+', '_', subject)[:80].rstrip('_') 

    return raw_date, subject

def create_and_save_pdf(url, new_filename):
    """Downloads the PDF and saves it with the new filename."""
    try:
        response = requests.get(url)
        response.raise_for_status() 
        
        os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)
        file_path = os.path.join(PDF_OUTPUT_DIR, new_filename)
        
        with open(file_path, 'wb') as f:
            f.write(response.content)
            
        print(f"::notice file={file_path}::Successfully saved as {new_filename}")
        print(f"File saved successfully as {file_path}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error saving PDF (second download): {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during file saving: {e}")
        sys.exit(1)

# --- Main Execution Block ---
if __name__ == "__main__":
    # Script now expects 3 arguments: URL, Manual_Date, Manual_Subject
    if len(sys.argv) < 2 or len(sys.argv) > 4:
        print("Usage: python gst_processor.py <PDF_URL> [Manual_Date] [Manual_Subject]")
        sys.exit(1)

    pdf_url = sys.argv[1]
    # Check if manual overrides were provided (they will be empty strings if not set in Action)
    manual_raw_date = sys.argv[2] if len(sys.argv) > 2 else ""
    manual_subject = sys.argv[3] if len(sys.argv) > 3 else ""
    
    print(f"Processing URL: {pdf_url}")

    raw_date = None
    subject = None
    pdf_text = None
    
    # 1. Manual Override Check
    if manual_raw_date and manual_subject:
        print("Using MANUAL inputs provided via GitHub Action.")
        raw_date = manual_raw_date
        subject = manual_subject
    else:
        # 2. Automated Parsing Attempt (if no manual input)
        pdf_text = download_and_read_pdf(pdf_url)
        if pdf_text:
            raw_date, subject = parse_gst_details(pdf_text)
        else:
            print("Error: Could not download or read PDF for automated parsing.")
            sys.exit(1)

    # 3. Final Validation and Saving
    
    # If the subject is empty or failed to parse, or date is missing, exit.
    if not raw_date or not subject or subject == "Subject_Not_Found":
        print("Error: Could not determine final date or subject for renaming.")
        print(f"Date found: {raw_date}, Subject found: {subject}")
        sys.exit(1)
        
    # Standardize the Date Format
    date_prefix = None
    try:
        # Tries to parse DD/MM/YYYY and reformat to YYYY-MM-DD
        date_obj = datetime.strptime(raw_date.replace('-', '/').replace('.', '/'), '%d/%m/%Y')
        date_prefix = date_obj.strftime('%Y-%m-%d')
    except ValueError:
        print(f"Fatal Error: The date '{raw_date}' (manual or parsed) could not be standardized to DD/MM/YYYY.")
        sys.exit(1)

    # Clean the subject again, just in case the manual input was messy
    clean_subject = re.sub(r'[^\w\s-]', '', subject).strip()
    clean_subject = re.sub(r'\s+', '_', clean_subject)[:80].rstrip('_')
    
    new_filename = f"{date_prefix}_{clean_subject}.pdf"
    print(f"Constructed filename: {new_filename}")
    
    # Save the file using the original URL
    create_and_save_pdf(pdf_url, new_filename)
