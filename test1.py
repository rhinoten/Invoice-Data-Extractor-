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
import base64
import tempfile
import os
import sys

# HARDCODED COORDINATES - Define coordinates for different positions
POSITION_COORDINATES = {
    1: {  # First position (TOP)
        'lot_x': 100,      # X position for Lot # field
        'lot_y': 540,      # Y position for Lot # field  
        'shipped_x': 540,  # X position for Shipped field
        'shipped_y': 615   # Y position for Shipped field
    },
    2: {  # Second position (MIDDLE)
        'lot_x': 100,      # Lot X
        'lot_y': 372,      # Lot Y
        'shipped_x': 540,  # Shipped X
        'shipped_y': 457   # Shipped Y
    },
    3: {  # Third position (BOTTOM)
        'lot_x': 100,      # Lot X
        'lot_y': 207,      # Lot Y
        'shipped_x': 540,  # Shipped X
        'shipped_y': 290   # Shipped Y
    }
}

def extract_page_data_with_positions(page_text, page_num):
    """Extract order number and item numbers with their positions"""
    data = {
        'order_number': None,
        'item_positions': [],
        'raw_text': page_text
    }
    
    # FIXED: Extract order number - now handles both numeric and alphanumeric (M005582, etc.)
    order_pattern = r'Order\s*Number:\s*([A-Z0-9]+)'  # Changed from (\d+) to ([A-Z0-9]+)
    order_match = re.search(order_pattern, page_text, re.IGNORECASE)
    if order_match:
        data['order_number'] = order_match.group(1)
    
    # Extract items with their line numbers to determine positions
    lines = page_text.split('\n')
    
    item_counter = 0
    for line in lines:
        # Match lines starting with numbers (single or multiple digits)
        if re.match(r'^\d+\.?\s+', line.strip()) or re.match(r'^\d+\s+', line.strip()):
            parts = line.strip().split()
            if len(parts) >= 2:
                potential_item = parts[1]
                
                # Check if it matches our item number patterns
                patterns = [
                    r'^[A-Z]\d+-\d+[A-Z]*$',
                    r'^\d+[A-Z]*-\d+[A-Z]*$',
                    r'^[A-Z]+\d+-\d+[A-Z]*$',
                    r'^[A-Z0-9]+-\d+[A-Z]*$'
                ]
                
                for pattern in patterns:
                    if re.match(pattern, potential_item):
                        item_counter += 1
                        # Position is determined by the order we find items (1st, 2nd, 3rd)
                        data['item_positions'].append({
                            'item_number': potential_item,
                            'position': item_counter,
                            'original_line': line.strip()
                        })
                        break
    
    # Also extract just the item numbers for backward compatibility
    data['item_numbers'] = [item['item_number'] for item in data['item_positions']]
    
    return data

def count_lot_occurrences(page_text):
    """Count how many times 'Lot #' appears on the page"""
    lot_matches = re.findall(r'lot\s*#', page_text.lower())
    lot_count = len(lot_matches)
    return lot_count

def get_coordinates_for_page(lot_count):
    """Determine how many entry spaces based on Lot # count"""
    if lot_count >= 9:
        return 3, [POSITION_COORDINATES[1], POSITION_COORDINATES[2], POSITION_COORDINATES[3]]
    elif lot_count >= 6:
        return 2, [POSITION_COORDINATES[1], POSITION_COORDINATES[2]]
    elif lot_count >= 3:
        return 1, [POSITION_COORDINATES[1]]
    else:
        return 1, [POSITION_COORDINATES[1]]

def get_column_names(df):
    """Get column names with exact matching"""
    # Create a case-insensitive mapping
    df_columns_lower = [str(col).lower().strip() for col in df.columns]
    actual_columns = list(df.columns)
    
    column_mapping = {}
    
    # Define what we're looking for (case insensitive)
    targets = {
        'order_number': ['order #', 'order number', 'order no', 'order'],
        'part_number': ['part #', 'part number', 'part no', 'part'],
        'quantity': ['quantity', 'qty', 'shipping quantity'],
        'lot_number': ['lot #', 'lot number', 'lot no', 'lot']
    }
    
    for key, possible_names in targets.items():
        found_column = None
        for possible_name in possible_names:
            if possible_name in df_columns_lower:
                # Find the actual column name that matches
                idx = df_columns_lower.index(possible_name)
                found_column = actual_columns[idx]
                break
        
        column_mapping[key] = found_column
    
    return column_mapping

