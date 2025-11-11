import streamlit as st
import pandas as pd
import PyPDF2
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import white
import io
import re
import logging
import base64
import tempfile
import os

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# HARDCODED COORDINATES - Define coordinates for different page types
COORDINATE_SETS = {
    # For pages with 1 entry space (1 "Lot #" occurrence)
    1: [
        {
            'lot_x': 100,      # X position for Lot # field
            'lot_y': 540,      # Y position for Lot # field  
            'shipped_x': 540,  # X position for Shipped field
            'shipped_y': 615   # Y position for Shipped field
        }
    ],
    # For pages with 2 entry spaces (2 "Lot #" occurrences)
    2: [
        {
            'lot_x': 100,      # First entry - Lot X
            'lot_y': 544,      # First entry - Lot Y
            'shipped_x': 540,  # First entry - Shipped X
            'shipped_y': 615   # First entry - Shipped Y
        },
        {
            'lot_x': 100,      # Second entry - Lot X
            'lot_y': 372,      # Second entry - Lot Y
            'shipped_x': 540,  # Second entry - Shipped X
            'shipped_y': 457   # Second entry - Shipped Y
        }
    ],
    # For pages with 3 entry spaces (3 "Lot #" occurrences)
    3: [
        {
            'lot_x': 100,      # First entry - Lot X
            'lot_y': 540,      # First entry - Lot Y
            'shipped_x': 540,  # First entry - Shipped X
            'shipped_y': 615   # First entry - Shipped Y
        },
        {
            'lot_x': 100,      # Second entry - Lot X
            'lot_y': 364,      # Second entry - Lot Y
            'shipped_x': 540,  # Second entry - Shipped X
            'shipped_y': 450   # Second entry - Shipped Y
        },
        {
            'lot_x': 100,      # Third entry - Lot X
            'lot_y': 207,      # Third entry - Lot Y
            'shipped_x': 540,  # Third entry - Shipped X
            'shipped_y': 290   # Third entry - Shipped Y
        }
    ]
}

# Order number coordinates (same for all pages)
ORDER_COORDS = {
    'order_x': 493,      # X position for Order # field 
    'order_y': 712       # Y position for Order # field 
}

def count_lot_occurrences(page_text):
    """Count how many times 'Lot #' appears on the page"""
    # Use regex to find exact "Lot #" matches (case insensitive)
    lot_matches = re.findall(r'lot\s*#', page_text.lower())
    lot_count = len(lot_matches)
    
        
    return lot_count

def get_coordinates_for_page(lot_count):
    """Determine how many entry spaces based on Lot # count"""
    # Simple mapping: 1 Lot # = 1 entry, 2 Lot # = 2 entries, 3 Lot # = 3 entries
    if lot_count > 9:
        logging.warning(f"⚠️  Unexpected high Lot # count: {lot_count}. Using 3 entries.")
        return 3, COORDINATE_SETS[3]
    elif lot_count == 9:
        logging.info(f"   → Page type: 3-entry page (3 'Lot #' detected)")
        return 3, COORDINATE_SETS[3]
    elif lot_count == 6:
        logging.info(f"   → Page type: 2-entry page (2 'Lot #' detected)")
        return 2, COORDINATE_SETS[2]
    elif lot_count == 3:
        logging.info(f"   → Page type: 1-entry page (1 'Lot #' detected)")
        return 1, COORDINATE_SETS[1]
    else:
        logging.info(f"   → Page type: Defaulting to 1-entry page (0 'Lot #' detected)")
        return 1, COORDINATE_SETS[1]

def read_excel_data(file):
    data = pd.read_excel(file)
    logging.info(f"Excel columns: {data.columns.tolist()}")
    return data

def get_column_names(df):
    column_mapping = {
        'part_number': df.filter(regex=r'(?i)part.*(?:number|#|no)').columns,
        'lot_number': df.filter(regex=r'(?i)lot.*(?:number|#|no)').columns,
        'quantity': df.filter(regex=r'(?i)quantity|qty').columns,
        'order_comments': df.filter(regex=r'(?i)order.*comment').columns,
        'internal_comments': df.filter(regex=r'(?i)(?:internal|so).*comment').columns,
        'order_number': df.filter(regex=r'(?i)order.*(?:number|#|no)').columns
    }

    result = {key: next(iter(value), None) for key, value in column_mapping.items()}
    logging.info(f"Detected column names: {result}")
    return result

