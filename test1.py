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

POSITION_COORDINATES = {
    1: {
        'lot_x': 100,      
        'lot_y': 540,      
        'shipped_x': 540,  
        'shipped_y': 615,
        'back_x': 580,
        'back_y': 615
    },
    2: {
        'lot_x': 100,      
        'lot_y': 372,      
        'shipped_x': 540,  
        'shipped_y': 457,
        'back_x': 580,
        'back_y': 457   
    },
    3: {
        'lot_x': 100,      
        'lot_y': 207,      
        'shipped_x': 540,  
        'shipped_y': 265,
        'back_x': 580,
        'back_y': 265   
    }
}

COMMENT_COORDINATES = {
    'x': 360,
    'y': 750
}

def read_excel_data(file):
    data = pd.read_excel(file, dtype=str)
    return data

def extract_page_data_with_positions(page_text, page_num):
    data = {
        'order_number': None,
        'item_positions': [],
        'raw_text': page_text
    }
    
    order_pattern = r'Order\s*Number:\s*([A-Z0-9]+)'
    order_match = re.search(order_pattern, page_text, re.IGNORECASE)
    if order_match:
        data['order_number'] = order_match.group(1)
    
    lines = page_text.split('\n')
    entry_position = 0
    
    for line in lines:
        if re.match(r'^\d+\.?\s+', line.strip()) or re.match(r'^\d+\s+', line.strip()):
            parts = line.strip().split()
            if len(parts) >= 2:
                potential_item = parts[1]
                
                patterns = [
                    r'^[A-Z]+\d+-\d+-\d+[A-Z]*$',
                    r'^[A-Z]+\d+-\d+[A-Z]*$',
                    r'^[A-Z]\d+-\d+[A-Z]*$',
                    r'^\d+[A-Z]*-?\d+[A-Z]*$',
                    r'^[A-Z0-9]+-?[A-Z0-9]+$',
                    r'^[A-Z]+\d*-?\d+[A-Z]*$'
                ]
                
                is_shipping_method = potential_item in ['FEDEX', 'UPS', 'USPS', 'DHL', 'SHIP']
                
                if not is_shipping_method:
                    for pattern in patterns:
                        if re.match(pattern, potential_item):
                            entry_position += 1
                            data['item_positions'].append({
                                'item_number': potential_item,
                                'position': entry_position,
                                'original_line': line.strip()
                            })
                            break
    
    data['item_numbers'] = [item['item_number'] for item in data['item_positions']]
    return data