def create_overlay_for_matched_records(data, matched_records, page_number, total_pages, coordinates, column_names, positions_used=None):
    """Create overlay for matched records with position awareness"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Add page number
    page_number_pos = (500, 780)
    can.drawString(page_number_pos[0], page_number_pos[1], f"Page {page_number} of {total_pages}")

    # Fill each entry space with data from matched records
    for i, record_idx in enumerate(matched_records):
        if i >= len(coordinates):
            break
            
        current_record = data.iloc[record_idx]
        
        # Use the actual position if provided, otherwise use sequential order
        if positions_used and i < len(positions_used):
            position = positions_used[i]
            coord_set = coordinates[position - 1]
        else:
            position = i + 1
            coord_set = coordinates[i]
        
        # Lot Number
        if column_names['lot_number'] and pd.notna(current_record[column_names['lot_number']]):
            lot_text = f"{current_record[column_names['lot_number']]}"
            can.drawString(coord_set['lot_x'], coord_set['lot_y'], lot_text)

        # Quantity
        if column_names['quantity'] and pd.notna(current_record[column_names['quantity']]):
            qty_text = f"{int(current_record[column_names['quantity']])}"
            can.drawString(coord_set['shipped_x'], coord_set['shipped_y'], qty_text)

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

def read_excel_data(file):
    data = pd.read_excel(file)
    return data

def populate_pdf_correct_matching(input_pdf, output_pdf, data, progress_bar, column_names):
    """Process PDF with CORRECT matching and position handling"""
    template_doc = PyPDF2.PdfReader(input_pdf)
    output_pdf_writer = PyPDF2.PdfWriter()
    processed_records = set()
    total_records = len(data)
    
    for page_num in range(len(template_doc.pages)):
        if len(processed_records) >= total_records:
            break
        
        # Extract page data with positions
        with pdfplumber.open(input_pdf) as pdf:
            page_text = pdf.pages[page_num].extract_text() or ""
        
        if not page_text.strip():
            output_pdf_writer.add_page(template_doc.pages[page_num])
            continue
        
        page_data = extract_page_data_with_positions(page_text, page_num + 1)
        lot_count = count_lot_occurrences(page_text)
        entry_spaces, coordinates = get_coordinates_for_page(lot_count)
        
        # Find matching records for this page
        matched_records = []  # This will store (record_idx, position) pairs
        
        if page_data['order_number'] and page_data['item_positions']:
            # For each item on the page, find the EXACT matching record
            for item_info in page_data['item_positions']:
                page_item = item_info['item_number']
                item_position = item_info['position']
                
                if item_position > entry_spaces:
                    continue
                    
                # Find record with matching order number AND matching item number
                for idx, record in data.iterrows():
                    if idx not in processed_records and idx not in [r[0] for r in matched_records]:
                        record_order = str(record[column_names['order_number']]).strip()
                        record_part = str(record[column_names['part_number']]).strip()
                        page_order = str(page_data['order_number']).strip()
                        
                        # Check BOTH order number AND item number
                        if record_order == page_order and record_part == str(page_item).strip():
                            matched_records.append((idx, item_position))
                            break
        
        # Create overlay if we have matches
        if matched_records:
            try:
                # Sort matched records by position to ensure correct placement
                matched_records.sort(key=lambda x: x[1])
                record_indices = [r[0] for r in matched_records]
                positions_used = [r[1] for r in matched_records]
                
                overlay_packet = create_overlay_for_matched_records(
                    data, record_indices, page_num + 1, len(template_doc.pages), coordinates, column_names, positions_used
                )
                
                template_page_bytes = io.BytesIO()
                template_writer = PyPDF2.PdfWriter()
                template_writer.add_page(template_doc.pages[page_num])
                template_writer.write(template_page_bytes)
                template_page_bytes.seek(0)
                
                merged_page = merge_pdf_page(template_page_bytes, overlay_packet)
                merged_pdf = PyPDF2.PdfReader(merged_page)
                output_pdf_writer.add_page(merged_pdf.pages[0])
                
                # Mark records as processed
                processed_records.update(record_indices)
                
            except Exception as e:
                output_pdf_writer.add_page(template_doc.pages[page_num])
        else:
            output_pdf_writer.add_page(template_doc.pages[page_num])
        
        progress_bar.progress(min(len(processed_records) / total_records, 1.0))

    # Save output PDF
    try:
        with open(output_pdf, 'wb') as output_file:
            output_pdf_writer.write(output_file)
    except Exception as e:
        st.error(f"Error saving PDF: {e}")

def main():
    st.title("PDF Processor - Automated Form Filling")

    uploaded_excel = st.file_uploader("Upload Excel file", type="xlsx")
    uploaded_pdf = st.file_uploader("Upload PDF file", type="pdf")

    if uploaded_excel is not None and uploaded_pdf is not None:
        if st.button("Process PDF"):
            try:
                data = read_excel_data(uploaded_excel)
                column_names = get_column_names(data)

                st.write(f"**Total records in Excel:** {len(data)}")

                # Validate required columns
                required_columns = ['order_number', 'part_number', 'quantity', 'lot_number']
                missing_columns = [col for col in required_columns if not column_names[col]]
                
                if missing_columns:
                    st.error(f"Missing required columns: {', '.join(missing_columns)}")
                    st.info("Please ensure your Excel has: Order #, Part #, Quantity, and Lot # columns")
                    return

                # Show mapping confirmation
                st.success("✅ Column mapping successful!")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
                    temp_input.write(uploaded_pdf.getbuffer())
                    input_pdf = temp_input.name

                output_pdf = "Populated_Picking_Sheet.pdf"
                progress_bar = st.progress(0)
                
                # Use the matching function
                populate_pdf_correct_matching(input_pdf, output_pdf, data, progress_bar, column_names)

                st.success(f"PDF processing completed successfully!")
                
                with open(output_pdf, "rb") as file:
                    st.download_button(
                        label="Download Processed PDF",
                        data=file,
                        file_name=output_pdf,
                        mime="application/pdf"
                    )

                os.unlink(input_pdf)
                if os.path.exists(output_pdf):
                    os.unlink(output_pdf)

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
