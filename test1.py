import streamlit as st
import pandas as pd
import PyPDF2
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import white, black
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

# Coordinates for "IN-PROCESS SHIPPING" comment
COMMENT_COORDINATES = {
    'x': 360,   
    'y': 750    
}

# Coordinates for page numbers
PAGE_NUMBER_COORDS = {
    'x': 500,
    'y': 780
}

def extract_page_data_with_positions(page_text, page_num):
    """Extract order number and item numbers with their positions"""
    data = {
        'order_number': None,
        'item_positions': [],
        'raw_text': page_text
    }
    
    # Extract order number - handles both numeric and alphanumeric
    order_pattern = r'Order\s*Number:\s*([A-Z0-9]+)'
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
                        data['item_positions'].append({
                            'item_number': potential_item,
                            'position': item_counter,
                            'original_line': line.strip()
                        })
                        break
    
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
    df_columns_lower = [str(col).lower().strip() for col in df.columns]
    actual_columns = list(df.columns)
    
    column_mapping = {}
    
    targets = {
        'order_number': ['order #', 'order number', 'order no', 'order'],
        'part_number': ['part #', 'part number', 'part no', 'part'],
        'quantity': ['quantity', 'qty', 'shipping quantity'],
        'lot_number': ['lot #', 'lot number', 'lot no', 'lot'],
        'order_comments': ['order comments', 'comments', 'order comment']
    }
    
    for key, possible_names in targets.items():
        found_column = None
        for possible_name in possible_names:
            if possible_name in df_columns_lower:
                idx = df_columns_lower.index(possible_name)
                found_column = actual_columns[idx]
                break
        column_mapping[key] = found_column
    
    return column_mapping

def check_in_process_shipping_for_order(data, order_number, column_names):
    """Check if any record with this order number has 'IN-PROCESS SHIPPING' comment"""
    if not column_names['order_comments']:
        return False
    
    for _, record in data.iterrows():
        record_order = str(record[column_names['order_number']]).strip()
        if record_order == order_number:
            comments = str(record[column_names['order_comments']]).strip().upper()
            if 'IN-PROCESS SHIPPING' in comments:
                return True
    return False

def create_overlay_for_matched_records(data, matched_records, coordinates, column_names, positions_used=None, add_in_process_comment=False):
    """Create overlay for matched records WITHOUT page numbers"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Add "IN-PROCESS SHIPPING" comment if needed
    if add_in_process_comment:
        can.drawString(COMMENT_COORDINATES['x'], COMMENT_COORDINATES['y'], "IN-PROCESS SHIPPING")

    # Fill each entry space with data from matched records
    for i, record_idx in enumerate(matched_records):
        if i >= len(coordinates):
            break
            
        current_record = data.iloc[record_idx]
        
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

def create_page_number_overlay(page_number, total_pages):
    """Create overlay with just the page number"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Add white rectangle to cover original page numbers
    rect_width = 80
    rect_height = 20
    
    # Draw white rectangle to cover the area where page numbers go
    can.setFillColor(white)
    can.rect(PAGE_NUMBER_COORDS['x'] - 5, PAGE_NUMBER_COORDS['y'] - 5, rect_width, rect_height, fill=1, stroke=0)
    
    # Reset fill color to black for text
    can.setFillColor(black)
    
    # Add page number on top of the white rectangle
    can.drawString(PAGE_NUMBER_COORDS['x'], PAGE_NUMBER_COORDS['y'], f"Page {page_number} of {total_pages}")

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

def add_page_numbers_to_final_pdf(pdf_bytes):
    """Add page numbers to the final PDF after all processing"""
    original_pdf = PyPDF2.PdfReader(pdf_bytes)
    output_pdf_writer = PyPDF2.PdfWriter()
    total_pages = len(original_pdf.pages)
    
    for page_num in range(total_pages):
        # Create page number overlay for this page
        page_number_overlay = create_page_number_overlay(page_num + 1, total_pages)
        
        # Convert current page to bytes
        page_bytes = io.BytesIO()
        temp_writer = PyPDF2.PdfWriter()
        temp_writer.add_page(original_pdf.pages[page_num])
        temp_writer.write(page_bytes)
        page_bytes.seek(0)
        
        # Merge page number overlay with the page
        merged_page = merge_pdf_page(page_bytes, page_number_overlay)
        merged_pdf = PyPDF2.PdfReader(merged_page)
        output_pdf_writer.add_page(merged_pdf.pages[0])
    
    # Save the final PDF with page numbers
    final_bytes = io.BytesIO()
    output_pdf_writer.write(final_bytes)
    final_bytes.seek(0)
    
    return final_bytes