def populate_pdf_correct_matching(input_pdf, output_pdf, data, progress_bar, column_names):
    try:
        template_doc = PyPDF2.PdfReader(input_pdf)
    except Exception as e:
        st.error(f"Error reading input PDF: {e}")
        return
    
    output_pdf_writer = PyPDF2.PdfWriter()
    processed_records = set()
    total_records = len(data)
    
    order_comments_cache = {}
    valid_processed_pages = []  
    
    for page_num in range(len(template_doc.pages)):
        if len(processed_records) >= total_records:
            break
        
        try:
            with pdfplumber.open(input_pdf) as pdf:
                page_text = pdf.pages[page_num].extract_text() or ""
        except:
            page_text = ""
        
        if not page_text.strip():
            continue 
        
        page_data = extract_page_data_with_positions(page_text, page_num + 1)
        lot_count = count_lot_occurrences(page_text)
        entry_spaces, coordinates = get_coordinates_for_page(lot_count)
        
        matched_records = []
        
        if page_data['order_number'] and page_data['item_positions']:
            order_number = page_data['order_number']
            if order_number not in order_comments_cache:
                order_comments_cache[order_number] = check_in_process_shipping_for_order(data, order_number, column_names)
            add_comment = order_comments_cache[order_number]
            
            for item_info in page_data['item_positions']:
                page_item = item_info['item_number']
                item_entry_position = item_info['position']
                
                if item_entry_position > entry_spaces:
                    continue
                    
                for idx, record in data.iterrows():
                    record_lot = str(record[column_names['lot_number']]).strip()
                    if not record_lot or record_lot == '':
                        continue
                    
                    if idx not in processed_records and idx not in [r[0] for r in matched_records]:
                        record_order = str(record[column_names['order_number']]).strip()
                        record_part = str(record[column_names['part_number']]).strip()
                        page_order = str(page_data['order_number']).strip()
                        
                        if (record_order == page_order or 
                            record_order.lstrip('0') == page_order.lstrip('0')):
                            if record_part.strip() == page_item.strip():
                                matched_records.append((idx, item_entry_position))
                                break
        
        if matched_records:
            try:
                matched_records.sort(key=lambda x: x[1])
                record_indices = [r[0] for r in matched_records]
                entry_positions_used = [r[1] for r in matched_records]
                
                if page_data['order_number'] and page_data['order_number'] not in order_comments_cache:
                    order_comments_cache[page_data['order_number']] = check_in_process_shipping_for_order(data, page_data['order_number'], column_names)
                add_comment = order_comments_cache.get(page_data['order_number'], False)
                
                overlay_packet = create_overlay_for_matched_records(
                    data, record_indices, coordinates, column_names, entry_positions_used, add_comment
                )
                
                template_page_bytes = safe_create_pdf_page(template_doc.pages[page_num])
                if template_page_bytes is None:
                    continue
                
                merged_page = safe_merge_pdf_page(template_page_bytes, overlay_packet)
                if merged_page is None:
                    continue
                
                if is_valid_pdf_page(merged_page):
                    merged_pdf = PyPDF2.PdfReader(merged_page)
                    valid_processed_pages.append(merged_pdf.pages[0])
                    processed_records.update(record_indices)
                
            except Exception:
                continue

    if len(valid_processed_pages) == 0:
        st.error("No pages were successfully processed!")
        return

    for page in valid_processed_pages:
        output_pdf_writer.add_page(page)
    
    try:
        with open(output_pdf, 'wb') as output_file:
            output_pdf_writer.write(output_file)
    except Exception as e:
        st.error(f"Error saving final PDF: {e}")
        return
    
    progress_bar.progress(1.0)

def count_lot_occurrences(page_text):
    lot_matches = re.findall(r'lot\s*#', page_text.lower())
    return len(lot_matches)

def get_coordinates_for_page(lot_count):
    if lot_count >= 9:
        return 3, [POSITION_COORDINATES[1], POSITION_COORDINATES[2], POSITION_COORDINATES[3]]
    elif lot_count >= 6:
        return 2, [POSITION_COORDINATES[1], POSITION_COORDINATES[2]]
    elif lot_count >= 3:
        return 1, [POSITION_COORDINATES[1]]
    else:
        return 1, [POSITION_COORDINATES[1]]