def create_overlay_for_page(data_rows, page_number, total_pages, coordinates, column_names):
    """Create overlay for a page with multiple entry spaces"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    logging.debug(f"Creating overlay for page {page_number} with {len(coordinates)} entry spaces, filling {len(data_rows)} records")

    # Add Order Comments on all pages (use first record's comments)
    order_comments_pos = (360, 750)
    if column_names['order_comments'] and pd.notna(data_rows.iloc[0][column_names['order_comments']]):
        can.drawString(order_comments_pos[0], order_comments_pos[1],
                       f"{data_rows.iloc[0][column_names['order_comments']]}")
        logging.debug("Added order comments")

    # Add page number
    page_number_pos = (500, 780)
    can.drawString(page_number_pos[0], page_number_pos[1], f"Page {page_number} of {total_pages}")


    # Fill each entry space with data from corresponding record
    for i, coord_set in enumerate(coordinates):
        if i < len(data_rows):
            current_record = data_rows.iloc[i]
            
            # Lot Number
            if column_names['lot_number'] and pd.notna(current_record[column_names['lot_number']]):
                lot_text = f"{current_record[column_names['lot_number']]}"
                can.drawString(coord_set['lot_x'], coord_set['lot_y'], lot_text)
                logging.debug(f"Added lot number '{lot_text}' at position {i+1}")

            # Quantity
            if column_names['quantity'] and pd.notna(current_record[column_names['quantity']]):
                qty_text = f"{int(current_record[column_names['quantity']])}"
                can.drawString(coord_set['shipped_x'], coord_set['shipped_y'], qty_text)
                logging.debug(f"Added quantity '{qty_text}' at position {i+1}")

    can.save()
    packet.seek(0)
    return packet

def merge_pdf_page(original_pdf_bytes, overlay_pdf_bytes):
    """Merge original PDF page with overlay using PyPDF2"""
    original_pdf = PyPDF2.PdfReader(original_pdf_bytes)
    overlay_pdf = PyPDF2.PdfReader(overlay_pdf_bytes)
    
    output_pdf = PyPDF2.PdfWriter()
    original_page = original_pdf.pages[0]
    overlay_page = overlay_pdf.pages[0]
    
    original_page.merge_page(overlay_page)
    output_pdf.add_page(original_page)
    
    output_bytes = io.BytesIO()
    output_pdf.write(output_bytes)
    output_bytes.seek(0)
    
    return output_bytes

def populate_pdf(input_pdf, output_pdf, data, progress_bar, column_names):
    """Process PDF page by page, matching Excel records to page entry spaces"""
    template_doc = PyPDF2.PdfReader(input_pdf)
    output_pdf_writer = PyPDF2.PdfWriter()
    
    current_record_index = 0
    total_records = len(data)
    
    
    for page_num in range(len(template_doc.pages)):
        if current_record_index >= total_records:
            logging.info(f"✅ All records processed. Stopping at page {page_num + 1}")
            break
            
        
        # Extract text from current page to count Lot # occurrences
        with pdfplumber.open(input_pdf) as pdf:
            page_text = pdf.pages[page_num].extract_text() or ""
        
        lot_count = count_lot_occurrences(page_text)
        entry_spaces, coordinates = get_coordinates_for_page(lot_count)
        
        # Get records for this page (only as many as entry spaces available)
        records_for_page = data.iloc[current_record_index:current_record_index + entry_spaces]
        
        logging.info(f"   → Records to place on this page: {len(records_for_page)}")
        logging.info(f"   → Records range: {current_record_index} to {current_record_index + len(records_for_page) - 1}")
        
        # Create overlay for this page
        overlay_packet = create_overlay_for_page(
            records_for_page, page_num + 1, len(template_doc.pages), coordinates, column_names
        )
        
        # Merge with original page
        template_page_bytes = io.BytesIO()
        template_writer = PyPDF2.PdfWriter()
        template_writer.add_page(template_doc.pages[page_num])
        template_writer.write(template_page_bytes)
        template_page_bytes.seek(0)
        
        merged_page = merge_pdf_page(template_page_bytes, overlay_packet)
        merged_pdf = PyPDF2.PdfReader(merged_page)
        output_pdf_writer.add_page(merged_pdf.pages[0])
        
        # Move to next set of records
        current_record_index += len(records_for_page)
        progress_bar.progress(min(current_record_index / total_records, 1.0))
        
        logging.info(f"   ✅ Page {page_num + 1} completed successfully")

    # Save output PDF
    with open(output_pdf, 'wb') as output_file:
        output_pdf_writer.write(output_file)
    

def main():
    st.title("PDF Processor")

    uploaded_excel = st.file_uploader("Upload Excel file", type="xlsx")
    uploaded_pdf = st.file_uploader("Upload PDF file", type="pdf")

    if uploaded_excel is not None and uploaded_pdf is not None:
        if st.button("Process PDF"):
            try:
                data = read_excel_data(uploaded_excel)
                column_names = get_column_names(data)

                st.write(f"Total records in Excel: {len(data)}")

                if not any(column_names.values()):
                    st.error("No matching column names found in the Excel file. Please check your column names.")
                    return

                # Check for required columns
                if not column_names['lot_number']:
                    st.error("No 'Lot #' column found in Excel file.")
                    return
                if not column_names['quantity']:
                    st.error("No 'Quantity' column found in Excel file.")
                    return
                if not column_names['order_number']:
                    st.error("No 'Order #' column found in Excel file.")
                    return

                # Save uploaded PDF temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
                    temp_input.write(uploaded_pdf.getbuffer())
                    input_pdf = temp_input.name

                output_pdf = "Populated_Picking_Sheet.pdf"

                progress_bar = st.progress(0)
                populate_pdf(input_pdf, output_pdf, data, progress_bar, column_names)

                st.success(f"PDF processing completed successfully!")
                
                # Auto-download the PDF
                with open(output_pdf, "rb") as file:
                    btn = st.download_button(
                        label="Download Processed PDF",
                        data=file,
                        file_name=output_pdf,
                        mime="application/pdf"
                    )

                # Clean up temp files
                os.unlink(input_pdf)
                if os.path.exists(output_pdf):
                    os.unlink(output_pdf)

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                logging.exception("An error occurred during processing")

if __name__ == "__main__":
    main()