def populate_pdf_correct_matching(input_pdf, output_pdf, data, progress_bar, column_names):
    """Process PDF with CORRECT matching, position handling, blank page removal, and comments"""
    template_doc = PyPDF2.PdfReader(input_pdf)
    output_pdf_writer = PyPDF2.PdfWriter()
    processed_records = set()
    total_records = len(data)
    
    # Track which order numbers need "IN-PROCESS SHIPPING" comment
    order_comments_cache = {}
    
    # Store pages temporarily to remove blank ones later
    processed_pages = []
    
    for page_num in range(len(template_doc.pages)):
        if len(processed_records) >= total_records:
            break
        
        # Extract page data with positions
        with pdfplumber.open(input_pdf) as pdf:
            page_text = pdf.pages[page_num].extract_text() or ""
        
        if not page_text.strip():
            # Skip completely blank pages
            continue
        
        page_data = extract_page_data_with_positions(page_text, page_num + 1)
        lot_count = count_lot_occurrences(page_text)
        entry_spaces, coordinates = get_coordinates_for_page(lot_count)
        
        # Find matching records for this page
        matched_records = []
        
        if page_data['order_number'] and page_data['item_positions']:
            # Check if this order needs "IN-PROCESS SHIPPING" comment
            order_number = page_data['order_number']
            if order_number not in order_comments_cache:
                order_comments_cache[order_number] = check_in_process_shipping_for_order(data, order_number, column_names)
            add_comment = order_comments_cache[order_number]
            
            # For each item on the page, find the EXACT matching record
            for item_info in page_data['item_positions']:
                page_item = item_info['item_number']
                item_position = item_info['position']
                
                if item_position > entry_spaces:
                    continue
                    
                for idx, record in data.iterrows():
                    if idx not in processed_records and idx not in [r[0] for r in matched_records]:
                        record_order = str(record[column_names['order_number']]).strip()
                        record_part = str(record[column_names['part_number']]).strip()
                        page_order = str(page_data['order_number']).strip()
                        
                        if record_order == page_order and record_part == str(page_item).strip():
                            matched_records.append((idx, item_position))
                            break
        
        # Only add page if it has matches OR has "IN-PROCESS SHIPPING" comment
        if matched_records:
            try:
                matched_records.sort(key=lambda x: x[1])
                record_indices = [r[0] for r in matched_records]
                positions_used = [r[1] for r in matched_records]
                
                # Check again for comment in case new records were found
                if page_data['order_number'] and page_data['order_number'] not in order_comments_cache:
                    order_comments_cache[page_data['order_number']] = check_in_process_shipping_for_order(data, page_data['order_number'], column_names)
                add_comment = order_comments_cache.get(page_data['order_number'], False)
                
                overlay_packet = create_overlay_for_matched_records(
                    data, record_indices, coordinates, column_names, positions_used, add_comment
                )
                
                template_page_bytes = io.BytesIO()
                template_writer = PyPDF2.PdfWriter()
                template_writer.add_page(template_doc.pages[page_num])
                template_writer.write(template_page_bytes)
                template_page_bytes.seek(0)
                
                merged_page = merge_pdf_page(template_page_bytes, overlay_packet)
                merged_pdf = PyPDF2.PdfReader(merged_page)
                
                # Store the processed page
                processed_pages.append(merged_pdf.pages[0])
                
                processed_records.update(record_indices)
                
            except Exception as e:
                # Skip pages with errors (treat as blank)
                continue
    
    # Update order comments for all pages in case comments were found later
    final_pages = []
    for page in processed_pages:
        # Extract order number from the page text to check for comments
        page_text = ""
        try:
            output_bytes = io.BytesIO()
            temp_writer = PyPDF2.PdfWriter()
            temp_writer.add_page(page)
            temp_writer.write(output_bytes)
            output_bytes.seek(0)
            
            with pdfplumber.open(output_bytes) as pdf:
                if pdf.pages:
                    page_text = pdf.pages[0].extract_text() or ""
        except:
            pass
        
        # Check if this page needs "IN-PROCESS SHIPPING" comment
        order_match = re.search(r'Order\s*Number:\s*([A-Z0-9]+)', page_text, re.IGNORECASE)
        if order_match:
            order_number = order_match.group(1)
            if order_number in order_comments_cache and order_comments_cache[order_number]:
                # Recreate overlay with comment
                try:
                    overlay_packet = create_overlay_for_matched_records(
                        data, [], [], column_names, [], True
                    )
                    
                    page_bytes = io.BytesIO()
                    temp_writer = PyPDF2.PdfWriter()
                    temp_writer.add_page(page)
                    temp_writer.write(page_bytes)
                    page_bytes.seek(0)
                    
                    merged_page = merge_pdf_page(page_bytes, overlay_packet)
                    merged_pdf = PyPDF2.PdfReader(merged_page)
                    final_pages.append(merged_pdf.pages[0])
                    continue
                except:
                    pass
        
        final_pages.append(page)
    
    # Add only non-blank pages to final output (without page numbers first)
    temp_output = io.BytesIO()
    temp_writer = PyPDF2.PdfWriter()
    for page in final_pages:
        temp_writer.add_page(page)
    temp_writer.write(temp_output)
    temp_output.seek(0)
    
    # NEW: Add page numbers to the final PDF
    final_pdf_with_numbers = add_page_numbers_to_final_pdf(temp_output)
    
    # Save the final PDF with proper page numbers
    with open(output_pdf, 'wb') as output_file:
        output_file.write(final_pdf_with_numbers.getvalue())
    
    progress_bar.progress(1.0)

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

                st.success("✅ Column mapping successful!")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
                    temp_input.write(uploaded_pdf.getbuffer())
                    input_pdf = temp_input.name

                output_pdf = "Populated_Picking_Sheet.pdf"
                progress_bar = st.progress(0)
                
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