def get_column_names(df):
    df_columns_lower = [str(col).lower().strip() for col in df.columns]
    actual_columns = list(df.columns)
    
    column_mapping = {}
    
    targets = {
        'order_number': ['order #', 'order number', 'order no', 'order'],
        'part_number': ['part #', 'part number', 'part no', 'part'],
        'quantity': ['quantity', 'qty', 'shipping quantity'],
        'lot_number': ['lot #', 'lot number', 'lot no', 'lot'],
        'order_comments': ['order comments', 'comments', 'order comment'],
        'backorder_quantity': ['quantity backordered', 'backordered qty', 'backorder qty', 'qty backordered', 'backorder quantity']
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
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    if add_in_process_comment:
        can.drawString(COMMENT_COORDINATES['x'], COMMENT_COORDINATES['y'], "IN-PROCESS SHIPPING")
    
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
        
        has_lot_number = column_names['lot_number'] and pd.notna(current_record[column_names['lot_number']]) and str(current_record[column_names['lot_number']]).strip() != ''
        has_quantity = column_names['quantity'] and pd.notna(current_record[column_names['quantity']]) and str(current_record[column_names['quantity']]).strip() != ''
        has_backorder = column_names['backorder_quantity'] and pd.notna(current_record[column_names['backorder_quantity']]) and str(current_record[column_names['backorder_quantity']]).strip() != ''
        
        if has_lot_number or has_quantity or has_backorder:
            if has_lot_number:
                lot_text = f"{current_record[column_names['lot_number']]}"
                can.drawString(coord_set['lot_x'], coord_set['lot_y'], lot_text)

            if has_quantity:
                try:
                    qty_text = f"{int(float(current_record[column_names['quantity']]))}"
                except (ValueError, TypeError):
                    qty_text = f"{current_record[column_names['quantity']]}"
                can.drawString(coord_set['shipped_x'], coord_set['shipped_y'], qty_text)
            
            if has_backorder:
                try:
                    # Check if backorder quantity is greater than 0
                    backorder_value = float(current_record[column_names['backorder_quantity']])
                    if backorder_value > 0:
                        back_text = f"{int(backorder_value)}"
                        can.drawString(coord_set['back_x'], coord_set['back_y'], back_text)
                except (ValueError, TypeError):
                    # If value can't be converted to float, just display it if it's not empty
                    back_text = f"{current_record[column_names['backorder_quantity']]}"
                    if back_text.strip() and back_text.strip() != '0':
                        can.drawString(coord_set['back_x'], coord_set['back_y'], back_text)

    can.save()
    packet.seek(0)
    return packet

def is_valid_pdf_page(page_bytes):
    try:
        pdf_reader = PyPDF2.PdfReader(page_bytes)
        if len(pdf_reader.pages) == 0:
            return False
        
        page = pdf_reader.pages[0]
        try:
            text = page.extract_text()
            if text and len(text.strip()) > 10:  
                return True
        except:
            pass
            
        return True
        
    except Exception:
        return False

def safe_merge_pdf_page(original_page_bytes, overlay_pdf_bytes):
    try:
        original_pdf = PyPDF2.PdfReader(original_page_bytes)
        overlay_pdf = PyPDF2.PdfReader(overlay_pdf_bytes)
        
        if len(original_pdf.pages) == 0 or len(overlay_pdf.pages) == 0:
            return None
            
        output_pdf = PyPDF2.PdfWriter()
        original_page = original_pdf.pages[0]
        overlay_page = overlay_pdf.pages[0]
        
        original_page.merge_page(overlay_page)
        output_pdf.add_page(original_page)
        
        output_bytes = io.BytesIO()
        output_pdf.write(output_bytes)
        output_bytes.seek(0)
        
        if not is_valid_pdf_page(output_bytes):
            return None
            
        return output_bytes
            
    except Exception:
        return None

def safe_create_pdf_page(page_obj):
    try:
        output_bytes = io.BytesIO()
        writer = PyPDF2.PdfWriter()
        writer.add_page(page_obj)
        writer.write(output_bytes)
        output_bytes.seek(0)
        
        if not is_valid_pdf_page(output_bytes):
            return None
            
        return output_bytes
    except Exception:
        return None

def main():
    st.title("PDF Processor - Automated Form Filling")

    uploaded_excel = st.file_uploader("Upload Excel file", type="xlsx")
    uploaded_pdf = st.file_uploader("Upload PDF file", type="pdf")

    if uploaded_excel is not None and uploaded_pdf is not None:
        if st.button("Process PDF"):
            try:
                data = read_excel_data(uploaded_excel)
                column_names = get_column_names(data)

                st.write(f"Total records in Excel: {len(data)}")
                
                empty_lot_count = len(data[
                    (data[column_names['lot_number']].isna()) | 
                    (data[column_names['lot_number']].str.strip() == '')
                ])
                
                if empty_lot_count > 0:
                    st.warning(f"Found {empty_lot_count} records with empty lot numbers - they will be skipped during processing")
                
                required_columns = ['order_number', 'part_number', 'quantity', 'lot_number']
                missing_columns = [col for col in required_columns if not column_names[col]]
                
                if missing_columns:
                    st.error(f"Missing required columns: {', '.join(missing_columns)}")
                    return

                st.success("Column mapping successful!")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
                    temp_input.write(uploaded_pdf.getbuffer())
                    input_pdf = temp_input.name

                output_pdf = "Populated_Picking_Sheet.pdf"
                progress_bar = st.progress(0)
                
                populate_pdf_correct_matching(input_pdf, output_pdf, data, progress_bar, column_names)

                if os.path.exists(output_pdf):
                    st.success("PDF processing completed successfully!")
                    
                    with open(output_pdf, "rb") as file:
                        st.download_button(
                            label="Download Processed PDF",
                            data=file,
                            file_name=output_pdf,
                            mime="application/pdf"
                        )
                    
                    os.unlink(input_pdf)
                    os.unlink(output_pdf)
                else:
                    st.error("Processing completed but no output PDF was created")

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
