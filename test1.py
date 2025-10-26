import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import re
import logging
import base64
import tempfile
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# HARDCODED COORDINATES - Update these after running the coordinate analyzer
HARDCODED_COORDINATES = {
    'lot_x': 100,      # X position for Lot # field
    'lot_y': 540,      # Y position for Lot # field  
    'shipped_x': 540,  # X position for Shipped field
    'shipped_y': 615 # Y position for Shipped field
}



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

def create_overlay_for_record(data_row, page_number, total_pages, page, column_names):
    """Create overlay for a single record using hardcoded coordinates"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    logging.debug(f"Creating overlay for record on page {page_number}")

    # Add Order Comments on all pages
    order_comments_pos = (360, 750)
    if column_names['order_comments'] and pd.notna(data_row[column_names['order_comments']]):
        can.drawString(order_comments_pos[0], order_comments_pos[1],
                       f"{data_row[column_names['order_comments']]}")
        logging.debug("Added order comments")

    # Add page number
    page_number_pos = (500, 780)
    can.drawString(page_number_pos[0], page_number_pos[1], f"Page {page_number} of {total_pages}")

    # Use hardcoded coordinates for precise placement
    lot_position = (HARDCODED_COORDINATES['lot_x'], HARDCODED_COORDINATES['lot_y'])
    shipped_position = (HARDCODED_COORDINATES['shipped_x'], HARDCODED_COORDINATES['shipped_y'])

    # Lot Number - using hardcoded coordinates
    if column_names['lot_number'] and pd.notna(data_row[column_names['lot_number']]):
        lot_text = f"{data_row[column_names['lot_number']]}"
        can.drawString(lot_position[0], lot_position[1], lot_text)
        logging.debug(f"Added lot number: {lot_text} at {lot_position}")

    # Quantity - using hardcoded coordinates
    if column_names['quantity'] and pd.notna(data_row[column_names['quantity']]):
        qty_text = f"{int(data_row[column_names['quantity']])}"
        can.drawString(shipped_position[0], shipped_position[1], qty_text)
        logging.debug(f"Added quantity: {qty_text} at {shipped_position}")

    can.save()
    packet.seek(0)
    return fitz.open(stream=packet, filetype="pdf")

def populate_pdf(input_pdf, output_pdf, data, progress_bar, column_names):
    # Create a new PDF document
    template_doc = fitz.open(input_pdf)
    output_doc = fitz.open()
    
    total_records = len(data)
    
    # Create one page per record
    for record_num in range(total_records):
        # Use the first page as template for all records
        if record_num < len(template_doc):
            # Use existing page from template
            page = template_doc[record_num]
        else:
            # Use first page as template for additional records
            page = template_doc[0]
        
        # Add the page to output document
        output_doc.insert_pdf(template_doc, from_page=min(record_num, len(template_doc)-1), to_page=min(record_num, len(template_doc)-1))
        
        # Get the current page in output document
        current_page = output_doc[record_num]
        current_record = data.iloc[record_num]
        
        logging.info(f"Processing record {record_num + 1} of {total_records}")
        
        # Create overlay for this single record
        overlay = create_overlay_for_record(
            current_record, record_num + 1, total_records, current_page, column_names
        )
        
        # Apply the overlay
        current_page.show_pdf_page(current_page.rect, overlay, 0)
        
        progress_bar.progress((record_num + 1) / total_records)

    output_doc.save(output_pdf)
    output_doc.close()
    template_doc.close()
    logging.info(f"PDF saved to {output_pdf}")

def get_binary_file_downloader_html(bin_file, file_label='File'):
    with open(bin_file, 'rb') as f:
        data = f.read()
    bin_str = base64.b64encode(data).decode()
    href = f'<a href="data:application/octet-stream;base64,{bin_str}" download="{bin_file}">Download {file_label}</a>'
    return href

def main():
    st.title("PDF Processor")

    uploaded_excel = st.file_uploader("Upload Excel file", type="xlsx")
    uploaded_pdf = st.file_uploader("Upload PDF file", type="pdf")

    if uploaded_excel is not None and uploaded_pdf is not None:
        if st.button("Process PDF"):
            try:
                data = read_excel_data(uploaded_excel)
                column_names = get_column_names(data)

                st.write("Detected column names:", column_names)
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

                # Save uploaded PDF temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
                    temp_input.write(uploaded_pdf.getbuffer())
                    input_pdf = temp_input.name

                output_pdf = "Populated_Picking_Sheet.pdf"

                progress_bar = st.progress(0)
                populate_pdf(input_pdf, output_pdf, data, progress_bar, column_names)

                st.success(f"PDF processing completed successfully! Created {len(data)} pages.")
                st.markdown(get_binary_file_downloader_html(output_pdf, 'Processed PDF'), unsafe_allow_html=True)

                # Clean up temp file
                os.unlink(input_pdf)

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                logging.exception("An error occurred during processing")

if __name__ == "__main__":
    main()