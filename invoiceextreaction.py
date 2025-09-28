import streamlit as st
import pandas as pd
import pdfplumber
import re
from typing import Dict, List, Optional, Tuple
import io

def _extract_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract common invoice information from lines"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_number': ''
    }
    
    for line in lines:
        # Try multiple patterns for invoice number
        patterns = [
            r'invoice no\.?\s*[:#]?\s*(\w+)',
            r'rechnung nr\.?\s*[:#]?\s*(\w+)',
            r'no\.\s*[:#]?\s*(\d+)',
            r'invoice\s+(\w+)',
            r'rechnung\s+(\w+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and not invoice_data['invoice_number']:
                invoice_data['invoice_number'] = match.group(1)
        
        # Try multiple patterns for date
        date_patterns = [
            r'date\s*[:#]?\s*(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4})',
            r'datum\s*[:#]?\s*(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4})',
            r'rechnungsdatum\s*[:#]?\s*(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4})',
            r'invoice date\s*[:#]?\s*(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4})',
            r'from\s+(\d{1,2}\.\d{1,2}\.\d{4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and not invoice_data['invoice_date']:
                invoice_data['invoice_date'] = match.group(1)
        
        # Try multiple patterns for order number
        order_patterns = [
            r'order no\.?\s*[:#]?\s*(\w+)',
            r'your order\s*[:#]?\s*(\w+)',
            r'auftrag nr\.?\s*[:#]?\s*(\w+)',
            r'purchase order\s*[:#]?\s*(\w+)'
        ]
        
        for pattern in order_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and not invoice_data['order_number']:
                invoice_data['order_number'] = match.group(1)
    
    return invoice_data

#bumuller
def extract_bumuller_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Bumüller GmbH invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # Get total number of pages
        num_pages = len(pdf.pages)

        # Extract invoice-level data from first page
        first_page_text = pdf.pages[0].extract_text()

        # Extract invoice number and date from first page
        invoice_number_match = re.search(r'No\.\s*(\d+)', first_page_text)
        invoice_number = invoice_number_match.group(1) if invoice_number_match else ""

        invoice_date_match = re.search(r'from\s+(\d{2}\.\d{2}\.\d{4})', first_page_text)
        invoice_date = invoice_date_match.group(1) if invoice_date_match else ""

        # Process all pages
        for page_num in range(num_pages):
            # Extract text from current page
            text = pdf.pages[page_num].extract_text()

            # Split text into lines for processing
            lines = text.split('\n')

            # Initialize/reset page-level variables
            current_po = ""
            current_novo_item = ""
            current_vendor_item = ""
            current_lot = ""

            # Process lines to extract item data
            i = 0
            while i < len(lines):
                line = lines[i]

                # Extract PO number
                po_match = re.search(r'your order no\.\s*(\d+)', line)
                if po_match:
                    current_po = po_match.group(1)

                # Extract Novo item number
                novo_match = re.search(r'Your Item No\.\s*(\w+[-]\d+)', line)
                if novo_match:
                    current_novo_item = novo_match.group(1)

                    # Look ahead for lot number within next few lines
                    for j in range(i, min(i + 5, len(lines))):
                        lot_match = re.search(r'LOT#\s*([\w-]+)', lines[j])
                        if lot_match:
                            current_lot = lot_match.group(1)
                            break

                # Extract vendor item number
                vendor_match = re.search(r'(\d+-\d+-\d+)', line)
                if vendor_match:
                    current_vendor_item = vendor_match.group(1)

                # Look for quantity and price pattern
                qty_price_match = re.search(r'(\d+)pcs\s+(\d+,\d+)\s+(\d+,\d+)', line)
                if qty_price_match:
                    qty = qty_price_match.group(1)
                    price_each = qty_price_match.group(2)

                    item_data = {
                        'invoice_date': invoice_date,
                        'invoice_number': invoice_number,
                        'purchase_order': current_po,
                        'vendor_item': current_vendor_item,
                        'novo_item': current_novo_item,
                        'lot_number': current_lot,
                        'quantity': qty,
                        'price_each': price_each,
                        'page_number': page_num + 1  # Add page number for reference
                    }

                    extracted_data.append(item_data)

                    # Reset item-specific variables after extraction
                    current_lot = ""

                i += 1

    return extracted_data

#amilazzo
def extract_amilazzo_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from A. Milazzo Medizintechnik GmbH invoice format.
    Works with both single-line and multi-line item layouts.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")

            # Extract invoice-level info
            invoice_date = ""
            invoice_number = ""

            for line in lines:
                inv_match = re.search(r'INVOICE NO\.\s*:\s*(\d+)', line, re.IGNORECASE)
                if inv_match:
                    invoice_number = inv_match.group(1)

                date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line)
                if date_match:
                    invoice_date = date_match.group(1)

            # Scan for items (block-based)
            current_block = []
            for line in lines:
                if re.search(r'your art\.-no\.:', line, re.IGNORECASE):
                    # Start new block
                    if current_block:
                        # Process previous block before starting new one
                        item = _parse_milazzo_item_block(
                            current_block, invoice_date, invoice_number, page_num
                        )
                        if item:
                            extracted_data.append(item)
                    current_block = [line]
                elif re.search(r'Lot number', line, re.IGNORECASE):
                    # End block
                    current_block.append(line)
                    item = _parse_milazzo_item_block(
                        current_block, invoice_date, invoice_number, page_num
                    )
                    if item:
                        extracted_data.append(item)
                    current_block = []
                elif current_block:
                    # Collect block lines
                    current_block.append(line)

            # Handle last block if file ends without "Lot number"
            if current_block:
                item = _parse_milazzo_item_block(
                    current_block, invoice_date, invoice_number, page_num
                )
                if item:
                    extracted_data.append(item)

    return extracted_data


#milazzo
def _parse_milazzo_item_block(block_lines: List[str], invoice_date: str, invoice_number: str, page_num: int) -> Optional[Dict]:
    """
    Parse a block of lines corresponding to a single Milazzo invoice item.
    """
    block_text = " ".join(block_lines)

    # Vendor item
    vendor_item = ""
    art_match = re.search(r'your art\.-no\.:?\s*([\w-]+)', block_text, re.IGNORECASE)
    if art_match:
        vendor_item = art_match.group(1)

    # PO Number (M.* style codes)
    po_number = ""
    po_match = re.search(r'(M\.[A-Z]\.\d{2}-\d{2}/\d+)', block_text)
    if po_match:
        po_number = po_match.group(1)

    # Lot number
    lot_number = ""
    lot_match = re.search(r'Lot number\s*([\w\/ -]+)', block_text, re.IGNORECASE)
    if lot_match:
        lot_number = lot_match.group(1).strip()

    # Quantity and price each (take first match like "3 74,78" or "4 91,52")
    qty = ""
    price_each = ""
    qty_price_match = re.search(r'(\d+)\s+(\d+,\d{2})', block_text)
    if qty_price_match:
        qty = qty_price_match.group(1)
        price_each = qty_price_match.group(2)

    # Novo item (description) → remove known fields and keep what’s left
    description = re.sub(r'(your art\.-no\.:.*|Lot number.*|M\.[A-Z]\.\d{2}-\d{2}/\d+|\d+\s+\d+,\d{2})', '', block_text, flags=re.IGNORECASE)
    description = re.sub(r'\s+', ' ', description).strip()

    if all([invoice_date, invoice_number, vendor_item, po_number, lot_number, qty, price_each]):
        return {
            "invoice_date": invoice_date,
            "invoice_number": invoice_number,
            "purchase_order": po_number,
            "vendor_item": vendor_item,
            "novo_item": description,
            "lot_number": lot_number,
            "quantity": qty,
            "price_each": price_each,
            "page_number": page_num + 1,
        }
    return None


#valign
def extract_avalign_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Avalign German Specialty Instruments invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # Get total number of pages
        num_pages = len(pdf.pages)

        for page_num in range(num_pages):
            text = pdf.pages[page_num].extract_text()
            lines = text.split('\n')

            # Extract invoice-level data
            invoice_number = ""
            invoice_date = ""
            po_number = ""

            for line in lines:
                if "Invoice:" in line:
                    invoice_match = re.search(r'Invoice:\s*(\d+)', line)
                    invoice_number = invoice_match.group(1) if invoice_match else ""
                elif "Date:" in line:
                    date_match = re.search(r'Date:\s*(\d{1,2}/\d{1,2}/\d{4})', line)
                    invoice_date = date_match.group(1) if date_match else "" 
                elif "Reference PO:" in line:
                    po_match = re.search(r'Reference PO:\s*(\d+)', line)
                    po_number = po_match.group(1) if po_match else ""

            # Look for line items
            # item_pattern = r'(\d+\.\d+)\s+(N\d+-\d+)\s+(.*?)\s+(\d+\.\d+)\s+EA\s+\$\s*([\d,]+\.\d+)\s+\$\s*([\d,]+\.\d+)'
            item_pattern = r'(\d+\.\d+)\s+([A-Z]\d+-\d+)\s+(.*?)\s+(\d+\.\d+)\s+EA\s+\$\s*([\d,]+\.\d+)\s+\$\s*([\d,]+\.\d+)'



            for i, line in enumerate(lines):
                item_match = re.search(item_pattern, line)
                if item_match:
                    # Extract item details
                    novo_item = item_match.group(2)
                    quantity = item_match.group(4)
                    price_each = item_match.group(5)

                    # Look for lot number in subsequent lines
                    lot_number = ""
                    for j in range(i, min(i + 3, len(lines))):  # Check next 3 lines
                        search_line = lines[j]
                        # Updated pattern to match exact format from your example
                        lot_match = re.search(r'Lot/Qty:\s\s*([\d\-]+(?:[\-/]\d+)*)\s*/\s*\d+', search_line)
                        if lot_match:
                            lot_number = lot_match.group(1)
                            break

                    item_data = {
                        'invoice_date': invoice_date,
                        'invoice_number': invoice_number,
                        'purchase_order': po_number,
                        'vendor_item': '',  # Avalign doesn't show vendor item numbers
                        'novo_item': novo_item,
                        'lot_number': lot_number,
                        'quantity': quantity,
                        'price_each': price_each.replace(',', ''),
                        'page_number': page_num + 1
                    }

                    # Debug information
                    st.write(f"Processing item {novo_item}:")
                    st.write(f"Looking for lot in lines:")
                    for j in range(i, min(i + 3, len(lines))):
                        st.write(f"Line {j}: {lines[j]}")
                    st.write(f"Found lot number: {lot_number}")

                    extracted_data.append(item_data)

    return extracted_data


#ackermann
def extract_ackermann_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Ackermann Instrumente GmbH invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_invoice_info(lines)
            
            # Find item blocks by looking for lines with item numbers and descriptions
            item_blocks = []
            current_block = []
            
            for i, line in enumerate(lines):
                # Look for lines that likely contain item information
                if (re.search(r'item no\.', line, re.IGNORECASE) or 
                    (re.search(r'\d{6,}', line) and re.search(r'desc\.', line, re.IGNORECASE))):
                    if current_block:
                        item_blocks.append(current_block)
                    current_block = [line]
                elif current_block and not re.search(r'^(Gross|Subtotal|Total)', line, re.IGNORECASE):
                    current_block.append(line)
                elif current_block and re.search(r'^(Gross|Subtotal|Total)', line, re.IGNORECASE):
                    item_blocks.append(current_block)
                    current_block = []
            
            if current_block:
                item_blocks.append(current_block)
            
            # Process each item block
            for block in item_blocks:
                item_data = _parse_ackermann_item_block(block, invoice_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _parse_ackermann_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Ackermann invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'position': '',
        'item_no': '',
        'description': '',
        'po_no': '',
        'quantity': '',
        'unit_price': '',
        'discount': '',
        'total': '',
        'order_no': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # Join block for easier parsing
    block_text = ' '.join(block)
    
    # Extract position number from the first line
    pos_match = re.search(r'^(\d+)\s+', block[0])
    if pos_match:
        item_data['position'] = pos_match.group(1)
    
    # Parse the main item line which contains most of the data
    # Format: "10 Item No. NS52500-28-01-1 266870 3pcs. 252,12 23,72 576,96"
    item_line_match = re.search(r'^\d+\s+Item No\.\s+([^\s]+)\s+(\d+)\s+(\d+)pcs\.\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)', block[0])
    if item_line_match:
        item_data['item_no'] = item_line_match.group(1)
        item_data['po_no'] = item_line_match.group(2)
        item_data['quantity'] = item_line_match.group(3)
        item_data['unit_price'] = item_line_match.group(4).replace(',', '.')
        item_data['discount'] = item_line_match.group(5).replace(',', '.')
        item_data['total'] = item_line_match.group(6).replace(',', '.')
    
    # Extract description from the following lines
    desc_lines = []
    for line in block[1:]:
        if re.search(r'Desc\.', line, re.IGNORECASE):
            # Remove "Desc." prefix and get the description
            desc_match = re.search(r'Desc\.\s*(.+)', line, re.IGNORECASE)
            if desc_match:
                desc_lines.append(desc_match.group(1))
        elif re.search(r'LST:|Authorization|Your Order|Lot\.', line, re.IGNORECASE):
            # Stop when we hit other metadata
            break
        elif desc_lines:
            # Continue adding to description if we've already started
            desc_lines.append(line.strip())
    
    if desc_lines:
        item_data['description'] = ' '.join(desc_lines).strip()
    
    # Extract other fields from the block
    for line in block:
        # Extract order number
        order_match = re.search(r'Your Order No\.\s+([^\s-]+)', line, re.IGNORECASE)
        if order_match and not item_data['order_no']:
            item_data['order_no'] = order_match.group(1)
        
        # Extract lot information
        lot_match = re.search(r'Lot\.\s+(.+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
    
    # Only return if we have at least some basic item information
    if item_data['item_no'] or item_data['description']:
        return item_data
    
    return None

#betzler
def extract_betzler_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from A. Betzler GmbH invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_invoice_info(lines)
            
            # Find item blocks by looking for order references
            item_blocks = []
            current_block = []
            
            for line in lines:
                if re.search(r'your order', line, re.IGNORECASE):
                    if current_block:
                        item_blocks.append(current_block)
                    current_block = [line]
                elif current_block:
                    if re.search(r'your order', line, re.IGNORECASE) or re.search(r'total', line, re.IGNORECASE):
                        item_blocks.append(current_block)
                        current_block = [line] if re.search(r'your order', line, re.IGNORECASE) else []
                    else:
                        current_block.append(line)
            
            if current_block:
                item_blocks.append(current_block)
            
            # Process each item block
            for block in item_blocks:
                item_data = _parse_betzler_item_block(block, invoice_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _parse_betzler_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Betzler invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': '',
        'order_date': '',
        'description': '',
        'quantity': '',
        'price': '',
        'art_no': '',
        'mdl_reg_no': '',
        'lot_number': '',
        'page': page_num + 1
    }
    
    block_text = ' '.join(block)
    
    # Extract order information
    order_match = re.search(r'your order no\.?\s*([^\s]+)[^\d]*(\d{1,2}\.\d{1,2}\.\d{2,4})', block_text, re.IGNORECASE)
    if order_match:
        item_data['order_no'] = order_match.group(1)
        item_data['order_date'] = order_match.group(2)
    
    # Extract position number and article code from the first line after order number
    # Format: "1 BA 6001-18 micro-scissor, round handle 10 118,19 1.181,90"
    item_line_match = re.search(r'^(\d+)\s+([A-Z]+\s+[A-Z0-9\-]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', block[1] if len(block) > 1 else '')
    if item_line_match:
        item_data['quantity'] = item_line_match.group(4)
        item_data['price'] = item_line_match.group(6).replace(',', '.')  # Total price
        
        # Build description from multiple lines
        description_parts = [item_line_match.group(3)]  # First part from the item line
        
        # Add subsequent description lines until we hit metadata
        for i in range(2, len(block)):
            line = block[i]
            if re.search(r'your art\.|MDL Reg\.|Lot number|customs', line, re.IGNORECASE):
                break
            description_parts.append(line.strip())
        
        item_data['description'] = ' '.join(description_parts).strip()
    
    # Extract other fields from the block
    for line in block:
        # Extract article number
        art_match = re.search(r'your art\.-no\.:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match and not item_data['art_no']:
            item_data['art_no'] = art_match.group(1)
        
        # Extract MDL registration number
        mdl_match = re.search(r'MDL Reg\. No\.:\s*([^\s/]+)', line, re.IGNORECASE)
        if mdl_match and not item_data['mdl_reg_no']:
            item_data['mdl_reg_no'] = mdl_match.group(1)
        
        # Extract lot number
        lot_match = re.search(r'Lot number\s+([^\s]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot_number']:
            item_data['lot_number'] = lot_match.group(1)
    
    # Only return if we have at least quantity and price
    if item_data['quantity'] and item_data['price']:
        return item_data
    
    return None


#hipp
def extract_hipp_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Anton Hipp GmbH invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_invoice_info(lines)
            
            # Find order confirmation sections
            order_blocks = []
            current_order_block = []
            in_order_block = False
            
            for line in lines:
                line_clean = line.strip()
                
                # Start of order confirmation block
                if re.search(r'Order confirmation\s+\d+', line_clean, re.IGNORECASE):
                    if current_order_block and in_order_block:
                        order_blocks.append(current_order_block)
                    current_order_block = [line_clean]
                    in_order_block = True
                
                # Continue adding to current order block
                elif in_order_block:
                    if (re.search(r'Order confirmation\s+\d+', line_clean, re.IGNORECASE) or
                        re.search(r'to be carried over|total|Value of goods|Page', line_clean, re.IGNORECASE)):
                        order_blocks.append(current_order_block)
                        current_order_block = [line_clean] if re.search(r'Order confirmation\s+\d+', line_clean, re.IGNORECASE) else []
                        in_order_block = bool(current_order_block)
                    else:
                        current_order_block.append(line_clean)
            
            if current_order_block and in_order_block:
                order_blocks.append(current_order_block)
            
            # Process each order confirmation block to find individual items
            for order_block in order_blocks:
                # Extract order info from the order block header
                order_info = _extract_hipp_order_info(order_block)
                
                # Find individual items within this order block
                item_blocks = []
                current_item_block = []
                in_item_block = False
                
                for line in order_block:
                    line_clean = line.strip()
                    
                    # Start of item block (article number or product line)
                    if (re.search(r'^\d{7}\s+[A-Z]\d{6}\s+[A-Z]{3}', line_clean) or  # 8010528 A915928 LRW
                        re.search(r'Ref\.-No\.', line_clean) or  # Ref.-No.E7862-25
                        re.search(r'^\d+\s+\(\d+\)\s+[A-Z0-9\.]+\s+[A-Z]', line_clean)):  # 3 (1) 1.045.14 AUFRICHT
                        
                        if current_item_block and in_item_block:
                            item_blocks.append(current_item_block)
                        current_item_block = [line_clean]
                        in_item_block = True
                    
                    # Continue adding to current item block (include lot and quantity lines)
                    elif in_item_block:
                        if (re.search(r'^\d{7}\s+[A-Z]\d{6}\s+[A-Z]{3}', line_clean) or
                            re.search(r'Ref\.-No\.', line_clean) or
                            re.search(r'^\d+\s+\(\d+\)\s+[A-Z0-9\.]+\s+[A-Z]', line_clean) or
                            re.search(r'to be carried over', line_clean, re.IGNORECASE)):
                            
                            item_blocks.append(current_item_block)
                            current_item_block = [line_clean] if not re.search(r'to be carried over', line_clean, re.IGNORECASE) else []
                            in_item_block = bool(current_item_block)
                        else:
                            # Include lot and quantity lines in the item block
                            current_item_block.append(line_clean)
                
                if current_item_block and in_item_block:
                    item_blocks.append(current_item_block)
                
                # Process each item block with the order info
                for item_block in item_blocks:
                    # Combine order info with item details
                    full_block = order_block[:2] + item_block  # First 2 lines contain order info
                    item_data = _parse_hipp_item_block(full_block, invoice_data, page_num)
                    if item_data:
                        extracted_data.append(item_data)
    
    return extracted_data

def _extract_hipp_order_info(order_block: List[str]) -> Dict[str, str]:
    """Extract order information from order confirmation block"""
    order_info = {
        'confirmation_no': '',
        'order_no': '',
        'order_date': ''
    }
    
    # Check first two lines for order information
    for i, line in enumerate(order_block[:2]):
        line_clean = line.strip()
        
        # Extract confirmation number from first line
        if i == 0:
            conf_match = re.search(r'Order confirmation\s+(\d+)', line_clean, re.IGNORECASE)
            if conf_match:
                order_info['confirmation_no'] = conf_match.group(1)
        
        # Extract order number and date from second line
        if i == 1:
            order_match = re.search(r'Your order\s+([^\s]+)', line_clean, re.IGNORECASE)
            if order_match:
                order_info['order_no'] = order_match.group(1)
            
            date_match = re.search(r'dtd\.?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
            if date_match:
                order_info['order_date'] = date_match.group(1)
    
    return order_info

def _parse_hipp_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Hipp invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'confirmation_no': '',
        'order_no': '',
        'order_date': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # Extract order information from the first two lines of the block
    order_info = _extract_hipp_order_info(block)
    item_data['confirmation_no'] = order_info['confirmation_no']
    item_data['order_no'] = order_info['order_no']
    item_data['order_date'] = order_info['order_date']
    
    block_text = ' '.join(block)
    
    # Extract description - look for the product name line
    # Format: "3 (1) 1.045.14 AUFRICHT Scissor 14.5 cm curved 3,00pcs 20,14 60,42"
    desc_match = re.search(r'^\d+\s+\(\d+\)\s+[A-Z0-9\.]+\s+(.+?)\s+(\d+,\d+)\s*(?:pcs|Stck|stck)\s*([\d,]+)\s*([\d,]+)', block_text)
    if desc_match:
        item_data['description'] = desc_match.group(1).strip()
        item_data['quantity'] = desc_match.group(2).replace(',', '.')
        item_data['unit_price'] = desc_match.group(3).replace(',', '.')
        item_data['total_price'] = desc_match.group(4).replace(',', '.')
    
    # Alternative approach: extract from individual lines
    if not item_data['description']:
        desc_lines = []
        for line in block:
            # Look for lines that contain product descriptions
            if (re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+\s+', line) and  # Multiple words with capitalization
                not re.search(r'^\d{7}|Ref\.-No\.|Lot:|Quantity:|Order|Page', line)):  # Exclude metadata lines
                desc_lines.append(line.strip())
        
        if desc_lines:
            item_data['description'] = ' '.join(desc_lines).strip()
    
    # Extract quantity from alternative format
    if not item_data['quantity']:
        qty_match = re.search(r'Quantity:\s*(\d+)', block_text, re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    # Extract lot number - look for "Lot:XXXXX" pattern (more flexible pattern)
    lot_match = re.search(r'Lot:\s*(\d+)', block_text, re.IGNORECASE)
    if lot_match:
        item_data['lot'] = lot_match.group(1)
    
    # If lot still not found, try a more specific search in individual lines
    if not item_data['lot']:
        for line in block:
            lot_line_match = re.search(r'Lot:\s*(\d+)', line, re.IGNORECASE)
            if lot_line_match:
                item_data['lot'] = lot_line_match.group(1)
                break
    
    # Extract unit price and total from alternative formats
    if not item_data['unit_price']:
        price_match = re.search(r'(\d+,\d+)\s*(?:pcs|Stck|stck)\s*([\d,]+)\s*([\d,]+)', block_text)
        if price_match:
            item_data['quantity'] = price_match.group(1).replace(',', '.')
            item_data['unit_price'] = price_match.group(2).replace(',', '.')
            item_data['total_price'] = price_match.group(3).replace(',', '.')
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#aspen
def extract_aspen_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Aspen Surgical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_aspen_invoice_info(lines)
            
            # Find the start of the items table
            start_index = -1
            for i, line in enumerate(lines):
                if re.search(r'Part No\s+Description\s+Invoice Qty\s+U of M\s+Unit Price\s+Net Amount', line, re.IGNORECASE):
                    start_index = i + 2  # Skip header and line numbers
                    break
            
            if start_index == -1:
                # Alternative pattern for table header
                for i, line in enumerate(lines):
                    if re.search(r'Part No.*Description.*Invoice Qty.*Unit Price.*Net Amount', line, re.IGNORECASE):
                        start_index = i + 2
                        break
            
            if start_index == -1:
                # If no table header found, look for item lines directly
                start_index = 0
            
            # Find item blocks - include all related lines
            item_blocks = []
            current_block = []
            in_item_block = False
            
            for i in range(start_index, len(lines)):
                line = lines[i].strip()
                
                # Skip empty lines and header lines
                if not line or re.search(r'Line No|Lot Number|USD', line, re.IGNORECASE):
                    continue
                
                # Look for lines that start with part numbers (like 096129BBG)
                if re.match(r'^\d{6,}[A-Z]*', line) and not re.search(r'Sub Total|Total|Tax|Handling', line, re.IGNORECASE):
                    if current_block and in_item_block:
                        item_blocks.append(current_block)
                    current_block = [line]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next item
                    if (re.match(r'^\d{6,}[A-Z]*', line) or
                        re.search(r'Sub Total|Total|Tax|Handling', line, re.IGNORECASE)):
                        
                        item_blocks.append(current_block)
                        current_block = [line] if re.match(r'^\d{6,}[A-Z]*', line) else []
                        in_item_block = bool(re.match(r'^\d{6,}[A-Z]*', line))
                    else:
                        # Include all lines until next item (including LOT lines)
                        current_block.append(line)
            
            if current_block and in_item_block:
                item_blocks.append(current_block)
            
            # Process each item block
            for block in item_blocks:
                item_data = _parse_aspen_item_block(block, invoice_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_aspen_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Aspen invoice with specific patterns"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_number': ''
    }
    
    # Look for the specific line patterns
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Look for the line with address followed by date and invoice number
        # Pattern: "6945 Southbelt Dr. SE | Caledonia, MI 49316 11/6/23 CD3038894"
        if re.search(r'Caledonia.*\d{5}', line_clean) and re.search(r'\d{1,2}/\d{1,2}/\d{2,4}\s+[A-Z]{2}\d{7}', line_clean):
            # Extract invoice date and number
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line_clean)
            inv_match = re.search(r'([A-Z]{2}\d{7})', line_clean)
            
            if date_match and not invoice_data['invoice_date']:
                invoice_data['invoice_date'] = date_match.group(1)
            if inv_match and not invoice_data['invoice_number']:
                invoice_data['invoice_number'] = inv_match.group(1)
        
        # Look for the line with phone number followed by date and order number
        # Pattern: "phone: (888) 364-7004 | fax: (616) 698-9281 11/3/23 C1166613"
        elif re.search(r'phone.*fax.*\d{1,2}/\d{1,2}/\d{2,4}\s+[A-Z]\d{6,7}', line_clean, re.IGNORECASE):
            # Extract order number only (skip the date)
            order_match = re.search(r'([A-Z]\d{6,7})', line_clean)
            if order_match and not invoice_data['order_number']:
                invoice_data['order_number'] = order_match.group(1)
    
    # If still not found, try a more direct approach
    if not all([invoice_data['invoice_number'], invoice_data['invoice_date'], invoice_data['order_number']]):
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Look for invoice number pattern with date nearby
            inv_match = re.search(r'([A-Z]{2}\d{7})', line_clean)
            if inv_match and not invoice_data['invoice_number']:
                # Check if there's a date on the same line
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line_clean)
                if date_match:
                    invoice_data['invoice_number'] = inv_match.group(1)
                    invoice_data['invoice_date'] = date_match.group(1)
            
            # Look for order number pattern
            order_match = re.search(r'([A-Z]\d{6,7})', line_clean)
            if order_match and not invoice_data['order_number']:
                # Make sure it's not the invoice number
                if not re.search(r'[A-Z]{2}\d{7}', order_match.group(1)):
                    invoice_data['order_number'] = order_match.group(1)
    
    return invoice_data

def _parse_aspen_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Aspen invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data.get('invoice_date', ''),
        'invoice_number': invoice_data.get('invoice_number', ''),
        'order_number': invoice_data.get('order_number', ''),
        'part_no': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'net_amount': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract part number (first word in the line)
    part_match = re.match(r'^(\d+[A-Z]*)', first_line)
    if part_match:
        item_data['part_no'] = part_match.group(1)
    
    # Try to extract the main item data using multiple patterns
    # Pattern: PartNo Description Qty UOM UnitPrice NetAmount
    pattern = r'^\d+[A-Z]*\s+(.+?)\s+(\d+)\s+[A-Z]{2}\s+([\d,\.]+)\s+([\d,\.]+)$'
    match = re.search(pattern, first_line)
    
    if match:
        item_data['description'] = match.group(1).strip()
        item_data['quantity'] = match.group(2)
        item_data['unit_price'] = match.group(3).replace(',', '')
        item_data['net_amount'] = match.group(4).replace(',', '')
    
    # If the first pattern didn't match, try a more flexible pattern
    if not item_data['quantity']:
        # Pattern: Look for number followed by 2-letter UOM followed by prices
        flex_pattern = r'(.+?)\s+(\d+)\s+[A-Z]{2}\s+([\d,\.]+)\s+([\d,\.]+)$'
        flex_match = re.search(flex_pattern, first_line)
        if flex_match:
            # Remove part number from description
            desc = re.sub(r'^\d+[A-Z]*\s*', '', flex_match.group(1)).strip()
            item_data['description'] = desc
            item_data['quantity'] = flex_match.group(2)
            item_data['unit_price'] = flex_match.group(3).replace(',', '')
            item_data['net_amount'] = flex_match.group(4).replace(',', '')
    
    # If description is still empty, try a simpler approach
    if not item_data['description']:
        # Remove part number, then take the rest as description (excluding quantity, UOM and prices)
        desc_line = re.sub(r'^\d+[A-Z]*\s*', '', first_line)
        # Remove quantity, UOM, price fields from the end
        desc_line = re.sub(r'\s+\d+\s+[A-Z]{2}\s+[\d,\.]+\s+[\d,\.]+$', '', desc_line)
        item_data['description'] = desc_line.strip()
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for pattern: number + 2-letter UOM + price + price
        qty_match = re.search(r'\s+(\d+)\s+[A-Z]{2}\s+[\d,\.]+\s+[\d,\.]+$', first_line)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        # The last two numbers are unit price and net amount
        prices = re.findall(r'[\d,\.]+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '')
            item_data['net_amount'] = prices[-1].replace(',', '')
    
    # Extract lot number from the entire block - more thorough search
    for line in block:
        # More flexible lot number pattern to handle various formats
        lot_match = re.search(r'LOT[:\s]*([0-9][0-9\-\.\*]*)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1).strip()
            break
    
    # If still not found, try even more flexible pattern
    if not item_data['lot']:
        for line in block:
            # Look for any pattern that starts with LOT and has numbers/dashes
            lot_match = re.search(r'LOT[^\d]*([\d\-\.\*]+)', line, re.IGNORECASE)
            if lot_match:
                item_data['lot'] = lot_match.group(1).strip()
                break
    
    # For multi-line descriptions, combine them (excluding lot lines)
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't contain LOT, HTS, COO patterns
            if not re.search(r'LOT:|HTS:|COO:', line, re.IGNORECASE):
                additional_desc.append(line.strip())
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Only return if we have at least part number and description
    if item_data['part_no'] and item_data['description']:
        return item_data
    
    return None

# Reuchlen cid encoding issue.

#bahadir
def extract_bahadir_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Bahadir USA invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract Bahadir-specific invoice info
            invoice_data = _extract_bahadir_invoice_info(lines)
            po_number = ""
            lot_number = ""
            
            for line in lines:
                po_match = re.search(r'p\.o\.\s*[:#]?\s*(\d+)', line, re.IGNORECASE)
                if po_match:
                    po_number = po_match.group(1)
                
                lot_match = re.search(r'lot\s*[:#]?\s*(\d+)', line, re.IGNORECASE)
                if lot_match:
                    lot_number = lot_match.group(1)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            
            for line in lines:
                if re.match(r'^\d+\s+[A-Z0-9]', line):
                    if current_block:
                        item_blocks.append(current_block)
                    current_block = [line]
                elif current_block:
                    if re.match(r'^\d+\s+[A-Z0-9]', line) or re.search(r'total|balance', line, re.IGNORECASE):
                        item_blocks.append(current_block)
                        current_block = [line] if re.match(r'^\d+\s+[A-Z0-9]', line) else []
                    else:
                        current_block.append(line)
            
            if current_block:
                item_blocks.append(current_block)
            
            # Process each item block
            for block in item_blocks:
                item_data = _parse_bahadir_item_block(block, invoice_data, po_number, lot_number, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_bahadir_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Bahadir invoice with specific patterns"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': ''
    }
    
    for line in lines:
        # Extract invoice number - look for "Invoice # 2664" pattern
        inv_match = re.search(r'Invoice\s*#\s*(\d+)', line, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date - look for date pattern
        date_match = re.search(r'Date\s*#\s*(\d{1,2}/\d{1,2}/\d{4})', line, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
    
    # If not found with specific patterns, try general patterns
    if not invoice_data['invoice_number']:
        for line in lines:
            inv_match = re.search(r'Invoice.*?(\d{3,})', line, re.IGNORECASE)
            if inv_match and not invoice_data['invoice_number']:
                invoice_data['invoice_number'] = inv_match.group(1)
    
    if not invoice_data['invoice_date']:
        for line in lines:
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
            if date_match and not invoice_data['invoice_date']:
                invoice_data['invoice_date'] = date_match.group(1)
    
    return invoice_data

def _parse_bahadir_item_block(block: List[str], invoice_data: Dict, po_number: str, lot_number: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Bahadir invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data.get('invoice_date', ''),
        'invoice_number': invoice_data.get('invoice_number', ''),
        'po_number': po_number,
        'lot_number': lot_number,
        'line_no': '',
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total': '',
        'page': page_num + 1
    }
    
    # Join block for easier parsing
    block_text = ' '.join(block)
    
    # Extract line number
    line_match = re.search(r'^(\d+)\s+', block[0])
    if line_match:
        item_data['line_no'] = line_match.group(1)
    
    # Extract item code, description, quantity, unit price, and total
    # More flexible pattern to handle variations
    item_match = re.search(r'^\d+\s+([A-Z0-9\.]+)\s+(.+?)\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$', block[0])
    if item_match:
        item_data['item_code'] = item_match.group(1)
        item_data['description'] = item_match.group(2)
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '')
        item_data['total'] = item_match.group(5).replace(',', '')
    
    # Alternative pattern if the first one doesn't match
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+([A-Z0-9\.]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', block[0])
        if alt_match:
            item_data['item_code'] = alt_match.group(1)
            item_data['description'] = alt_match.group(2)
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '')
            item_data['total'] = alt_match.group(5).replace(',', '')
    
    # Only return if we have at least item code and description
    if item_data['item_code'] and item_data['description']:
        return item_data
    
    return None

#bauer
def extract_bauer_hasselbarth_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Bauer und Hasselbarth invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice info
            invoice_data = _extract_bauer_invoice_info(lines)
            
            # Extract PO number and LOT numbers
            po_number = ""
            current_lot = ""
            
            for line in lines:
                # Extract PO number
                po_match = re.search(r'Your Order Number\s+(\d+)', line, re.IGNORECASE)
                if po_match:
                    po_number = po_match.group(1)
                
                # Extract LOT number
                lot_match = re.search(r'LOT:\s*(\d+)', line, re.IGNORECASE)
                if lot_match:
                    current_lot = lot_match.group(1)
            
            # Find item blocks - look for lines that start with position numbers
            item_blocks = []
            current_block = []
            in_item_block = False
            
            for line in lines:
                # Check if line starts with a position number (like "1 ", "2 ", etc.)
                if re.match(r'^\d+\s+[A-Z0-9\-]', line.strip()):
                    if current_block:
                        item_blocks.append(current_block)
                    current_block = [line]
                    in_item_block = True
                elif in_item_block:
                    # Check if this is a continuation line (contains LOT/LST or description)
                    if re.search(r'LOT:|LST:|Speculum|Sound|marking', line, re.IGNORECASE) or not re.search(r'total|carry-over|page|\d+,\d+', line, re.IGNORECASE):
                        current_block.append(line)
                    else:
                        # End of item block
                        if current_block:
                            item_blocks.append(current_block)
                        current_block = []
                        in_item_block = False
            
            if current_block:
                item_blocks.append(current_block)
            
            # Process each item block
            for block in item_blocks:
                item_data = _parse_bauer_item_block(block, invoice_data, po_number, current_lot, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_bauer_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Bauer invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': ''
    }
    
    for line in lines:
        # Extract invoice number
        inv_match = re.search(r'Invoice Number\s+(\d+)', line, re.IGNORECASE)
        if inv_match:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s+(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if date_match:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Customer Number\s+(\d+)', line, re.IGNORECASE)
        if cust_match:
            invoice_data['customer_number'] = cust_match.group(1)
    
    return invoice_data

def _parse_bauer_item_block(block: List[str], invoice_data: Dict, po_number: str, lot_number: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Bauer invoice"""
    if not block:
        return None
    
    # Join block for analysis
    block_text = ' '.join(block)
    
    # Skip if this doesn't look like an item line
    if not re.search(r'\d+\s+[A-Z0-9\-]+\s+.*\d+\s+[pcs|Stk]\.?\s+\d+,\d+\s+\d+,\d+', block_text):
        return None
    
    item_data = {
        'invoice_date': invoice_data.get('invoice_date', ''),
        'invoice_number': invoice_data.get('invoice_number', ''),
        'customer_number': invoice_data.get('customer_number', ''),
        'po_number': po_number,
        'lot_number': lot_number,
        'line_no': '',
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total': '',
        'page': page_num + 1
    }
    
    # Extract line number from first line
    line_match = re.search(r'^(\d+)\s+', block[0])
    if line_match:
        item_data['line_no'] = line_match.group(1)
    
    # Parse the main item line - Bauer format: "Pos. Art-No. Description Qty. Price Total"
    item_pattern = r'^\d+\s+([A-Z0-9\-\.]+(?:\s+[A-Z0-9\-\.]+)?)\s+(.+?)\s+(\d+)\s+[pcs|Stk]\.?\s+([\d,]+)\s+([\d,]+)$'
    
    # Try different patterns to match the item data
    patterns = [
        r'^\d+\s+([A-Z0-9\-\.]+(?:\s+[A-Z0-9\-\.]+)?)\s+(.+?)\s+(\d+)\s+[pcs|Stk]\.?\s+([\d,]+)\s+([\d,]+)$',
        r'^\d+\s+([A-Z0-9\-\.]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$'
    ]
    
    for pattern in patterns:
        item_match = re.search(pattern, block[0])
        if item_match:
            item_data['item_code'] = item_match.group(1).strip()
            item_data['description'] = item_match.group(2).strip()
            item_data['quantity'] = item_match.group(3)
            item_data['unit_price'] = item_match.group(4).replace(',', '.')
            item_data['total'] = item_match.group(5).replace(',', '.')
            break
    
    # If we couldn't parse with regex, try a more manual approach
    if not item_data['item_code']:
        parts = block[0].split()
        if len(parts) >= 6:
            try:
                item_data['item_code'] = parts[1]
                # Description is everything between item code and quantity
                qty_index = next((i for i, part in enumerate(parts) if part.isdigit() and i > 1), -1)
                if qty_index > 2:
                    item_data['description'] = ' '.join(parts[2:qty_index])
                    item_data['quantity'] = parts[qty_index]
                    item_data['unit_price'] = parts[qty_index + 1].replace(',', '.')
                    item_data['total'] = parts[qty_index + 2].replace(',', '.')
            except (IndexError, ValueError):
                pass
    
    # Add additional description from subsequent lines if available
    if len(block) > 1:
        additional_desc = []
        for line in block[1:]:
            if re.search(r'LOT:|LST:|Your Order Number', line):
                continue
            if not re.search(r'\d+,\d+\s+\d+,\d+$', line):  # Skip lines that look like prices
                additional_desc.append(line.strip())
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Clean up description
    item_data['description'] = re.sub(r'\s+', ' ', item_data['description']).strip()
    
    # Only return if we have essential data
    if item_data['item_code'] and item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

#biselli
def extract_biselli_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Biselli Medical Instruments invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Extract invoice information
        invoice_data = _extract_biselli_invoice_info(full_text)
        
        # Extract items
        items = _extract_biselli_items(full_text, invoice_data)
        extracted_data.extend(items)
    
    return extracted_data

def _extract_biselli_invoice_info(full_text: str) -> Dict[str, str]:
    """Extract invoice information from Biselli invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_number': '',
        'order_date': '',
        'delivery_note': '',
        'delivery_date': '',
        'lot_number': '',
        'lst_number': ''
    }
    
    # Extract invoice number
    inv_match = re.search(r'INVOICE NO\.\s*(\d+)', full_text)
    if inv_match:
        invoice_data['invoice_number'] = inv_match.group(1)
    
    # Extract invoice date
    date_match = re.search(r'Date\s*(\d{2}\.\d{2}\.\d{4})', full_text)
    if date_match:
        invoice_data['invoice_date'] = date_match.group(1)
    
    # Extract customer number
    cust_match = re.search(r'Cust\.-No\.\s*(\d+)', full_text)
    if cust_match:
        invoice_data['customer_number'] = cust_match.group(1)
    
    # Extract order number and date
    order_match = re.search(r'Your Order No\.\s*(\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', full_text)
    if order_match:
        invoice_data['order_number'] = order_match.group(1)
        invoice_data['order_date'] = order_match.group(2)
    
    # Extract delivery note and date
    delivery_match = re.search(r'Delivery Note No\.\s*(\d+)\s*At\s*(\d{2}\.\d{2}\.\d{4})', full_text)
    if delivery_match:
        invoice_data['delivery_note'] = delivery_match.group(1)
        invoice_data['delivery_date'] = delivery_match.group(2)
    
    # Extract LOT number
    lot_match = re.search(r'Lot No\.\s*(\d+)', full_text, re.IGNORECASE)
    if lot_match:
        invoice_data['lot_number'] = lot_match.group(1)
    
    # Extract LST number
    lst_match = re.search(r'LST:\s*([A-Z0-9/ ]+)', full_text)
    if lst_match:
        invoice_data['lst_number'] = lst_match.group(1).strip()
    
    return invoice_data

def _extract_biselli_items(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract items from Biselli invoice text"""
    items = []
    
    # Find the main item section between the record markers
    record_start = full_text.find('FDA Registration No. DEV 96 11 617')
    record_end = full_text.find('Total/EUR')
    
    if record_start != -1 and record_end != -1:
        record_section = full_text[record_start:record_end]
        
        # Look for the item line pattern: position + product code + description + quantity + price + total
        item_pattern = r'(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)'
        matches = re.finditer(item_pattern, record_section, re.DOTALL)
        
        for match in matches:
            item_data = {
                'invoice_number': invoice_data.get('invoice_number', ''),
                'invoice_date': invoice_data.get('invoice_date', ''),
                'order_number': invoice_data.get('order_number', ''),
                'order_date': invoice_data.get('order_date', ''),
                'delivery_note': invoice_data.get('delivery_note', ''),
                'delivery_date': invoice_data.get('delivery_date', ''),
                'lot_number': invoice_data.get('lot_number', ''),
                'lst_number': invoice_data.get('lst_number', ''),
                'position': match.group(1),
                'article_number': '',  # Leave blank as absent
                'description': match.group(3).strip(),
                'quantity': match.group(4),
                'unit_price': match.group(5).replace(',', '.'),
                'total_price': match.group(6).replace(',', '.')
            }
            
            # Clean up description
            item_data['description'] = re.sub(r'\s+', ' ', item_data['description']).strip()
            items.append(item_data)
    
    # If no items found with regex, use manual extraction
    if not items:
        items = _extract_biselli_items_manual(full_text, invoice_data)
    
    return items

def _extract_biselli_items_manual(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Manual extraction for Biselli items"""
    items = []
    lines = full_text.split('\n')
    
    # Find the record section
    record_start = -1
    record_end = -1
    
    for i, line in enumerate(lines):
        if 'FDA Registration No. DEV 96 11 617' in line:
            record_start = i
        if 'Total/EUR' in line and record_start != -1:
            record_end = i
            break
    
    if record_start != -1 and record_end != -1:
        record_lines = lines[record_start:record_end]
        
        for i, line in enumerate(record_lines):
            line = line.strip()
            
            # Look for item lines (start with number, contain product description)
            if re.match(r'^\d+\s+[A-Z]', line) and any(keyword in line for keyword in ['Castroviejo', 'Needle', 'Holder']):
                try:
                    # Split the line to extract components
                    parts = line.split()
                    
                    # Position is first element
                    position = parts[0]
                    
                    # Product code is second element
                    product_code = parts[1]
                    
                    # Find quantity, unit price, and total price
                    quantity = None
                    unit_price = None
                    total_price = None
                    
                    # Look for numeric values at the end of the line
                    price_pattern = r'(\d+)\s+([\d,]+)\s+([\d,]+)$'
                    price_match = re.search(price_pattern, line)
                    
                    if price_match:
                        quantity = price_match.group(1)
                        unit_price = price_match.group(2).replace(',', '.')
                        total_price = price_match.group(3).replace(',', '.')
                    
                    if quantity and unit_price and total_price:
                        # Extract description (everything between product code and prices)
                        desc_start = line.find(product_code) + len(product_code)
                        desc_end = line.find(quantity, desc_start)
                        description = line[desc_start:desc_end].strip()
                        
                        # Check if next line continues description
                        if i + 1 < len(record_lines):
                            next_line = record_lines[i + 1].strip()
                            if not re.match(r'^\d+|Lot No\.|LST:', next_line):
                                description += ' ' + next_line
                        
                        item_data = {
                            'invoice_number': invoice_data.get('invoice_number', ''),
                            'invoice_date': invoice_data.get('invoice_date', ''),
                            'order_number': invoice_data.get('order_number', ''),
                            'order_date': invoice_data.get('order_date', ''),
                            'delivery_note': invoice_data.get('delivery_note', ''),
                            'delivery_date': invoice_data.get('delivery_date', ''),
                            'lot_number': invoice_data.get('lot_number', ''),
                            'lst_number': invoice_data.get('lst_number', ''),
                            'position': position,
                            'article_number': '',  # Leave blank
                            'description': description,
                            'quantity': quantity,
                            'unit_price': unit_price,
                            'total_price': total_price
                        }
                        items.append(item_data)
                        
                except (IndexError, ValueError):
                    continue
    
    return items

#blache
def extract_blache_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Blache Medical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Extract invoice information
        invoice_data = _extract_blache_invoice_info(full_text)
        
        # Extract items by finding item blocks
        items = _extract_blache_item_blocks(full_text, invoice_data)
        extracted_data.extend(items)
    
    return extracted_data

def _extract_blache_invoice_info(full_text: str) -> Dict[str, str]:
    """Extract invoice information from Blache invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'vat_number': ''
    }
    
    # Extract invoice number
    inv_match = re.search(r'Invoice no\.\s*(\d+)', full_text, re.IGNORECASE)
    if inv_match:
        invoice_data['invoice_number'] = inv_match.group(1)
    
    # Extract invoice date
    date_match = re.search(r'Invoice Date\s*(\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
    if date_match:
        invoice_data['invoice_date'] = date_match.group(1)
    
    # Extract customer number
    cust_match = re.search(r'Your Customer no\.\s*(\d+)', full_text, re.IGNORECASE)
    if cust_match:
        invoice_data['customer_number'] = cust_match.group(1)
    
    # Extract VAT number
    vat_match = re.search(r'Your VAT\s*([A-Z0-9]+)', full_text, re.IGNORECASE)
    if vat_match:
        invoice_data['vat_number'] = vat_match.group(1)
    
    return invoice_data

def _extract_blache_item_blocks(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract complete item blocks from Blache invoice text"""
    items = []
    lines = full_text.split('\n')
    
    current_block = []
    in_item_block = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Look for the start of an item block (line starting with number + article number)
        if re.match(r'^\d+\s+[A-Z0-9\-]', line) and any(x in line for x in ['pcs.', 'BSI-', 'N6971', 'N9126']):
            if current_block and in_item_block:
                # Process the completed block
                item = _parse_blache_item_block(current_block, invoice_data)
                if item:
                    items.append(item)
                current_block = []
            
            current_block.append(line)
            in_item_block = True
        
        # Continue collecting lines for the current item block
        elif in_item_block:
            # Check if this is the start of a new item block or the end of current block
            if (re.match(r'^\d+\s+[A-Z0-9\-]', line) or 
                re.search(r'Total / net|Steuerfreie Ausfuhrlieferung', line) or
                (i + 1 < len(lines) and re.match(r'^\d+\s+[A-Z0-9\-]', lines[i + 1].strip()))):
                # Process the completed block
                item = _parse_blache_item_block(current_block, invoice_data)
                if item:
                    items.append(item)
                current_block = []
                in_item_block = False
                
                # If this is a new item block, start collecting it
                if re.match(r'^\d+\s+[A-Z0-9\-]', line):
                    current_block.append(line)
                    in_item_block = True
            else:
                current_block.append(line)
    
    # Process the last block if exists
    if current_block and in_item_block:
        item = _parse_blache_item_block(current_block, invoice_data)
        if item:
            items.append(item)
    
    return items

def _parse_blache_item_block(block: List[str], invoice_data: Dict) -> Optional[Dict]:
    """Parse a complete item block from Blache invoice"""
    if not block:
        return None
    
    # Join the block for easier parsing
    block_text = ' '.join(block)
    
    # Extract order information from the block
    order_match = re.search(r'Your Order No\.\s*(\d+)', block_text, re.IGNORECASE)
    order_number = order_match.group(1) if order_match else ""
    
    po_match = re.search(r'PO-No\.\s*([A-Z0-9/ ]+)', block_text, re.IGNORECASE)
    po_number = po_match.group(1).strip() if po_match else ""
    
    delivery_match = re.search(r'delivered with Delivery Note no\.\s*([A-Z0-9/ ]+)\s*Date:\s*(\d{2}\.\d{2}\.\d{4})', block_text, re.IGNORECASE)
    delivery_note = delivery_match.group(1).strip() if delivery_match else ""
    delivery_date = delivery_match.group(2) if delivery_match else ""
    
    # Extract the main item line (first line of the block)
    first_line = block[0]
    
    # Pattern for the main item line: position + article number + description + quantity + price + total
    item_pattern = r'^(\d+)\s+([A-Z0-9\-]+)\s+(.+?)\s+(\d+)\s+pcs\.\s+([\d,]+)\s+([\d,]+)$'
    item_match = re.search(item_pattern, first_line)
    
    if not item_match:
        # Try alternative pattern if first pattern doesn't match
        alt_pattern = r'^(\d+)\s+([A-Z0-9\-]+)\s+(.+?)\s+(\d+)\s+pcs\.\s+([\d,]+)'
        item_match = re.search(alt_pattern, first_line)
    
    if item_match:
        position = item_match.group(1)
        article_number = item_match.group(2)
        description = item_match.group(3).strip()
        quantity = item_match.group(4)
        unit_price = item_match.group(5).replace(',', '.')
        total_price = item_match.group(6).replace(',', '.') if len(item_match.groups()) >= 6 else ""
        
        # Add additional description from subsequent lines
        if len(block) > 1:
            additional_desc = []
            for line in block[1:]:
                # Skip lines that contain order/delivery information
                if not re.search(r'Your Order|PO-No\.|delivered with|MDL no\.|\d+ x \d+', line):
                    additional_desc.append(line.strip())
            
            if additional_desc:
                description += ' ' + ' '.join(additional_desc)
        
        # Clean up description
        description = re.sub(r'\s+', ' ', description).strip()
        
        return {
            'invoice_number': invoice_data.get('invoice_number', ''),
            'invoice_date': invoice_data.get('invoice_date', ''),
            'customer_number': invoice_data.get('customer_number', ''),
            'vat_number': invoice_data.get('vat_number', ''),
            'order_number': order_number,
            'po_number': po_number,
            'delivery_note': delivery_note,
            'delivery_date': delivery_date,
            'lot_number': '',  # LOT number is missing
            'position': position,
            'article_number': article_number,
            'description': description,
            'quantity': quantity,
            'unit_price': unit_price,
            'total_price': total_price
        }
    
    return None

#carl_teufel
def extract_carl_teufel_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Carl Teufel invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Extract invoice information
        invoice_data = _extract_carl_teufel_invoice_info(full_text)
        
        # Extract items
        items = _extract_carl_teufel_items(full_text, invoice_data)
        extracted_data.extend(items)
    
    return extracted_data

def _extract_carl_teufel_invoice_info(full_text: str) -> Dict[str, str]:
    """Extract invoice information from Carl Teufel invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'page_info': ''
    }
    
    # Extract invoice number - handle space in number like "41 402"
    inv_match = re.search(r'INVOICE NO\.\s*([\d\s]+)\s*\d+', full_text, re.IGNORECASE)
    if inv_match:
        invoice_data['invoice_number'] = inv_match.group(1).replace(' ', '')
    
    # Extract invoice date
    date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
    if date_match:
        invoice_data['invoice_date'] = date_match.group(1)
    
    # Extract page info (like "JS Page 1")
    page_match = re.search(r'([A-Z]{1,2})\s+Page\s+(\d+)', full_text)
    if page_match:
        invoice_data['page_info'] = f"{page_match.group(1)} Page {page_match.group(2)}"
    
    return invoice_data

def _extract_carl_teufel_items(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract items from Carl Teufel invoice text"""
    items = []
    
    # Split into lines for processing
    lines = full_text.split('\n')
    
    current_order_no = ""
    current_art_no = ""
    current_item = None
    collecting_description = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Extract order number and date
        order_match = re.search(r'Your order no\.\s*(\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if order_match:
            current_order_no = order_match.group(1)
        
        # Extract article number
        art_match = re.search(r'Your art\.-no\.:\s*([A-Z0-9\-]+)', line, re.IGNORECASE)
        if art_match:
            current_art_no = art_match.group(1)
        
        # Look for item lines (product code + quantity + description + price + total)
        # Pattern: product_code + quantity + description + price + total
        item_match = re.match(r'^([A-Z0-9\-]+)\s+(\d+)\s+(.+?)\s+([\d,]+)\s+([\d,]+)$', line)
        if item_match:
            if current_item:
                items.append(current_item)
            
            product_code = item_match.group(1)
            quantity = item_match.group(2)
            description = item_match.group(3).strip()
            unit_price = item_match.group(4).replace(',', '.')
            total_price = item_match.group(5).replace(',', '.')
            
            current_item = {
                'invoice_number': invoice_data.get('invoice_number', ''),
                'invoice_date': invoice_data.get('invoice_date', ''),
                'order_number': current_order_no,
                'article_number': current_art_no,
                'product_code': product_code,
                'description': description,
                'quantity': quantity,
                'unit_price': unit_price,
                'total_price': total_price,
                'lot_number': '',
                'mdl_number': '',
                'code': ''
            }
            collecting_description = False
        
        # Extract LOT number
        lot_match = re.search(r'LOT\s+([A-Z0-9\-]+)', line, re.IGNORECASE)
        if lot_match and current_item:
            current_item['lot_number'] = lot_match.group(1)
        
        # Extract MDL number
        mdl_match = re.search(r'MDL-No\.\s*([A-Z0-9]+)', line, re.IGNORECASE)
        if mdl_match and current_item:
            current_item['mdl_number'] = mdl_match.group(1)
        
        # Extract CODE
        code_match = re.search(r'CODE?\s*([A-Z0-9]+)', line, re.IGNORECASE)
        if code_match and current_item:
            current_item['code'] = code_match.group(1)
        
        # Continue description for multi-line items if the next line doesn't contain metadata
        elif (current_item and not collecting_description and 
              not re.match(r'^(Your order|Your art\.-no|LOT|MDL-No|CODE|Total)', line) and
              len(line) > 3 and not re.search(r'\d+,\d+', line)):
            current_item['description'] += ' ' + line
    
    # Add the last item if exists
    if current_item:
        items.append(current_item)
    
    return items
# Alternative block-based approach for better accuracy
def _extract_carl_teufel_item_blocks(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract complete item blocks from Carl Teufel invoice"""
    items = []
    lines = full_text.split('\n')
    
    current_block = []
    in_item_block = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Look for start of item block (order number line)
        if re.search(r'Your order no\.\s*\d+', line, re.IGNORECASE):
            if current_block and in_item_block:
                item = _parse_carl_teufel_block(current_block, invoice_data)
                if item:
                    items.append(item)
                current_block = []
            
            current_block.append(line)
            in_item_block = True
        
        # Continue collecting lines for current block
        elif in_item_block:
            # Check if this is the start of a new block or end of current block
            if (re.search(r'Your order no\.\s*\d+', line, re.IGNORECASE) or
                re.search(r'Total net|Total/EUR', line) or
                (i + 1 < len(lines) and re.search(r'Your order no\.\s*\d+', lines[i + 1].strip(), re.IGNORECASE))):
                
                # Process completed block
                item = _parse_carl_teufel_block(current_block, invoice_data)
                if item:
                    items.append(item)
                current_block = []
                
                # If this is a new block, start collecting it
                if re.search(r'Your order no\.\s*\d+', line, re.IGNORECASE):
                    current_block.append(line)
            else:
                current_block.append(line)
    
    # Process the last block
    if current_block:
        item = _parse_carl_teufel_block(current_block, invoice_data)
        if item:
            items.append(item)
    
    return items

def _parse_carl_teufel_block(block: List[str], invoice_data: Dict) -> Optional[Dict]:
    """Parse a complete item block from Carl Teufel invoice"""
    if not block:
        return None
    
    block_text = ' '.join(block)
    
    # Extract order information
    order_match = re.search(r'Your order no\.\s*(\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', block_text, re.IGNORECASE)
    order_number = order_match.group(1) if order_match else ""
    order_date = order_match.group(2) if order_match else ""
    
    # Extract article number
    art_match = re.search(r'Your art\.-no\.:\s*([A-Z0-9\-]+)', block_text, re.IGNORECASE)
    article_number = art_match.group(1) if art_match else ""
    
    # Extract item line (product code + quantity + description + price + total)
    item_match = re.search(r'([A-Z0-9\-]+)\s+(\d+)\s+(.+?)\s+([\d,]+)\s+([\d,]+)', block_text)
    if item_match:
        product_code = item_match.group(1)
        quantity = item_match.group(2)
        description = item_match.group(3).strip()
        unit_price = item_match.group(4).replace(',', '.')
        total_price = item_match.group(5).replace(',', '.')
        
        # Extract LOT, MDL, and CODE
        lot_match = re.search(r'LOT\s+([A-Z0-9\-]+)', block_text, re.IGNORECASE)
        lot_number = lot_match.group(1) if lot_match else ""
        
        mdl_match = re.search(r'MDL-No\.\s*([A-Z0-9]+)', block_text, re.IGNORECASE)
        mdl_number = mdl_match.group(1) if mdl_match else ""
        
        code_match = re.search(r'CODE?\s*([A-Z0-9]+)', block_text, re.IGNORECASE)
        code = code_match.group(1) if code_match else ""
        
        # Clean up description
        description = re.sub(r'\s+', ' ', description).strip()
        
        return {
            'invoice_number': invoice_data.get('invoice_number', ''),
            'invoice_date': invoice_data.get('invoice_date', ''),
            'order_number': order_number,
            'order_date': order_date,
            'article_number': article_number,
            'product_code': product_code,
            'description': description,
            'quantity': quantity,
            'unit_price': unit_price,
            'total_price': total_price,
            'lot_number': lot_number,
            'mdl_number': mdl_number,
            'code': code
        }
    
    return None

#chirmed
def extract_chirmed_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Chirmed invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Extract invoice information
        invoice_data = _extract_chirmed_invoice_info(full_text)
        
        # Extract items
        items = _extract_chirmed_items(full_text, invoice_data)
        extracted_data.extend(items)
    
    return extracted_data

def _extract_chirmed_invoice_info(full_text: str) -> Dict[str, str]:
    """Extract invoice information from Chirmed invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_number': '',
        'due_date': '',
        'currency': ''
    }
    
    # Extract invoice number (format: "No. DEX/26/2024")
    inv_match = re.search(r'No\.\s*([A-Z]+/\d+/\d+)', full_text, re.IGNORECASE)
    if inv_match:
        invoice_data['invoice_number'] = inv_match.group(1)
    
    # Extract invoice date (format: "2024-03-27")
    date_match = re.search(r'Invoice\s+(\d{4}-\d{2}-\d{2})', full_text, re.IGNORECASE)
    if date_match:
        invoice_data['invoice_date'] = date_match.group(1)
    
    # Extract order number
    order_match = re.search(r'Order no\.\s*(\d+)', full_text, re.IGNORECASE)
    if order_match:
        invoice_data['order_number'] = order_match.group(1)
    
    # Extract due date
    due_match = re.search(r'Date of due:\s*(\d{4}-\d{2}-\d{2})', full_text, re.IGNORECASE)
    if due_match:
        invoice_data['due_date'] = due_match.group(1)
    
    # Extract currency
    currency_match = re.search(r'Currency:\s*([A-Z]+)', full_text, re.IGNORECASE)
    if currency_match:
        invoice_data['currency'] = currency_match.group(1)
    
    return invoice_data

def _extract_chirmed_items(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract items from Chirmed invoice text"""
    items = []
    
    # Find the item table section
    lines = full_text.split('\n')
    in_item_section = False
    current_item_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Look for the start of item section (after column headers)
        if re.search(r'No\.\s+Description\s+Code\s+Quantity\s+Unit', line, re.IGNORECASE):
            in_item_section = True
            continue
        
        # Look for the end of item section
        if in_item_section and (re.search(r'TOTAL\s+[\d,]+', line) or re.search(r'Contain\s+[\d,]+', line)):
            in_item_section = False
            # Process collected item lines
            if current_item_lines:
                item = _parse_chirmed_item_line(' '.join(current_item_lines), invoice_data)
                if item:
                    items.append(item)
                current_item_lines = []
            continue
        
        # Collect item lines
        if in_item_section and line:
            # Check if this is a new item line (starts with number)
            if re.match(r'^\d+\s+', line) and current_item_lines:
                # Process previous item
                item = _parse_chirmed_item_line(' '.join(current_item_lines), invoice_data)
                if item:
                    items.append(item)
                current_item_lines = [line]
            else:
                current_item_lines.append(line)
    
    # Process the last item if any
    if current_item_lines:
        item = _parse_chirmed_item_line(' '.join(current_item_lines), invoice_data)
        if item:
            items.append(item)
    
    return items

def _parse_chirmed_item_line(line_text: str, invoice_data: Dict) -> Optional[Dict]:
    """Parse a single item line from Chirmed invoice with flexible pattern matching"""
    # Flexible pattern that handles both "szt" formats and optional code
    # Pattern: position + description + (optional code) + quantity + unit_price + total_price
    
    # Try pattern with code first
    patterns = [
        # With code, space in "szt": "3 szt"
        r'^(\d+)\s+(.+?)\s+([A-Z0-9\-/]+(?:\s+[A-Z0-9\-/]+)*?)\s+(\d+)\s+szt\s+([\d,]+)\s+([\d,]+)',
        # With code, no space in "szt": "6szt"  
        r'^(\d+)\s+(.+?)\s+([A-Z0-9\-/]+(?:\s+[A-Z0-9\-/]+)*?)\s+(\d+)szt\s+([\d,]+)\s+([\d,]+)',
        # Without code, space in "szt": "3 szt"
        r'^(\d+)\s+(.+?)\s+(\d+)\s+szt\s+([\d,]+)\s+([\d,]+)',
        # Without code, no space in "szt": "6szt"
        r'^(\d+)\s+(.+?)\s+(\d+)szt\s+([\d,]+)\s+([\d,]+)'
    ]
    
    for pattern in patterns:
        item_match = re.search(pattern, line_text)
        if item_match:
            position = item_match.group(1)
            
            if len(item_match.groups()) == 6:
                # Pattern with code
                description = item_match.group(2)
                product_code = item_match.group(3)
                quantity = item_match.group(4)
                unit_price = item_match.group(5).replace(',', '.')
                total_price = item_match.group(6).replace(',', '.')
            else:
                # Pattern without code
                description = item_match.group(2)
                product_code = ""
                quantity = item_match.group(3)
                unit_price = item_match.group(4).replace(',', '.')
                total_price = item_match.group(5).replace(',', '.')
            
            # Clean up description
            description = re.sub(r'\s+', ' ', description).strip()
            
            return {
                'invoice_number': invoice_data.get('invoice_number', ''),
                'invoice_date': invoice_data.get('invoice_date', ''),
                'order_number': invoice_data.get('order_number', ''),
                'due_date': invoice_data.get('due_date', ''),
                'currency': invoice_data.get('currency', ''),
                'position': position,
                'article_number': '',
                'lot_number': '',
                'product_code': product_code,
                'description': description,
                'quantity': quantity,
                'unit_price': unit_price,
                'total_price': total_price
            }
    
    return None

#cm_instrumente
def extract_cm_instrumente_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from CM Instrumente invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Extract invoice information
        invoice_data = _extract_cm_instrumente_invoice_info(full_text)
        
        # Extract items
        items = _extract_cm_instrumente_items(full_text, invoice_data)
        extracted_data.extend(items)
    
    return extracted_data

def _extract_cm_instrumente_invoice_info(full_text: str) -> Dict[str, str]:
    """Extract invoice information from CM Instrumente invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': ''
    }
    
    # Extract invoice number
    inv_match = re.search(r'INVOICE NO\.\s*:\s*(\d+)', full_text, re.IGNORECASE)
    if inv_match:
        invoice_data['invoice_number'] = inv_match.group(1)
    
    # Extract invoice date
    date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
    if date_match:
        invoice_data['invoice_date'] = date_match.group(1)
    
    # Extract customer number
    cust_match = re.search(r'Cust\.-No\.\s*:\s*(\d+)', full_text, re.IGNORECASE)
    if cust_match:
        invoice_data['customer_number'] = cust_match.group(1)
    
    return invoice_data

def _extract_cm_instrumente_items(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract items from CM Instrumente invoice text"""
    items = []
    
    # Split into lines for processing
    lines = full_text.split('\n')
    
    current_order_no = ""
    current_art_no = ""
    current_mdl_no = ""
    current_item = None
    current_block = []
    in_item_block = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Extract order number
        order_match = re.search(r'your order no\.\s*(\d+)', line, re.IGNORECASE)
        if order_match:
            current_order_no = order_match.group(1)
        
        # Extract article number
        art_match = re.search(r'your art\.-no\.:\s*([A-Z0-9\-]+)', line, re.IGNORECASE)
        if art_match:
            current_art_no = art_match.group(1)
        
        # Extract MDL registration number
        mdl_match = re.search(r'MDL Reg\. No\.:\s*([A-Z0-9\s]+)', line, re.IGNORECASE)
        if mdl_match:
            current_mdl_no = mdl_match.group(1).strip()
        
        # Look for item lines (POS + ARTICLE + description + qty + each + price)
        item_match = re.match(r'^(\d+)\s+([A-Z0-9\-]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', line)
        if item_match:
            if current_item:
                items.append(current_item)
            
            position = item_match.group(1)
            article_code = item_match.group(2)
            description = item_match.group(3).strip()
            quantity = item_match.group(4)
            unit_price = item_match.group(5).replace(',', '.')
            total_price = item_match.group(6).replace(',', '.')
            
            current_item = {
                'invoice_number': invoice_data.get('invoice_number', ''),
                'invoice_date': invoice_data.get('invoice_date', ''),
                'customer_number': invoice_data.get('customer_number', ''),
                'order_number': current_order_no,
                'article_number': current_art_no,
                'mdl_number': current_mdl_no,
                'lot_number': '',  # Missing in this format
                'position': position,
                'article_code': article_code,
                'description': description,
                'quantity': quantity,
                'unit_price': unit_price,
                'total_price': total_price
            }
            
            # Reset for next item
            current_art_no = ""
            current_mdl_no = ""
        
        # Continue description for multi-line items
        elif current_item and not re.match(r'^(your order|your art\.-no|MDL Reg\. No|carry-over|total)', line, re.IGNORECASE):
            # Check if this line contains additional description (not metadata)
            if not re.search(r'\d+\s+[\d,]+$', line) and len(line) > 3:
                current_item['description'] += ' ' + line
    
    # Add the last item if exists
    if current_item:
        items.append(current_item)
    
    return items

# Alternative block-based approach for better accuracy
def _extract_cm_instrumente_item_blocks(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract complete item blocks from CM Instrumente invoice"""
    items = []
    lines = full_text.split('\n')
    
    current_block = []
    in_item_block = False
    current_order_no = ""
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Look for start of item block (order number line)
        if re.search(r'your order no\.\s*\d+', line, re.IGNORECASE):
            if current_block and in_item_block:
                item = _parse_cm_instrumente_block(current_block, invoice_data, current_order_no)
                if item:
                    items.append(item)
                current_block = []
            
            # Extract order number from this line
            order_match = re.search(r'your order no\.\s*(\d+)', line, re.IGNORECASE)
            if order_match:
                current_order_no = order_match.group(1)
            
            current_block.append(line)
            in_item_block = True
        
        # Continue collecting lines for current block
        elif in_item_block:
            # Check if this is the start of a new block or end of current block
            if (re.search(r'your order no\.\s*\d+', line, re.IGNORECASE) or
                re.search(r'carry-over|total net', line) or
                (i + 1 < len(lines) and re.search(r'your order no\.\s*\d+', lines[i + 1].strip(), re.IGNORECASE))):
                
                # Process completed block
                item = _parse_cm_instrumente_block(current_block, invoice_data, current_order_no)
                if item:
                    items.append(item)
                current_block = []
                
                # If this is a new block, start collecting it
                if re.search(r'your order no\.\s*\d+', line, re.IGNORECASE):
                    order_match = re.search(r'your order no\.\s*(\d+)', line, re.IGNORECASE)
                    if order_match:
                        current_order_no = order_match.group(1)
                    current_block.append(line)
            else:
                current_block.append(line)
    
    # Process the last block
    if current_block:
        item = _parse_cm_instrumente_block(current_block, invoice_data, current_order_no)
        if item:
            items.append(item)
    
    return items

def _parse_cm_instrumente_block(block: List[str], invoice_data: Dict, order_number: str) -> Optional[Dict]:
    """Parse a complete item block from CM Instrumente invoice"""
    if not block:
        return None
    
    block_text = ' '.join(block)
    
    # Extract article number
    art_match = re.search(r'your art\.-no\.:\s*([A-Z0-9\-]+)', block_text, re.IGNORECASE)
    article_number = art_match.group(1) if art_match else ""
    
    # Extract MDL registration number
    mdl_match = re.search(r'MDL Reg\. No\.:\s*([A-Z0-9\s]+)', block_text, re.IGNORECASE)
    mdl_number = mdl_match.group(1).strip() if mdl_match else ""
    
    # Extract item line (POS + ARTICLE + description + qty + each + price)
    item_match = re.search(r'(\d+)\s+([A-Z0-9\-]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)', block_text)
    if item_match:
        position = item_match.group(1)
        article_code = item_match.group(2)
        description = item_match.group(3).strip()
        quantity = item_match.group(4)
        unit_price = item_match.group(5).replace(',', '.')
        total_price = item_match.group(6).replace(',', '.')
        
        # Clean up description
        description = re.sub(r'\s+', ' ', description).strip()
        
        return {
            'invoice_number': invoice_data.get('invoice_number', ''),
            'invoice_date': invoice_data.get('invoice_date', ''),
            'customer_number': invoice_data.get('customer_number', ''),
            'order_number': order_number,
            'article_number': article_number,
            'mdl_number': mdl_number,
            'lot_number': '',  # Missing
            'position': position,
            'article_code': article_code,
            'description': description,
            'quantity': quantity,
            'unit_price': unit_price,
            'total_price': total_price
        }
    
    return None


#CMF
def extract_cmf_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from CMF Medicon Surgical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Extract invoice information
        invoice_data = _extract_cmf_invoice_info(full_text)
        
        # Extract items
        items = _extract_cmf_items(full_text, invoice_data)
        extracted_data.extend(items)
    
    return extracted_data

def _extract_cmf_invoice_info(full_text: str) -> Dict[str, str]:
    """Extract invoice information from CMF invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'po_number': ''
    }
    
    # Extract invoice number and date - they are on the same line after "Date Invoice #"
    # Pattern: "Date Invoice #\n2/26/2024 27319"
    inv_match = re.search(r'Date Invoice #\s*(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)', full_text)
    if inv_match:
        invoice_data['invoice_date'] = inv_match.group(1)
        invoice_data['invoice_number'] = inv_match.group(2)
    else:
        # Try alternative pattern for the second file format
        inv_match = re.search(r'Date Invoice #\s*\d{3}-\d{3}-\d{4}\s*(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)', full_text)
        if inv_match:
            invoice_data['invoice_date'] = inv_match.group(1)
            invoice_data['invoice_number'] = inv_match.group(2)
    
    # Extract PO number - it's on the line after "P.O. No." in the terms section
    # Look for the line that contains the PO number (after the header line)
    po_match = re.search(r'P\.O\. No\.\s*\n.*?(\d{7})', full_text, re.IGNORECASE)
    if not po_match:
        # Try another pattern - look for the numbers after the sales order number
        po_match = re.search(r'FB - Sales Order #\s*[\w\-]+\s+(\d{7})', full_text, re.IGNORECASE)
    if not po_match:
        # Try looking for the PO number in the terms line
        po_match = re.search(r'Net \d+\s+[\d/]+\s+[\w\-]+\s+(\d{7})', full_text)
    
    if po_match:
        invoice_data['po_number'] = po_match.group(1)
    
    return invoice_data

def _extract_cmf_items(full_text: str, invoice_data: Dict) -> List[Dict]:
    """Extract items from CMF invoice text - ignore TKG records"""
    items = []
    
    # Split into lines for processing
    lines = full_text.split('\n')
    
    # Find the item section (after "Description Qty Rate Amount")
    in_item_section = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Look for the start of item section
        if re.search(r'Description\s+Qty\s+Rate\s+Amount', line, re.IGNORECASE):
            in_item_section = True
            continue
        
        # Look for the end of item section
        if in_item_section and (re.search(r'Subtotal|Sales Tax|Total|Beginning September', line, re.IGNORECASE)):
            in_item_section = False
            continue
        
        # Process item lines
        if in_item_section and line:
            # Skip TKG records (shipping/tracking information)
            if re.match(r'^TKG', line, re.IGNORECASE):
                continue
                
            # Skip processing/handling fees
            if re.search(r'P & H|Processing and Handling', line, re.IGNORECASE):
                continue
                
            # Look for product items with quantity and price
            # Use a more specific pattern to avoid false positives
            if re.search(r'\d+\s+[\d\.]+\s+[\d\.]+$', line) and not re.search(r'^[A-Z]{3}:', line):
                item = _parse_cmf_item_line(line, invoice_data)
                if item:
                    items.append(item)
    
    return items

def _parse_cmf_item_line(line_text: str, invoice_data: Dict) -> Optional[Dict]:
    """Parse a single item line from CMF invoice"""
    # Pattern for CMF product items: Description + Qty + Rate + Amount
    # Handle items with and without lot numbers
    
    # Pattern for items with lot number
    pattern_with_lot = r'(.+?)\s+Lot#:\s*([A-Z0-9\-]+)\s+(\d+)\s+([\d\.]+)\s+([\d\.]+)$'
    match = re.search(pattern_with_lot, line_text)
    
    if match:
        description = match.group(1).strip()
        lot_number = match.group(2)
        quantity = match.group(3)
        unit_price = match.group(4)
        total_price = match.group(5)
    else:
        # Pattern for items without lot number
        pattern_without_lot = r'(.+?)\s+(\d+)\s+([\d\.]+)\s+([\d\.]+)$'
        match = re.search(pattern_without_lot, line_text)
        if match:
            description = match.group(1).strip()
            lot_number = ""
            quantity = match.group(2)
            unit_price = match.group(3)
            total_price = match.group(4)
        else:
            return None
    
    # Clean up description
    description = re.sub(r'\s+', ' ', description).strip()
    
    # Ensure all invoice data is properly included
    return {
        'invoice_number': invoice_data.get('invoice_number', ''),
        'invoice_date': invoice_data.get('invoice_date', ''),
        'po_number': invoice_data.get('po_number', ''),
        'description': description,
        'quantity': quantity,
        'unit_price': unit_price,
        'total_price': total_price,
        'lot_number': lot_number
    }


#Dannoritzer
def extract_dannoritzer_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Dannoritzer Medizintechnik invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_dannoritzer_invoice_info(lines)
            
            # Find item blocks and their associated order information
            item_blocks = []
            current_block = []
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            in_item_block = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for order information that might change within the invoice
                if re.search(r'Your order no\.|PO#', line_clean, re.IGNORECASE):
                    # Extract order info from this line - CAPTURE ONLY THE NUMBER AFTER PO#
                    # Pattern: "Your order no. PO# 07102020 - 07.10.2020" or "Your order no. PO# 02-2500097 - 07.10.2020"
                    order_match = re.search(r'Your order no\.?\s*PO#\s*([A-Z0-9\s\-]+?)\s+-\s+(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1).strip()  # Only the number part
                        current_order_info['order_date'] = order_match.group(2)
                    else:
                        # Alternative pattern for orders without PO# prefix
                        order_match2 = re.search(r'Your order no\.?\s*([A-Z0-9\s\-]+?)\s+-\s+(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                        if order_match2:
                            current_order_info['order_no'] = order_match2.group(1).strip()
                            current_order_info['order_date'] = order_match2.group(2)
                        else:
                            # Fallback: extract just the order number before any dash
                            order_num_match = re.search(r'Your order no\.?\s*PO#\s*([A-Z0-9\s\-]+?|[A-Z0-9\s\-]+?)(?:\s+-\s+|$)', line_clean, re.IGNORECASE)
                            if order_num_match:
                                current_order_info['order_no'] = order_num_match.group(1).strip()
                            
                            # Check for date separately
                            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', line_clean)
                            if date_match:
                                current_order_info['order_date'] = date_match.group(1)
                            elif i + 1 < len(lines):
                                next_line = lines[i + 1].strip()
                                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', next_line)
                                if date_match:
                                    current_order_info['order_date'] = date_match.group(1)
                
                # Look for lines that start with item patterns
                if (re.match(r'^\d+\s+REP-', line_clean) or 
                    re.match(r'^\d+\s+[A-Z]', line_clean) or
                    re.match(r'^REP-', line_clean)):
                    
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+REP-', line_clean) or
                        re.match(r'^\d+\s+[A-Z]', line_clean) or
                        re.match(r'^REP-', line_clean) or
                        re.search(r'Total net|Package|Total/EUR|Payment|Terms of delivery', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean] if not re.search(r'Total net|Package|Total/EUR', line_clean, re.IGNORECASE) else []
                        in_item_block = bool(re.match(r'^\d+\s+REP-', line_clean) or re.match(r'^\d+\s+[A-Z]', line_clean) or re.match(r'^REP-', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy()))
            
            # Process each item block with its associated order info
            for block, order_info in item_blocks:
                item_data = _parse_dannoritzer_item_block(block, invoice_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_dannoritzer_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Dannoritzer invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    # Join lines for better pattern matching
    full_text = ' '.join(lines)
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note[#\s]*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
    
    # Extract order information with updated patterns (capture only the number after PO#)
    # Look for order information in the full text
    order_match = re.search(r'Your order no\.?\s*PO#\s*([A-Z0-9\s\-]+?)\s+-\s+(\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
    if order_match and not invoice_data['order_no']:
        invoice_data['order_no'] = order_match.group(1).strip()  # Only the number part
        invoice_data['order_date'] = order_match.group(2)
    
    # Alternative pattern for order extraction (without PO# but with dash)
    if not invoice_data['order_no']:
        order_match2 = re.search(r'Your order no\.?\s*([A-Z0-9\s\-]+?)\s+-\s+(\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
        if order_match2:
            invoice_data['order_no'] = order_match2.group(1).strip()
            invoice_data['order_date'] = order_match2.group(2)
    
    # If still not found, try line-by-line extraction for complex cases
    if not invoice_data['order_no']:
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Look for order number patterns with specific format
            if re.search(r'Your order no\.', line_clean, re.IGNORECASE):
                # Specific pattern for "Your order no. PO# 07102020 - 07.10.2020"
                order_match = re.search(r'Your order no\.?\s*PO#\s*([A-Z0-9\s\-]+?)\s+-\s+(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    invoice_data['order_no'] = order_match.group(1).strip()
                    invoice_data['order_date'] = order_match.group(2)
                    break
                
                # Alternative pattern without PO# but with dash
                order_match2 = re.search(r'Your order no\.?\s*([A-Z0-9\s\-]+?)\s+-\s+(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match2:
                    invoice_data['order_no'] = order_match2.group(1).strip()
                    invoice_data['order_date'] = order_match2.group(2)
                    break
                
                # If date is not on the same line, check next line
                if not invoice_data['order_date'] and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', next_line)
                    if date_match:
                        invoice_data['order_date'] = date_match.group(1)
                
                # Extract order number from this line (more specific pattern)
                order_num_match = re.search(r'Your order no\.?\s*PO#\s*([A-Z0-9\s\-]+?|[A-Z0-9\s\-]+?)(?:\s+-\s+|$)', line_clean, re.IGNORECASE)
                if order_num_match and not invoice_data['order_no']:
                    invoice_data['order_no'] = order_num_match.group(1).strip()
                    break
    
    return invoice_data

def _parse_dannoritzer_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Dannoritzer invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'position': '',
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        item_data['position'] = pos_match.group(1)
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern: "1 REP-N6933-92Repair Novo Surgical N6933-92ECC 1 pcs. 30,00 30,00"
    item_match = re.search(r'^\d+\s+([A-Z0-9\-]+)(.+?)\s+(\d+)\s+pcs?\.\s*([\d,]+)\s*([\d,]+)$', first_line)
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        item_data['total_price'] = item_match.group(5).replace(',', '.')
    
    # Alternative pattern for items without "pcs."
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+([A-Z0-9\-]+)(.+?)\s+(\d+)\s+([\d,]+)\s*([\d,]+)$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
            item_data['total_price'] = alt_match.group(5).replace(',', '.')
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata or prices
            if not re.search(r'[\d,]+$', line) and not re.match(r'^\d', line):
                additional_desc.append(line.strip())
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract quantity and price from alternative patterns if still missing
    if not item_data['quantity']:
        qty_match = re.search(r'\s+(\d+)\s+pcs?\.\s*[\d,]+\s*[\d,]+$', first_line)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    if not item_data['unit_price']:
        price_match = re.search(r'\s+([\d,]+)\s+([\d,]+)$', first_line)
        if price_match:
            item_data['unit_price'] = price_match.group(1).replace(',', '.')
            item_data['total_price'] = price_match.group(2).replace(',', '.')
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Dausch
def extract_dausch_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Dausch Medizintechnik invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_dausch_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            in_item_block = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for order information that might change within the invoice
                if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                    # Extract order info from this line
                    order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1)
                        current_order_info['order_date'] = order_match.group(2)
                
                # Look for lines that start with item patterns (position numbers followed by product codes)
                if (re.match(r'^\d+\s+[A-Z0-9]+\d*[A-Z]*\/', line_clean) or  # e.g., 10 75D876/6/28
                    re.match(r'^\d+\s+[A-Z0-9]+\d+[A-Z]*', line_clean) or    # e.g., 10 70D726/23
                    re.match(r'^\d+\s+[A-Z]+\d+', line_clean)):              # e.g., 10 ABC123
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+[A-Z0-9]+\d*[A-Z]*\/', line_clean) or
                        re.match(r'^\d+\s+[A-Z0-9]+\d+[A-Z]*', line_clean) or
                        re.match(r'^\d+\s+[A-Z]+\d+', line_clean) or
                        re.search(r'total net|package|total/EUR|payment|delivery', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean] if not re.search(r'total net|package|total/EUR', line_clean, re.IGNORECASE) else []
                        in_item_block = bool(re.match(r'^\d+\s+[A-Z0-9]+\d*[A-Z]*\/', line_clean) or 
                                           re.match(r'^\d+\s+[A-Z0-9]+\d+[A-Z]*', line_clean) or
                                           re.match(r'^\d+\s+[A-Z]+\d+', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy()))
            
            # Process each item block
            for block, order_info in item_blocks:
                item_data = _parse_dausch_item_block(block, invoice_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_dausch_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Dausch invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number - handle various formats including "INVOICEN O." issue
        inv_match = re.search(r'INVOICE\s*N?O\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Alternative pattern for the specific "INVOICEN O." format
        if not invoice_data['invoice_number']:
            inv_match_alt = re.search(r'INVOICEN\s*O\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
            if inv_match_alt:
                invoice_data['invoice_number'] = inv_match_alt.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_dausch_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Dausch invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'position': '',
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        item_data['position'] = pos_match.group(1)
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern for Dausch format: "10 75D876/6/28 Cup shaped Forceps 6mm 146,08 292,16"
    item_match = re.search(r'^\d+\s+([A-Z0-9\/]+)\s+(.+?)\s+(\d+[\.,]?\d*)\s+([\d,]+)\s+([\d,]+)$', first_line)
    if not item_match:
        # Alternative pattern: "10 70D726/23 KLEINSASSER Alligator Forceps 1 108,41 108,41"
        item_match = re.search(r'^\d+\s+([A-Z0-9\/]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3).replace(',', '.')
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        item_data['total_price'] = item_match.group(5).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+([A-Z0-9\/]+)\s+(.+?)\s+([\d,]+)\s+([\d,]+)$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            # Assume quantity is 1 if not specified
            item_data['quantity'] = '1'
            item_data['unit_price'] = alt_match.group(3).replace(',', '.')
            item_data['total_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        qty_match = re.search(r'\s+(\d+[\.,]?\d*)\s+[\d,]+\s+[\d,]+$', first_line)
        if qty_match:
            item_data['quantity'] = qty_match.group(1).replace(',', '.')
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '.')
            item_data['total_price'] = prices[-1].replace(',', '.')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot:\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Lot:|LST No\.|your art\.-no\.', line, re.IGNORECASE):
                additional_desc.append(line.strip())
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Denzel
def extract_denzel_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Denzel Medical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_denzel_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            in_item_block = False
            carry_over_detected = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for order information that might change within the invoice
                if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                    # Extract order info from this line
                    order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1)
                        current_order_info['order_date'] = order_match.group(2)
                
                # Look for lines that start with item patterns (position numbers followed by product codes)
                if re.match(r'^\d+\s+\d{2}\.\d{5}', line_clean):  # e.g., "1 01.71159"
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                    carry_over_detected = False
                elif in_item_block:
                    # Check for carry-over lines (they indicate continuation of items)
                    if re.search(r'carry-over', line_clean, re.IGNORECASE):
                        carry_over_detected = True
                        continue
                    
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+\d{2}\.\d{5}', line_clean) or
                        re.search(r'total net|package|freight|total/EUR|payment|delivery', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d{2}\.\d{5}', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+\d{2}\.\d{5}', line_clean))
                    else:
                        # Continue adding to current block if it's description or lot info
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy()))
            
            # Process each item block
            for block, order_info in item_blocks:
                item_data = _parse_denzel_item_block(block, invoice_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_denzel_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Denzel invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_denzel_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Denzel invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'position': '',
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        item_data['position'] = pos_match.group(1)
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern for Denzel format: "1 01.71159 Castroviejo Suturing Forceps, 1x2 teeth, 15 82,35 1235,25"
    item_match = re.search(r'^\d+\s+(\d{2}\.\d{5})\s+(.+?)\s+(\d+[\.,]?\d*)\s+([\d,]+)\s+([\d,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3).replace(',', '.')
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        item_data['total_price'] = item_match.group(5).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+(\d{2}\.\d{5})\s+(.+?)\s+([\d,]+)\s+([\d,]+)$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            # Assume quantity is 1 if not specified
            item_data['quantity'] = '1'
            item_data['unit_price'] = alt_match.group(3).replace(',', '.')
            item_data['total_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        qty_match = re.search(r'\s+(\d+[\.,]?\d*)\s+[\d,]+\s+[\d,]+$', first_line)
        if qty_match:
            item_data['quantity'] = qty_match.group(1).replace(',', '.')
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '.')
            item_data['total_price'] = prices[-1].replace(',', '.')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'lot number:\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'lot number:|MDL-NO\.|your art\.-no\.|carry-over', line, re.IGNORECASE):
                additional_desc.append(line.strip())
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#E.G. Voerling Scanned Copy, cant read

#Efinger
def extract_efinger_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Efinger Instruments invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_efinger_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            current_order_info = {'order_no': invoice_data['order_no']}
            in_item_block = False
            in_description_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the description section
                if re.search(r'Description\s+Quantity\s+Price\s+Total EUR', line_clean, re.IGNORECASE):
                    in_description_section = True
                    continue
                
                if not in_description_section:
                    continue
                
                # Look for order information that might change within the invoice
                if re.search(r'Based on your Purchase Order', line_clean, re.IGNORECASE):
                    order_match = re.search(r'Based on your Purchase Order\s+([^\s.,;]+)', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1)
                
                # Look for lines that start with item patterns (number followed by product name)
                if re.match(r'^\d+\s+[A-Z]', line_clean) and not re.search(r'Carry-over|Net Amount|Total EUR', line_clean, re.IGNORECASE):
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+[A-Z]', line_clean) or
                        re.search(r'Carry-over|Net Amount|Total EUR|Based on delivery|Thank you for', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+[A-Z]', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+[A-Z]', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy()))
            
            # Process each item block
            for block, order_info in item_blocks:
                item_data = _parse_efinger_item_block(block, invoice_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_efinger_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Efinger invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',
        'delivery_note': ''
    }
    
    # Look for the specific header line pattern
    header_found = False
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Look for the "A/R Invoice" line to identify the start of the header
        if re.search(r'A/R Invoice', line_clean, re.IGNORECASE):
            header_found = True
            continue
        
        # After finding "A/R Invoice", look for the next line with document details
        if header_found and re.search(r'Document No\.|Date|Page', line_clean, re.IGNORECASE):
            # The next line should contain the actual values
            if i + 1 < len(lines):
                values_line = lines[i + 1].strip()
                # Extract invoice number, date, and page from values line
                # Pattern: "102400312 4/17/2024 1 / 5"
                doc_match = re.search(r'^(\d+)\s+([\d/]+)\s+\d+\s*/\s*\d+$', values_line)
                if doc_match:
                    invoice_data['invoice_number'] = doc_match.group(1)
                    invoice_data['invoice_date'] = doc_match.group(2)
                    break
        
        # Extract delivery note information
        delivery_match = re.search(r'Based on delivery\s+(\d+)\s+from', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information from reference line
        order_match = re.search(r'Ref\.\s+.+?(\d{5,})', line_clean)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
    
    return invoice_data

def _parse_efinger_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Efinger invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': order_info['order_no'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern for Efinger format: "1 BELLUCCI MICRO SCISSORS 1.00 Stck 109.90 109.90"
    item_match = re.search(r'^\d+\s+([A-Z][^0-9]+?)\s+(\d+\.\d+)\s+Stck\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)', first_line, re.IGNORECASE)
    
    if item_match:
        item_data['description'] = item_match.group(1).strip()
        item_data['quantity'] = item_match.group(2).replace(',', '.')
        item_data['unit_price'] = item_match.group(3).replace(',', '.')
        item_data['total_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['description']:
        alt_match = re.search(r'^\d+\s+([A-Z].+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)', first_line, re.IGNORECASE)
        if alt_match:
            item_data['description'] = alt_match.group(1).strip()
            item_data['quantity'] = alt_match.group(2).replace(',', '.')
            item_data['unit_price'] = alt_match.group(3).replace(',', '.')
            item_data['total_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract item code from the block
    for line in block:
        code_match = re.search(r'Item Code:\s*([^\s]+)', line, re.IGNORECASE)
        if code_match:
            item_data['item_code'] = code_match.group(1)
            break
    
    # Extract batch number from the block
    for line in block:
        batch_match = re.search(r'Batch-Nr\.\s*([^\s]+)', line, re.IGNORECASE)
        if batch_match:
            item_data['lot'] = batch_match.group(1)
            break
    
    # Extract purchase order from the block if not already set
    if not item_data['order_no']:
        for line in block:
            po_match = re.search(r'Based on your Purchase Order\s+([^\s.,;]+)', line, re.IGNORECASE)
            if po_match:
                item_data['order_no'] = po_match.group(1)
                break
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Item Code:|Batch-Nr\.|Based on your Purchase Order|Product Information', line, re.IGNORECASE):
                clean_line = re.sub(r'^\d+\s+', '', line.strip())  # Remove position numbers from continuation lines
                if clean_line and not re.match(r'^\s*$', clean_line):
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        qty_match = re.search(r'\s+(\d+\.\d+)\s+Stck\s+', first_line, re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1).replace(',', '.')
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+\.\d+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '.')
            item_data['total_price'] = prices[-1].replace(',', '.')
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#ELMED
def extract_elmed_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from ELMED Incorporated invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_elmed_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_order_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the order section
                if re.search(r'Order\s+Ship\s+B/O\s+Item No\.\s+Description\s+Price Each\s+Amount', line_clean, re.IGNORECASE):
                    in_order_section = True
                    continue
                
                if not in_order_section:
                    continue
                
                # Look for lines that start with item patterns (numbers followed by item codes)
                if re.match(r'^\d+\s+\d+\s+\d*\s*[A-Z0-9]', line_clean) and not re.search(r'Subtotal|Total|Thank you', line_clean, re.IGNORECASE):
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+\d+\s+\d*\s*[A-Z0-9]', line_clean) or
                        re.search(r'Subtotal|Total|Thank you|UPS TRACKING', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d+\s+\d*\s*[A-Z0-9]', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+\d+\s+\d*\s*[A-Z0-9]', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_elmed_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_elmed_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from ELMED invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number and date from the header section
        # Pattern: "9/11/2024 2409221" or "2/26/2025 2502692"
        date_inv_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)', line_clean)
        if date_inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_date'] = date_inv_match.group(1)
            invoice_data['invoice_number'] = date_inv_match.group(2)
        
        # Extract PO number and date - look for the header line first
        if re.search(r'P\.O\. Number\s+P\.O\. Date\s+Terms', line_clean, re.IGNORECASE):
            # The next line should contain the actual values
            if i + 1 < len(lines):
                values_line = lines[i + 1].strip()
                # Pattern: "0016332 06/17/2024 Net 30 10/11/2024 SS 9/11/2024 UPS GROUND"
                po_match = re.search(r'^(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})', values_line)
                if po_match:
                    invoice_data['order_no'] = po_match.group(1)
                    invoice_data['order_date'] = po_match.group(2)
        
        # Extract tracking number as delivery note
        tracking_match = re.search(r'UPS TRACKING #:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if tracking_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = tracking_match.group(1)
    
    return invoice_data

def _parse_elmed_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from ELMED invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': invoice_data['order_no'],
        'order_date': invoice_data['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',  # ELMED doesn't seem to show lot numbers
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract order quantity, ship quantity, item code, description, prices
    # Pattern: "6 6 G1911-68 TITANIUM JEWELER BIPOLAR FORCEPS, 162.00 972.00"
    # or "1 1 9014-4054FDI 5MM, 45CM, CLEAR FLUSH, WAVE 646.75 646.75"
    item_match = re.search(r'^(\d+)\s+(\d+)\s+\d*\s*([A-Z0-9-]+)\s+(.+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line)
    
    if item_match:
        item_data['quantity'] = item_match.group(2)  # Use ship quantity
        item_data['item_code'] = item_match.group(3).strip()
        item_data['description'] = item_match.group(4).strip()
        item_data['unit_price'] = item_match.group(5).replace(',', '')
        item_data['total_price'] = item_match.group(6).replace(',', '')
    
    # Alternative pattern for handling items without B/O column
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d+)\s+(\d+)\s+([A-Z0-9-]+)\s+(.+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line)
        if alt_match:
            item_data['quantity'] = alt_match.group(2)
            item_data['item_code'] = alt_match.group(3).strip()
            item_data['description'] = alt_match.group(4).strip()
            item_data['unit_price'] = alt_match.group(5).replace(',', '')
            item_data['total_price'] = alt_match.group(6).replace(',', '')
    
    # Handle packing/handling items
    if not item_data['item_code'] and re.search(r'HNDL PACKING AND HANDLING', first_line, re.IGNORECASE):
        hndl_match = re.search(r'^(\d+)\s+(\d+)\s+(HNDL)\s+(PACKING AND HANDLING)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line, re.IGNORECASE)
        if hndl_match:
            item_data['quantity'] = hndl_match.group(2)
            item_data['item_code'] = hndl_match.group(3).strip()
            item_data['description'] = hndl_match.group(4).strip()
            item_data['unit_price'] = hndl_match.group(5).replace(',', '')
            item_data['total_price'] = hndl_match.group(6).replace(',', '')
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Skip lines that look like metadata or continuation of other items
            if not re.search(r'UDI#|Thank you|Subtotal|Total', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d+', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract UDI number if present (as lot number equivalent)
    for line in block:
        udi_match = re.search(r'UDI#:\s*([^\s]+)', line, re.IGNORECASE)
        if udi_match:
            item_data['lot'] = udi_match.group(1)
            break
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+\.\d+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '')
            item_data['total_price'] = prices[-1].replace(',', '')
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Ermis MedTech
def extract_ermis_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Ermis MedTech invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_ermis_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            current_ref_no = invoice_data.get('ref_no', '')
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\s+article\s+description\s+qty\.\s+each\s+price', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    # Extract Ref-No. from header area
                    ref_match = re.search(r'Ref-No\.:\s*([^\s]+)', line_clean, re.IGNORECASE)
                    if ref_match:
                        current_ref_no = ref_match.group(1)
                    continue
                
                # Look for order information that might change within the invoice
                if re.search(r'Your inq\. No\.', line_clean, re.IGNORECASE):
                    order_match = re.search(r'Your inq\. No\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1)
                        current_order_info['order_date'] = order_match.group(2)
                
                # Look for lines that start with item patterns (position numbers followed by content)
                if re.match(r'^\d+\s+[^0-9]', line_clean) and not re.search(r'total net|package|freight|Total/EUR', line_clean, re.IGNORECASE):
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy(), current_ref_no))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+[^0-9]', line_clean) or
                        re.search(r'total net|package|freight|Total/EUR|payment|delivery', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy(), current_ref_no))
                        current_block = [line_clean] if re.match(r'^\d+\s+[^0-9]', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+[^0-9]', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy(), current_ref_no))
            
            # Process each item block
            for block, order_info, ref_no in item_blocks:
                item_data = _parse_ermis_item_block(block, invoice_data, order_info, ref_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_ermis_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Ermis invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': '',
        'ref_no': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number (PROFORMA-INVOICE)
        inv_match = re.search(r'PROFORMA-INVOICE\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract order information
        order_match = re.search(r'Your inq\. No\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
        
        # Extract Ref-No.
        ref_match = re.search(r'Ref-No\.:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if ref_match and not invoice_data['ref_no']:
            invoice_data['ref_no'] = ref_match.group(1)
        
        # Extract delivery method
        delivery_match = re.search(r'Delivery\s*:\s*([^\n]+)', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1).strip()
    
    return invoice_data

def _parse_ermis_item_block(block: List[str], invoice_data: Dict, order_info: Dict, ref_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Ermis invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # Use Ref-No. as item code if available
    if ref_no:
        item_data['item_code'] = ref_no
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Remove position number from the beginning
    first_line = re.sub(r'^\d+\s+', '', first_line).strip()
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern: "ER290.100 3/4 Wire Basket 4pcs 92,93 371,72"
    item_match = re.search(r'^([A-Z0-9\.-]+)\s+(.+?)\s+(\d+)pcs\s+([\d,]+)\s+([\d,]+)$', first_line, re.IGNORECASE)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()  # Override Ref-No with actual item code
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        item_data['total_price'] = item_match.group(5).replace(',', '.')
    
    # Alternative pattern for service items without proper item codes
    if not item_data['quantity']:
        alt_match = re.search(r'^([A-Z]+)\s+(.+?)\s+(\d+)pcs\.?\s+([\d,]+)\s+([\d,]+)$', first_line, re.IGNORECASE)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
            item_data['total_price'] = alt_match.group(5).replace(',', '.')
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata or new items
            if not re.search(r'Ref-No\.|total net|package|freight', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '.')
            item_data['total_price'] = prices[-1].replace(',', '.')
            # Try to extract quantity if still missing
            if not item_data['quantity']:
                qty_match = re.search(r'\s+(\d+)pcs', first_line, re.IGNORECASE)
                if qty_match:
                    item_data['quantity'] = qty_match.group(1)
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#ESMA
def extract_esma_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from ESMA invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_esma_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'QTY\s+UNITS\s+DESCRIPTION\s+ITEM\s+RATE\s+AMOUNT', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for lines that start with quantity patterns (digits followed by text)
                if (re.match(r'^\d+\s+[A-Za-z]', line_clean) and 
                    not re.search(r'Total|Shipping Charges|Shipped', line_clean, re.IGNORECASE)):
                    
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+[A-Za-z]', line_clean) or
                        re.search(r'Total|Shipping Charges|Shipped|PAY FROM INVOICE', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+[A-Za-z]', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+[A-Za-z]', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_esma_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_esma_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from ESMA invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',  # PO number not shown in the extract
        'delivery_note': ''
    }
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number and date from the combined line
        # Pattern: "7/6/2023 53155"
        date_inv_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)', line_clean)
        if date_inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_date'] = date_inv_match.group(1)
            invoice_data['invoice_number'] = date_inv_match.group(2)
        
        # Extract tracking number as delivery note
        tracking_match = re.search(r'Trk#\s*([^\s]+)', line_clean, re.IGNORECASE)
        if tracking_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = tracking_match.group(1)
    
    return invoice_data

def _parse_esma_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from ESMA invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': invoice_data['order_no'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract quantity, description, and prices
    # Pattern: "1 Relay 3PDT, 15A, 24VDC Coil 080X 27.00 27.00"
    # But looking at the extract, it seems like "080X" might be part of description
    
    # First try to extract the basic pattern with quantity, description, prices
    item_match = re.search(r'^(\d+)\s+(.+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line)
    
    if item_match:
        item_data['quantity'] = item_match.group(1)
        item_data['description'] = item_match.group(2).strip()
        item_data['unit_price'] = item_match.group(3).replace(',', '')
        item_data['total_price'] = item_match.group(4).replace(',', '')
        
        # Try to extract item code from description (last word that looks like a code)
        words = item_data['description'].split()
        if words:
            last_word = words[-1]
            if re.match(r'^[A-Z0-9]+$', last_word) and len(last_word) >= 3:
                item_data['item_code'] = last_word
                item_data['description'] = ' '.join(words[:-1]).strip()
    
    # Handle shipping charges separately
    if not item_data['quantity'] and re.search(r'Shipping Charges', first_line, re.IGNORECASE):
        shipping_match = re.search(r'^(\d+)\s+Shipping Charges\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line, re.IGNORECASE)
        if shipping_match:
            item_data['quantity'] = shipping_match.group(1)
            item_data['description'] = 'Shipping Charges'
            item_data['item_code'] = 'SHIPPING'
            item_data['unit_price'] = shipping_match.group(2).replace(',', '')
            item_data['total_price'] = shipping_match.group(3).replace(',', '')
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Skip lines that look like metadata or shipping info
            if not re.search(r'Shipped|Trk#|Total', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract shipped date if available
    for line in block:
        shipped_match = re.search(r'Shipped\s+([\d/]+)', line, re.IGNORECASE)
        if shipped_match:
            item_data['shipped_date'] = shipped_match.group(1)
            break
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

#EUROMED
def extract_euromed_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Euromed invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_euromed_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            current_po_info = {'order_no': invoice_data['order_no']}
            current_parcel = ''
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'QUANTITY & DESCRIPTION OF GOODS', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for parcel sections
                parcel_match = re.search(r'PARCEL\s+(\d+)', line_clean, re.IGNORECASE)
                if parcel_match:
                    current_parcel = parcel_match.group(1)
                    continue
                
                # Look for PO number lines
                po_match = re.search(r'^(\d+)\s+([A-Z]\d+-\d+)', line_clean)
                if po_match:
                    current_po_info['order_no'] = po_match.group(1)
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_po_info.copy(), current_parcel))
                    current_block = [line_clean]
                    in_item_block = True
                    continue
                
                # Look for excess quantity lines (start with "Excess Qty")
                excess_match = re.search(r'^Excess Qty\s+([A-Z]\d+-\d+)', line_clean, re.IGNORECASE)
                if excess_match:
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_po_info.copy(), current_parcel))
                    current_block = [line_clean]
                    in_item_block = True
                    continue
                
                # Continue current item block
                if in_item_block:
                    # Stop when we hit summary lines
                    if (re.search(r'^\d+\s+[A-Z]\d+-\d+', line_clean) or
                        re.search(r'Total USD:|CERTIFIED TO BE CORRECT', line_clean, re.IGNORECASE) or
                        re.search(r'PARCEL\s+\d+', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_po_info.copy(), current_parcel))
                        current_block = [line_clean] if re.search(r'^\d+\s+[A-Z]\d+-\d+', line_clean) else []
                        in_item_block = bool(re.search(r'^\d+\s+[A-Z]\d+-\d+', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_po_info.copy(), current_parcel))
            
            # Process each item block
            for block, po_info, parcel in item_blocks:
                item_data = _parse_euromed_item_block(block, invoice_data, po_info, parcel, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_euromed_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Euromed invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number and date
        inv_match = re.search(r'Invoice No\s*:\s*([^\s]+)\s+Dated\s*:\s*([\d/]+)', line_clean, re.IGNORECASE)
        if inv_match:
            invoice_data['invoice_number'] = inv_match.group(1)
            invoice_data['invoice_date'] = inv_match.group(2)
        
        # Extract AWB number as delivery note
        awb_match = re.search(r'AWB No\s*:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if awb_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = awb_match.group(1)
        
        # Extract PO number from the items section header (fallback)
        po_match = re.search(r'PO No\s+Item Description', line_clean, re.IGNORECASE)
        if po_match and not invoice_data['order_no']:
            # PO numbers are extracted per item in the parsing function
            pass
    
    return invoice_data

def _parse_euromed_item_block(block: List[str], invoice_data: Dict, po_info: Dict, parcel: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Euromed invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': po_info['order_no'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'parcel': parcel,
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Pattern 1: Regular items "0017240 G6561-65 harrington forceps... 18 PCS 25.00 450.00"
    item_match = re.search(r'^(\d+)\s+([A-Z]\d+-\d+)\s+(.+?)\s+(\d+)\s+PCS\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line, re.IGNORECASE)
    
    if item_match:
        item_data['order_no'] = item_match.group(1)
        item_data['item_code'] = item_match.group(2)
        item_data['description'] = item_match.group(3).strip()
        item_data['quantity'] = item_match.group(4)
        item_data['unit_price'] = item_match.group(5).replace(',', '')
        item_data['total_price'] = item_match.group(6).replace(',', '')
    
    # Pattern 2: Excess quantity items "Excess Qty G6561-65 harrington forceps... 6 PCS 25.00 150.00"
    if not item_data['item_code']:
        excess_match = re.search(r'^Excess Qty\s+([A-Z]\d+-\d+)\s+(.+?)\s+(\d+)\s+PCS\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line, re.IGNORECASE)
        if excess_match:
            item_data['item_code'] = excess_match.group(1)
            item_data['description'] = excess_match.group(2).strip()
            item_data['quantity'] = excess_match.group(3)
            item_data['unit_price'] = excess_match.group(4).replace(',', '')
            item_data['total_price'] = excess_match.group(5).replace(',', '')
    
    # Pattern 3: Alternative format without PCS abbreviation
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d+)\s+([A-Z]\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line)
        if alt_match:
            item_data['order_no'] = alt_match.group(1)
            item_data['item_code'] = alt_match.group(2)
            item_data['description'] = alt_match.group(3).strip()
            item_data['quantity'] = alt_match.group(4)
            item_data['unit_price'] = alt_match.group(5).replace(',', '')
            item_data['total_price'] = alt_match.group(6).replace(',', '')
    
    # Extract GTIN number with improved logic for alphanumeric GTINs
    gtin_found = False
    
    # First, check if there's a proper GTIN number after "GTN #" or "GTIN #"
    for i, line in enumerate(block):
        # Look for "GTN #" or "GTIN #" followed by alphanumeric GTIN (not the quantity)
        # GTIN can be alphanumeric like "G586G6561650"
        gtin_match = re.search(r'GTN\s*#\s*([A-Z0-9]{8,})', line, re.IGNORECASE)
        if not gtin_match:
            gtin_match = re.search(r'GTIN\s*#\s*([A-Z0-9]{8,})', line, re.IGNORECASE)
        
        if gtin_match:
            item_data['lot'] = gtin_match.group(1)
            gtin_found = True
            break
    
    # If no GTIN found after "GTN #", check the next line after prices for a GTIN
    if not gtin_found and len(block) > 1:
        for i in range(len(block)):
            current_line = block[i].strip()
            
            # Check if this line has prices (indicating it's the main item line)
            if re.search(r'[\d,]+\.\d+\s+[\d,]+\.\d+$', current_line):
                # Check the next line for a GTIN sequence
                if i + 1 < len(block):
                    next_line = block[i + 1].strip()
                    gtin_match = re.search(r'^([A-Z0-9]{8,})$', next_line)
                    if gtin_match:
                        item_data['lot'] = gtin_match.group(1)
                        gtin_found = True
                        break
    
    # Clean up description - remove GTN # reference if no GTIN was captured after it
    if not gtin_found:
        # Remove "GTN #" or "GTIN #" and any trailing spaces from description
        item_data['description'] = re.sub(r'GTN\s*#\s*$', '', item_data['description'], flags=re.IGNORECASE).strip()
        item_data['description'] = re.sub(r'GTIN\s*#\s*$', '', item_data['description'], flags=re.IGNORECASE).strip()
    else:
        # If GTIN was found, remove the GTIN reference and the GTIN itself from description
        item_data['description'] = re.sub(r'GTN\s*#\s*[A-Z0-9]{8,}', '', item_data['description'], flags=re.IGNORECASE).strip()
        item_data['description'] = re.sub(r'GTIN\s*#\s*[A-Z0-9]{8,}', '', item_data['description'], flags=re.IGNORECASE).strip()
    
    # For multi-line descriptions, combine them (excluding GTIN lines)
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i, line in enumerate(block[1:]):
            clean_line = line.strip()
            
            # Skip lines that are just GTIN numbers or empty
            if (re.match(r'^[A-Z0-9]{8,}$', clean_line) or  # Lines with just GTINs
                re.search(r'Total USD|PARCEL', clean_line, re.IGNORECASE) or
                not clean_line):
                continue
                
            # Don't include lines that start like new items
            if not re.match(r'^\d+\s+[A-Z]', clean_line) and not re.match(r'^Excess Qty', clean_line, re.IGNORECASE):
                # Also remove GTIN references from continuation lines
                clean_line = re.sub(r'GTN\s*#\s*[A-Z0-9]{8,}', '', clean_line, flags=re.IGNORECASE).strip()
                clean_line = re.sub(r'GTIN\s*#\s*[A-Z0-9]{8,}', '', clean_line, flags=re.IGNORECASE).strip()
                if clean_line:
                    additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Faulhaber
def extract_faulhaber_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Faulhaber Pinzetten invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_faulhaber_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            in_item_block = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for order information that might change within the invoice
                if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                    # Extract order info from this line
                    order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1)
                        current_order_info['order_date'] = order_match.group(2)
                
                # Look for lines that start with item patterns (position numbers followed by item codes)
                if re.match(r'^\d+\s+\d{2}/\d{4}', line_clean):  # e.g., "1 01/2718"
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+\d{2}/\d{4}', line_clean) or
                        re.search(r'carry-over|total net|freight and package|total/EUR|payment', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d{2}/\d{4}', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+\d{2}/\d{4}', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy()))
            
            # Process each item block
            for block, order_info in item_blocks:
                item_data = _parse_faulhaber_item_block(block, invoice_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_faulhaber_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Faulhaber invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
        
        # Extract delivery note (Debit number)
        delivery_match = re.search(r'Deb\.-Nr\.:\s*(\d+)', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
    
    return invoice_data

def _parse_faulhaber_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Faulhaber invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern: "01/2718 Micro Fcps. 1x2tth. with round handle 2 114,40 30 % 160,16"
    item_match = re.search(r'^(\d{2}/\d{4})\s+(.+?)\s+(\d+)\s+([\d,]+)\s+30\s*%\s+([\d,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        item_data['total_price'] = item_match.group(5).replace(',', '.')
    
    # Alternative pattern without the 30% discount notation
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d{2}/\d{4})\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
            item_data['total_price'] = alt_match.group(5).replace(',', '.')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot number\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract customer article number from the block
    customer_art_match = None
    for line in block:
        art_match = re.search(r'your art\.-no\.:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            customer_art_match = art_match.group(1)
            break
    
    # If we have a customer article number, append it to description
    if customer_art_match and item_data['description']:
        item_data['description'] += f" (Art-No: {customer_art_match})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Lot number|LST:|your art\.-no\.', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d{2}/\d{4}', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '.')
            item_data['total_price'] = prices[-1].replace(',', '.')
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Fetzer
def extract_fetzer_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Fetzer invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_fetzer_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'qty\. ord\s+qty\. ship\.\s+qty\. B/O\s+unit\s+item no\.\s+description\s+each\s+ext\. price', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for lines that start with quantity patterns (digits followed by item codes)
                if (re.match(r'^\d+\s+\d+\s+\d+\s+[a-z]+\.[\s]*[A-Z]', line_clean) and 
                    not re.search(r'Sales Amt\.|Total/\$|backordered', line_clean, re.IGNORECASE)):
                    
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+\d+\s+\d+\s+[a-z]+\.[\s]*[A-Z]', line_clean) or
                        re.search(r'Sales Amt\.|Total/\$|backordered', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d+\s+\d+\s+[a-z]+\.[\s]*[A-Z]', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+\d+\s+\d+\s+[a-z]+\.[\s]*[A-Z]', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_fetzer_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_fetzer_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Fetzer invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',
        'order_date': '',
        'customer_number': ''
    }
    
    # Look for the ORDER NO. header line first
    header_found = False
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number and date from header
        date_inv_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+\d+', line_clean)
        if date_inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_date'] = date_inv_match.group(1)
            invoice_data['invoice_number'] = date_inv_match.group(2)
        
        # Look for the ORDER NO. header
        if re.search(r'ORDER NO\.\s+ORDER DATE\s+CUSTOMER NO\.\s+CUSTOMER P\.O\.', line_clean, re.IGNORECASE):
            header_found = True
            # The next line should contain the actual values
            if i + 1 < len(lines):
                values_line = lines[i + 1].strip()
                # Pattern: "4233755 3/15/2024 40026 0016278 0016278 3/19/2024 FedEx Ground"
                order_match = re.search(r'^(\d+)\s+([\d/]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d/]+)\s+([^\n]+)$', values_line)
                if order_match:
                    invoice_data['order_no'] = order_match.group(1)  # ORDER NO. (4233755)
                    invoice_data['order_date'] = order_match.group(2)  # ORDER DATE (3/15/2024)
                    invoice_data['customer_number'] = order_match.group(3)  # CUSTOMER NO. (40026)
            break
    
    return invoice_data

def _parse_fetzer_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Fetzer invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': invoice_data['order_no'],
        'order_date': invoice_data['order_date'],
        'customer_number': invoice_data['customer_number'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract quantities, item code, description, prices
    # Pattern: "1 1 0 ea. E6957-31 micro cup forceps, shaft 5" (125.0mm), 275.00 275.00"
    item_match = re.search(r'^(\d+)\s+(\d+)\s+\d+\s+[a-z]+\.\s*([A-Za-z0-9-]+)\s+(.+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line, re.IGNORECASE)
    
    if item_match:
        item_data['quantity'] = item_match.group(2)  # Use shipped quantity
        item_data['item_code'] = item_match.group(3).strip()
        item_data['description'] = item_match.group(4).strip()
        item_data['unit_price'] = item_match.group(5).replace(',', '')
        item_data['total_price'] = item_match.group(6).replace(',', '')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d+)\s+(\d+)\s+\d+\s+[a-z]+\.\s*([A-Za-z0-9-]+)\s+(.+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$', first_line)
        if alt_match:
            item_data['quantity'] = alt_match.group(2)
            item_data['item_code'] = alt_match.group(3).strip()
            item_data['description'] = alt_match.group(4).strip()
            item_data['unit_price'] = alt_match.group(5).replace(',', '')
            item_data['total_price'] = alt_match.group(6).replace(',', '')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot No\.\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract country of origin if available
    country_origin = ''
    for line in block:
        country_match = re.search(r'Country of origin:\s*([^\n]+)', line, re.IGNORECASE)
        if country_match:
            country_origin = country_match.group(1).strip()
            break
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Skip lines that look like metadata
            if not re.search(r'Lot No\.|Country of origin|Sales Amt|Total/\$', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d+\s+\d+\s+[a-z]+\.', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Add country of origin to description if found
    if country_origin and item_data['description']:
        item_data['description'] += f" (Origin: {country_origin})"
    
    # Extract prices from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+\.\d+', first_line)
        if len(prices) >= 2:
            item_data['unit_price'] = prices[-2].replace(',', '')
            item_data['total_price'] = prices[-1].replace(',', '')
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

#Gebrüder
def extract_gebruder_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Gebrüder invoice/statement format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract header information
            header_data = _extract_gebruder_header_info(lines)
            
            # Find invoice lines
            invoice_lines = []
            in_invoice_section = False
            
            for line in lines:
                line_clean = line.strip()
                
                # Look for the start of the invoice section
                if re.search(r'RECHNR\.\s+RECHDAT\.\s+NETTO\s+MWST\s+BRUTTO', line_clean, re.IGNORECASE):
                    in_invoice_section = True
                    continue
                
                if not in_invoice_section:
                    continue
                
                # Look for invoice lines (starting with invoice numbers)
                if re.match(r'^\d{5}\s+\d{2}\.\d{2}\.\d{4}', line_clean) and not re.search(r'SUMME|TOTAL', line_clean, re.IGNORECASE):
                    invoice_lines.append(line_clean)
            
            # Process each invoice line
            for line in invoice_lines:
                item_data = _parse_gebruder_invoice_line(line, header_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_gebruder_header_info(lines: List[str]) -> Dict[str, str]:
    """Extract header information from Gebrüder statement"""
    header_data = {
        'customer_number': '',
        'customer_name': '',
        'currency': '',
        'statement_date': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract statement date
        date_match = re.search(r'Stand:\s*(\d{2}\.\d{2}\.\d{4})', line_clean)
        if date_match and not header_data['statement_date']:
            header_data['statement_date'] = date_match.group(1)
        
        # Extract customer information
        customer_match = re.search(r'OFFENE POSTEN FÜR KUNDE:\s*(\d+)\s*-\s*([^;]+);\s*WÄHRUNG:\s*([A-Z]+)', line_clean)
        if customer_match:
            header_data['customer_number'] = customer_match.group(1)
            header_data['customer_name'] = customer_match.group(2).strip()
            header_data['currency'] = customer_match.group(3)
    
    return header_data

def _parse_gebruder_invoice_line(line: str, header_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual invoice line from Gebrüder statement"""
    if not line.strip():
        return None
    
    item_data = {
        'invoice_date': '',
        'invoice_number': '',
        'order_no': '',
        'order_date': '',
        'customer_number': header_data['customer_number'],
        'item_code': '',
        'description': 'Invoice Amount',
        'quantity': '1',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'due_date': '',
        'page': page_num + 1
    }
    
    # Pattern for invoice line: "43542 13.02.2024 432,34 0,00 432,34 . . 0,00 432,34"
    invoice_match = re.search(r'^(\d+)\s+(\d{2}\.\d{2}\.\d{4})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)', line)
    
    if invoice_match:
        item_data['invoice_number'] = invoice_match.group(1)
        item_data['invoice_date'] = invoice_match.group(2)
        item_data['unit_price'] = invoice_match.group(5).replace(',', '.')  # Using Brutto amount
        item_data['total_price'] = item_data['unit_price']  # Same as unit price for invoice amounts
        
        # The due date should be on the next line in the actual PDF structure
        # Since we're processing line by line, we'll handle this separately
        item_data['due_date'] = ''  # Will be populated from context
    
    # Look for due date in the next part of the line or subsequent processing
    due_date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+\d+\s+\d+\s+-?\d+\s+[A-Z]+', line)
    if due_date_match:
        item_data['due_date'] = due_date_match.group(1)
    
    # Only return if we have at least invoice number and amount
    if item_data['invoice_number'] and item_data['total_price']:
        return item_data
    
    return None


#Geister
def extract_geister_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Geister Medizintechnik invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    
    # First pass: extract all text and invoice-level info
    all_lines = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))
    
    # Extract invoice-level info from the entire document
    invoice_data = _extract_geister_invoice_info(all_lines)
    
    # Second pass: process each page for items
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # Store the current order info to carry over to subsequent pages
        current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
        
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\s+REF\s+TEXT\s+QTY\s+EACH\s+€\s+TOTAL\s+€', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    # Check for order information on this page (will update current_order_info if found)
                    if re.search(r'Your Order\s*#', line_clean, re.IGNORECASE):
                        order_match = re.search(r'Your Order\s*#\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                        if order_match:
                            current_order_info['order_no'] = order_match.group(1)
                            current_order_info['order_date'] = order_match.group(2)
                    continue
                
                # Look for order information that might change within the invoice
                if re.search(r'Your Order\s*#', line_clean, re.IGNORECASE):
                    order_match = re.search(r'Your Order\s*#\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                    if order_match:
                        current_order_info['order_no'] = order_match.group(1)
                        current_order_info['order_date'] = order_match.group(2)
                
                # Look for lines that start with position numbers followed by item codes
                if re.match(r'^\d{3}\s+\d{2}-\d{4}', line_clean):  # e.g., "001 21-0102"
                    if current_block and in_item_block:
                        item_blocks.append((current_block, current_order_info.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d{3}\s+\d{2}-\d{4}', line_clean) or
                        re.search(r'Turnover|Value of goods|Packing|Insurance|TOTAL/EUR', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d{3}\s+\d{2}-\d{4}', line_clean) else []
                        in_item_block = bool(re.match(r'^\d{3}\s+\d{2}-\d{4}', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, current_order_info.copy()))
            
            # Process each item block on this page
            for block, order_info in item_blocks:
                item_data = _parse_geister_item_block(block, invoice_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_geister_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Geister invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE\s*#\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date and customer ID
        date_match = re.search(r'Date:\s*(\d{2}\.\d{2}\.\d{4})\s+Customer ID:\s*(\d+)', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
            invoice_data['customer_number'] = date_match.group(2)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.\s*(\d+)\s*dated\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information (from first occurrence)
        order_match = re.search(r'Your Order\s*#\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_geister_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Geister invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],  # Use the order info passed from current page context
        'order_date': order_info['order_date'],  # Use the order info passed from current page context
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d{3})\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price, and total price
    # Pattern: "21-0102 Dilator, Vascular, acc. Garrett 1 38,50 38,50"
    item_match = re.search(r'^(\d{2}-\d{4})\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        item_data['total_price'] = item_match.group(5).replace(',', '.')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'LOT#\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract customer article number from the block
    customer_art_match = None
    for line in block:
        art_match = re.search(r'\[([^\]]+)\]', line)
        if art_match:
            customer_art_match = art_match.group(1)
            break
    
    # If we have a customer article number, append it to description
    if customer_art_match and item_data['description']:
        item_data['description'] += f" [{customer_art_match}]"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'LOT#|LST|CCT|\[.*\]', line):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d{3}\s+\d{2}-\d{4}', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Georg Alber
def extract_georgalber_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Georg Alber invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # First pass: extract all text and invoice-level info
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))
        
        # Extract invoice-level info from the entire document
        invoice_data = _extract_georgalber_invoice_info(all_lines)
        
        # Second pass: process each page for items
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            # Store the current order info to carry over to subsequent pages
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split("\n")
                
                # Find item blocks by looking for product lines
                item_blocks = []
                current_block = []
                in_item_block = False
                in_items_section = False
                
                for i, line in enumerate(lines):
                    line_clean = line.strip()
                    
                    # Look for the start of the items section
                    if re.search(r'#\s+Item\s+Shipment\s+Qty\.\s+Unit\s+Each\s+Total', line_clean, re.IGNORECASE):
                        in_items_section = True
                        continue
                    
                    if not in_items_section:
                        # Check for order information on this page (will update current_order_info if found)
                        if re.search(r'Your Order No\.', line_clean, re.IGNORECASE):
                            order_match = re.search(r'Your Order No\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                            if order_match:
                                current_order_info['order_no'] = order_match.group(1)
                                current_order_info['order_date'] = order_match.group(2)
                        continue
                    
                    # Look for order information that might change within the invoice
                    if re.search(r'Your Order No\.', line_clean, re.IGNORECASE):
                        order_match = re.search(r'Your Order No\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                        if order_match:
                            current_order_info['order_no'] = order_match.group(1)
                            current_order_info['order_date'] = order_match.group(2)
                    
                    # Look for lines that start with position numbers followed by "Item No."
                    if re.match(r'^\d+\s+Item No\.', line_clean):  # e.g., "10 Item No. 917018-P"
                        if current_block and in_item_block:
                            item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean]
                        in_item_block = True
                    elif in_item_block:
                        # Stop when we hit summary lines or next section
                        if (re.match(r'^\d+\s+Item No\.', line_clean) or
                            re.search(r'gross|weight|Preference|Payment|Delivery Terms', line_clean, re.IGNORECASE) or
                            re.search(r'Your Order No\.', line_clean, re.IGNORECASE)):
                            
                            item_blocks.append((current_block, current_order_info.copy()))
                            current_block = [line_clean] if re.match(r'^\d+\s+Item No\.', line_clean) else []
                            in_item_block = bool(re.match(r'^\d+\s+Item No\.', line_clean))
                        else:
                            current_block.append(line_clean)
                
                if current_block and in_item_block:
                    item_blocks.append((current_block, current_order_info.copy()))
                
                # Process each item block on this page
                for block, order_info in item_blocks:
                    item_data = _parse_georgalber_item_block(block, invoice_data, order_info, page_num)
                    if item_data:
                        extracted_data.append(item_data)
    
    return extracted_data

def _extract_georgalber_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Georg Alber invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number and date
        inv_match = re.search(r'Invoice No\.\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        date_match = re.search(r'dated\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Customer No\.\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note (shipment number from items)
        # This will be extracted from individual items since it's per item
        
        # Extract order information (from first occurrence)
        order_match = re.search(r'Your Order No\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_georgalber_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Georg Alber invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': '',
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, shipment, quantity, unit price (total price removed)
    # Pattern: "Item No. 917018-P 2240614 / 10 dated 05.09.2024 5 pcs. 153,65 768,25"
    item_match = re.search(r'Item No\.\s*([^\s]+)\s+(\d+)\s*/\s*\d+\s+dated\s+\d{2}\.\d{2}\.\d{4}\s+(\d+)\s+pcs\.\s+([\d,]+)', first_line, re.IGNORECASE)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['delivery_note'] = item_match.group(2)  # Shipment number as delivery note
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for items without "dated" part
    if not item_data['item_code']:
        alt_match = re.search(r'Item No\.\s*([^\s]+)\s+(\d+)\s*/\s*\d+\s+(\d+)\s+pcs\.\s+([\d,]+)', first_line, re.IGNORECASE)
        if alt_match:
            item_data['item_code'] = item_match.group(1).strip()
            item_data['delivery_note'] = item_match.group(2)
            item_data['quantity'] = item_match.group(3)
            item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Extract customer item number from the block
    customer_item_match = None
    for line in block:
        art_match = re.search(r'Your Item No\.\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            customer_item_match = art_match.group(1)
            break
    
    # Extract description
    desc_found = False
    for line in block:
        if re.search(r'Desc\.', line, re.IGNORECASE):
            # Extract everything after "Desc."
            desc_match = re.search(r'Desc\.\s*(.+)', line, re.IGNORECASE)
            if desc_match:
                item_data['description'] = desc_match.group(1).strip()
                desc_found = True
                break
    
    # If we have a customer item number, prepend it to description
    if customer_item_match and item_data['description']:
        item_data['description'] = f"{customer_item_match} - {item_data['description']}"
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot\s*(\d+\s*x\s*[A-Z]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract mark information
    mark_info = None
    for line in block:
        mark_match = re.search(r'Mark\s*([^\s]+)', line, re.IGNORECASE)
        if mark_match:
            mark_info = mark_match.group(1)
            break
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Item No\.|Your Item No\.|Desc\.|Lot|Mark|LST', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+Item No\.', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Add mark information to description if found
    if mark_info and item_data['description']:
        item_data['description'] += f" (Mark: {mark_info})"
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 1:
            item_data['unit_price'] = prices[-1].replace(',', '.')  # Use the last price found
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Getsch+Hiller
def extract_getschhiller_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Getsch+Hiller Medizintechnik invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # First pass: extract all text and invoice-level info
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))
        
        # Extract invoice-level info from the entire document
        invoice_data = _extract_getschhiller_invoice_info(all_lines)
        
        # Second pass: process each page for items
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            # Store the current order info to carry over to subsequent pages
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split("\n")
                
                # Find item blocks by looking for product lines
                item_blocks = []
                current_block = []
                in_item_block = False
                in_items_section = False
                
                for i, line in enumerate(lines):
                    line_clean = line.strip()
                    
                    # Look for the start of the items section
                    if re.search(r'POS\s+ARTICLE\s+description\s+qty\.\s+each\s+price', line_clean, re.IGNORECASE):
                        in_items_section = True
                        continue
                    
                    if not in_items_section:
                        # Check for order information on this page (will update current_order_info if found)
                        if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                            order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                            if order_match:
                                current_order_info['order_no'] = order_match.group(1)
                                current_order_info['order_date'] = order_match.group(2)
                        continue
                    
                    # Look for order information that might change within the invoice
                    if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                        if order_match:
                            current_order_info['order_no'] = order_match.group(1)
                            current_order_info['order_date'] = order_match.group(2)
                    
                    # Look for lines that start with position numbers followed by item codes
                    if re.match(r'^\d+\s+[A-Z0-9-]', line_clean):  # e.g., "1 50-41-0018"
                        if current_block and in_item_block:
                            item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean]
                        in_item_block = True
                    elif in_item_block:
                        # Stop when we hit summary lines or next section
                        if (re.match(r'^\d+\s+[A-Z0-9-]', line_clean) or
                            re.search(r'carry-over|total/EUR|payment|Terms of delivery', line_clean, re.IGNORECASE) or
                            re.search(r'your order no\.', line_clean, re.IGNORECASE)):
                            
                            item_blocks.append((current_block, current_order_info.copy()))
                            current_block = [line_clean] if re.match(r'^\d+\s+[A-Z0-9-]', line_clean) else []
                            in_item_block = bool(re.match(r'^\d+\s+[A-Z0-9-]', line_clean))
                        else:
                            current_block.append(line_clean)
                
                if current_block and in_item_block:
                    item_blocks.append((current_block, current_order_info.copy()))
                
                # Process each item block on this page
                for block, order_info in item_blocks:
                    item_data = _parse_getschhiller_item_block(block, invoice_data, order_info, page_num)
                    if item_data:
                        extracted_data.append(item_data)
    
    return extracted_data

def _extract_getschhiller_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Getsch+Hiller invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_getschhiller_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Getsch+Hiller invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price
    # Pattern: "50-41-0018 Antrum Grasping Forceps, Heuwieser 1 181,40 181,40"
    item_match = re.search(r'^([A-Z0-9-]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^([A-Z0-9-]+)\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot number\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract customer article number from the block
    customer_art_match = None
    for line in block:
        art_match = re.search(r'your art\.-no\.:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            customer_art_match = art_match.group(1)
            break
    
    # Extract drawing number from the block
    drawing_match = None
    for line in block:
        drwg_match = re.search(r'Drwg\. No\.\s*([^\s]+)', line, re.IGNORECASE)
        if drwg_match:
            drawing_match = drwg_match.group(1)
            break
    
    # If we have a customer article number, append it to description
    if customer_art_match and item_data['description']:
        item_data['description'] += f" (Art-No: {customer_art_match})"
    
    # If we have a drawing number, append it to description
    if drawing_match and item_data['description']:
        item_data['description'] += f" (Drwg: {drawing_match})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Lot number|LST:|your art\.-no\.|Drwg\. No\.', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+[A-Z0-9-]', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 1:
            item_data['unit_price'] = prices[-1].replace(',', '.')  # Use the last price found
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Gordon Brush
def extract_gordonbrush_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Gordon Brush invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_gordonbrush_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'LINE\s+PART ID\s+DESCRIPTION\s+YOU\s+WE\s+UNIT\s+EXTENDED', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for lines that start with line numbers followed by part IDs
                if re.match(r'^\d+\s+[A-Z0-9]', line_clean) and not re.search(r'SUBTOTAL|TAX AMT|FREIGHT|INVOICE TOTAL', line_clean, re.IGNORECASE):
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+[A-Z0-9]', line_clean) or
                        re.search(r'SUBTOTAL|TAX AMT|FREIGHT|INVOICE TOTAL|Make Payment To', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+[A-Z0-9]', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+[A-Z0-9]', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_gordonbrush_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_gordonbrush_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Gordon Brush invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',
        'customer_number': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number and date from header
        # Pattern: "3/25/2025 312388 0018065 CREDIT CARD"
        date_inv_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+(\d+)\s+', line_clean)
        if date_inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_date'] = date_inv_match.group(1)
            invoice_data['invoice_number'] = date_inv_match.group(2)
            invoice_data['order_no'] = date_inv_match.group(3)  # Customer PO
        
        # Extract sales order number
        so_match = re.search(r'Sales Order:\s*(\d+)', line_clean, re.IGNORECASE)
        if so_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = so_match.group(1)
        
        # Extract shipping method as delivery note
        ship_match = re.search(r'Ship Via:\s*([^\n]+)', line_clean, re.IGNORECASE)
        if ship_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = ship_match.group(1).strip()
    
    return invoice_data

def _parse_gordonbrush_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Gordon Brush invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': invoice_data['order_no'],
        'customer_number': invoice_data['customer_number'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract line number, part ID, description, quantities, unit price
    # Pattern: "1 221SSN-12 DBL SIDED UTIL SS.006/NY.016 GORDON PK12 24 24 2.78EA $66.72"
    item_match = re.search(r'^(\d+)\s+([A-Z0-9-]+)\s+(.+?)\s+(\d+)\s+(\d+)\s+([\d,]+\.\d+)EA\s+\$[\d,]+\.\d+', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(2).strip()
        item_data['description'] = item_match.group(3).strip()
        item_data['quantity'] = item_match.group(5)  # Use SHIPPED quantity (second quantity)
        item_data['unit_price'] = item_match.group(6).replace(',', '')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d+)\s+([A-Z0-9-]+)\s+(.+?)\s+(\d+)\s+(\d+)\s+([\d,]+\.\d+)EA', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(2).strip()
            item_data['description'] = alt_match.group(3).strip()
            item_data['quantity'] = alt_match.group(5)
            item_data['unit_price'] = alt_match.group(6).replace(',', '')
    
    # Extract customer part ID from the block (second line)
    customer_part_match = None
    for line in block:
        # Look for customer part ID pattern: "9212-03 EA 3/25/2025"
        cust_match = re.search(r'^([A-Z0-9-]+)\s+EA\s+[\d/]+', line)
        if cust_match:
            customer_part_match = cust_match.group(1)
            break
    
    # If we have a customer part ID, append it to description
    if customer_part_match and item_data['description']:
        item_data['description'] += f" (Cust-Part: {customer_part_match})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Skip lines that look like customer part IDs or metadata
            if not re.match(r'^[A-Z0-9-]+\s+EA\s+[\d/]+', line):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+[A-Z0-9-]', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        price_match = re.search(r'([\d,]+\.\d+)EA', first_line)
        if price_match:
            item_data['unit_price'] = price_match.group(1).replace(',', '')
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        qty_match = re.search(r'\s+(\d+)\s+(\d+)\s+', first_line)
        if qty_match:
            item_data['quantity'] = qty_match.group(2)  # Use shipped quantity
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Gunter Bissinger Medizintechnik GmbH
def extract_bissinger_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Günter Bissinger Medizintechnik invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # First pass: extract all text and invoice-level info
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))
        
        # Extract invoice-level info from the entire document
        invoice_data = _extract_bissinger_invoice_info(all_lines)
        
        # Second pass: process each page for items
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            # Store the current order info to carry over to subsequent pages
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split("\n")
                
                # Find item blocks by looking for product lines
                item_blocks = []
                current_block = []
                in_item_block = False
                in_items_section = False
                
                for i, line in enumerate(lines):
                    line_clean = line.strip()
                    
                    # Look for the start of the items section
                    if re.search(r'POS\s+ARTICLE\s+description\s+qty\.\s+each\s+price', line_clean, re.IGNORECASE):
                        in_items_section = True
                        continue
                    
                    if not in_items_section:
                        # Check for order information on this page (will update current_order_info if found)
                        if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                            order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                            if order_match:
                                current_order_info['order_no'] = order_match.group(1)
                                current_order_info['order_date'] = order_match.group(2)
                        continue
                    
                    # Look for order information that might change within the invoice
                    if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                        if order_match:
                            current_order_info['order_no'] = order_match.group(1)
                            current_order_info['order_date'] = order_match.group(2)
                    
                    # Look for lines that start with position numbers followed by item codes
                    if re.match(r'^\d+\s+\d{8}', line_clean):  # e.g., "1 81612601"
                        if current_block and in_item_block:
                            item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean]
                        in_item_block = True
                    elif in_item_block:
                        # Stop when we hit summary lines or next section
                        if (re.match(r'^\d+\s+\d{8}', line_clean) or
                            re.search(r'carry-over|Total/EUR|payment|Terms of delivery', line_clean, re.IGNORECASE) or
                            re.search(r'your order no\.', line_clean, re.IGNORECASE)):
                            
                            item_blocks.append((current_block, current_order_info.copy()))
                            current_block = [line_clean] if re.match(r'^\d+\s+\d{8}', line_clean) else []
                            in_item_block = bool(re.match(r'^\d+\s+\d{8}', line_clean))
                        else:
                            current_block.append(line_clean)
                
                if current_block and in_item_block:
                    item_blocks.append((current_block, current_order_info.copy()))
                
                # Process each item block on this page
                for block, order_info in item_blocks:
                    item_data = _parse_bissinger_item_block(block, invoice_data, order_info, page_num)
                    if item_data:
                        extracted_data.append(item_data)
    
    return extracted_data

def _extract_bissinger_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Bissinger invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*[:#]?\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*[:#]?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_bissinger_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Bissinger invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info['order_no'],
        'order_date': order_info['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price
    # Pattern: "81612601 Bipolar Forceps Adson 120 mm straight 20 73,00 1.387,00"
    item_match = re.search(r'^(\d{8})\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,\.]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d{8})\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot number\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract customer article number from the block
    customer_art_match = None
    for line in block:
        art_match = re.search(r'your art\.-no\.:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            customer_art_match = art_match.group(1)
            break
    
    # Extract drawing number from the block
    drawing_match = None
    for line in block:
        drwg_match = re.search(r'Drwg\. No\.\s*([^\s]+)', line, re.IGNORECASE)
        if drwg_match:
            drawing_match = drwg_match.group(1)
            break
    
    # If we have a customer article number, append it to description
    if customer_art_match and item_data['description']:
        item_data['description'] += f" (Art-No: {customer_art_match})"
    
    # If we have a drawing number, append it to description
    if drawing_match and item_data['description']:
        item_data['description'] += f" (Drwg: {drawing_match})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Lot number|your art\.-no\.|Drwg\. No\.|LST:|Customs tariff number|Country of Origin', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d{8}', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'[\d,]+', first_line)
        if len(prices) >= 1:
            item_data['unit_price'] = prices[-1].replace(',', '.')  # Use the last price found
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Hafner
def extract_hafner_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Hafner invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_hafner_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'#\s+Item\s+Shipment\s+Qty\.\s+Unit\s+Price\s+\(€\)\s+Amount\s+\(€\)', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for lines that start with position numbers followed by "Item No."
                if re.match(r'^\d+\s+Item No\.', line_clean):  # e.g., "10 Item No. 1100-10"
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+Item No\.', line_clean) or
                        re.search(r'Subtotal|Packaging|Total Amount Due|Steuerfreie|Weight|Payment|Shipment', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+Item No\.', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+Item No\.', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_hafner_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_hafner_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Hafner invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number and date
        inv_match = re.search(r'Invoice No\.\s*([^\s]+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        date_match = re.search(r'Date\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Customer No\.\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract order information
        order_match = re.search(r'Your Order No\.\s*([^\s]+)\s+from\s+(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
        
        # Extract shipment number as delivery note
        shipment_match = re.search(r'Shipment\s+(\d+)\s*/\s*\d+', line_clean, re.IGNORECASE)
        if shipment_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = shipment_match.group(1)
    
    return invoice_data

def _parse_hafner_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Hafner invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data['order_no'],
        'order_date': invoice_data['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, shipment, quantity, unit price
    # Pattern: "Item No. 1100-10 3250382 / 10 from 25.04.2025 10pcs. 18,56/ 1 185,60"
    item_match = re.search(r'Item No\.\s*([^\s]+)\s+(\d+)\s*/\s*\d+\s+from\s+\d{2}\.\d{2}\.\d{4}\s+(\d+)pcs\.\s+([\d,]+)/', first_line, re.IGNORECASE)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['delivery_note'] = item_match.group(2)  # Shipment number as delivery note
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'Item No\.\s*([^\s]+)\s+(\d+)\s*/\s*\d+\s+(\d+)pcs\.\s+([\d,]+)', first_line, re.IGNORECASE)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['delivery_note'] = item_match.group(2)
            item_data['quantity'] = item_match.group(3)
            item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Extract customer item number from the block
    customer_item_match = None
    for line in block:
        art_match = re.search(r'Your Item N\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            customer_item_match = art_match.group(1)
            break
    
    # Extract description
    desc_found = False
    for line in block:
        if re.search(r'Lot Desc\.', line, re.IGNORECASE):
            # Extract everything after "Lot Desc."
            desc_match = re.search(r'Lot Desc\.\s*(.+)', line, re.IGNORECASE)
            if desc_match:
                item_data['description'] = desc_match.group(1).strip()
                desc_found = True
                break
    
    # If we have a customer item number, prepend it to description
    if customer_item_match and item_data['description']:
        item_data['description'] = f"{customer_item_match} - {item_data['description']}"
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'Lot\s*(\d+\s*x\s*\d+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot'] = lot_match.group(1)
            break
    
    # Extract manufacturing date if available
    manuf_date = None
    for line in block:
        date_match = re.search(r'manufactured\s*(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if date_match:
            manuf_date = date_match.group(1)
            break
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Item No\.|Your Item N|Lot Desc\.|Lot|LST|manufactured', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+Item No\.', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # Add manufacturing date to description if found
    if manuf_date and item_data['description']:
        item_data['description'] += f" (Manufactured: {manuf_date})"
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        price_match = re.search(r'([\d,]+)/', first_line)
        if price_match:
            item_data['unit_price'] = price_match.group(1).replace(',', '.')
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        qty_match = re.search(r'(\d+)pcs\.', first_line, re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#HBH OCR Needed

#Heiss-Medical
def extract_heissmedical_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Heiss Medical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        # First pass: extract all text and invoice-level info
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))
        
        # Extract invoice-level info from the entire document
        invoice_data = _extract_heissmedical_invoice_info(all_lines)
        
        # Second pass: process each page for items
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            # Store the current order info to carry over to subsequent pages
            current_order_info = {'order_no': invoice_data['order_no'], 'order_date': invoice_data['order_date']}
            
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split("\n")
                
                # Find item blocks by looking for product lines
                item_blocks = []
                current_block = []
                in_item_block = False
                in_items_section = False
                
                for i, line in enumerate(lines):
                    line_clean = line.strip()
                    
                    # Look for the start of the items section
                    if re.search(r'POS\.\s+ARTICLE\s+description\s+qty\.\s+each\s+price', line_clean, re.IGNORECASE):
                        in_items_section = True
                        continue
                    
                    if not in_items_section:
                        # Check for order information on this page (will update current_order_info if found)
                        if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                            order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                            if order_match:
                                current_order_info['order_no'] = order_match.group(1)
                                current_order_info['order_date'] = order_match.group(2)
                        continue
                    
                    # Look for order information that might change within the invoice
                    if re.search(r'your order no\.', line_clean, re.IGNORECASE):
                        order_match = re.search(r'your order no\.\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                        if order_match:
                            current_order_info['order_no'] = order_match.group(1)
                            current_order_info['order_date'] = order_match.group(2)
                    
                    # Look for lines that start with position numbers followed by item codes
                    if re.match(r'^\d+\s+\d{5}', line_clean):  # e.g., "1 52482"
                        if current_block and in_item_block:
                            item_blocks.append((current_block, current_order_info.copy()))
                        current_block = [line_clean]
                        in_item_block = True
                    elif in_item_block:
                        # Stop when we hit summary lines or next section
                        if (re.match(r'^\d+\s+\d{5}', line_clean) or
                            re.search(r'carry-over|total net|total/EUR|payment|Terms of delivery', line_clean, re.IGNORECASE) or
                            re.search(r'your order no\.', line_clean, re.IGNORECASE)):
                            
                            item_blocks.append((current_block, current_order_info.copy()))
                            current_block = [line_clean] if re.match(r'^\d+\s+\d{5}', line_clean) else []
                            in_item_block = bool(re.match(r'^\d+\s+\d{5}', line_clean))
                        else:
                            current_block.append(line_clean)
                
                if current_block and in_item_block:
                    item_blocks.append((current_block, current_order_info.copy()))
                
                # Process each item block on this page
                for block, order_info in item_blocks:
                    item_data = _parse_heissmedical_item_block(block, invoice_data, order_info, page_num)
                    if item_data:
                        extracted_data.append(item_data)
    
    return extracted_data

def _normalize_heiss_text(text: str) -> str:
    """Normalize Heiss Medical text by handling complex duplicate character patterns"""
    if not text:
        return text
    
    # Handle the specific pattern in Heiss Medical files
    # Pattern: characters are often duplicated, but not always consistently
    normalized = []
    i = 0
    while i < len(text):
        current_char = text[i]
        normalized.append(current_char)
        
        # Skip duplicate characters but be careful with numbers and special patterns
        if current_char.isalpha():
            # Skip consecutive duplicate alphabetic characters
            j = i + 1
            while j < len(text) and text[j] == current_char:
                j += 1
            i = j
        else:
            # For non-alphabetic characters, don't skip duplicates
            # (numbers, punctuation, spaces should be preserved)
            i += 1
    
    result = ''.join(normalized)
    
    # Fix specific known patterns that don't follow the general rule
    replacements = {
        'J.obseef': 'J.',
        'GmbbH': 'GmbH',
        'GmbbHH': 'GmbH',
        'Incc.': 'Inc.',
        'IInncc..': 'Inc.',
        'NNoo..': 'No.',
        'NNOO..': 'NO.',
    }
    
    for wrong, correct in replacements.items():
        result = result.replace(wrong, correct)
    
    return result

def _extract_heissmedical_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Heiss Medical invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    # First, let's normalize the entire text and look for patterns
    normalized_lines = [_normalize_heiss_text(line.strip()) for line in lines]
    
    # Debug: print normalized lines to see what we're working with
    print("Normalized lines for debugging:")
    for i, line in enumerate(normalized_lines[:10]):  # First 10 lines
        if line:
            print(f"Line {i}: {line}")
    
    for line in normalized_lines:
        if not line:
            continue
            
        print(f"Processing line: {line}")  # Debug
        
        # Extract invoice number - more flexible pattern
        inv_match = re.search(r'INVOICE NO\.?\s*[:]?\s*(\d+)', line, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
            print(f"Found invoice number: {invoice_data['invoice_number']}")
        
        # Extract invoice date - look for "Date" pattern
        date_match = re.search(r'Date\s*[:]?\s*(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
            print(f"Found invoice date: {invoice_data['invoice_date']}")
        
        # Extract customer number
        cust_match = re.search(r'Cust\.?-?No\.?\s*[:]?\s*(\d+)', line, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
            print(f"Found customer number: {invoice_data['customer_number']}")
        
        # Extract delivery note - more flexible pattern
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
            print(f"Found delivery note: {invoice_data['delivery_note']}")
        
        # Extract order information - multiple possible patterns
        order_patterns = [
            r'your order no\.?\s*([^\s-]+)[^\d]*(\d{2}\.\d{2}\.\d{4})',
            r'order no\.?\s*([^\s-]+)\s*[-]?\s*(\d{2}\.\d{2}\.\d{4})',
            r'your order\s*([^\s-]+)\s*(\d{2}\.\d{2}\.\d{4})'
        ]
        
        for pattern in order_patterns:
            order_match = re.search(pattern, line, re.IGNORECASE)
            if order_match and not invoice_data['order_no']:
                invoice_data['order_no'] = order_match.group(1).strip()
                invoice_data['order_date'] = order_match.group(2)
                print(f"Found order: {invoice_data['order_no']} on {invoice_data['order_date']}")
                break
    
    return invoice_data

def _parse_heissmedical_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Heiss Medical invoice"""
    if not block:
        return None
    
    # Normalize the entire block first
    normalized_block = [_normalize_heiss_text(line.strip()) for line in block if line.strip()]
    
    print(f"Processing item block: {normalized_block[0] if normalized_block else 'Empty'}")
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info.get('order_no', ''),
        'order_date': order_info.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    if not normalized_block:
        return None
    
    # The first line should contain the main item data
    first_line = normalized_block[0]
    
    # Extract position number (remove it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Pattern for item lines like: "58609 RHOTON-TYPE DISS 7 1/2\" 2M 1 20,30 20,30"
    # More flexible pattern that handles various spacings
    item_patterns = [
        r'^(\d{5,6})\s+([A-Za-z].+?)\s+(\d+)\s+([\d,]+\.?\d*)\s+[\d,]+\.?\d*$',
        r'^(\d{5,6})\s+([A-Za-z].+?)\s+(\d+)\s+([\d,]+\.?\d*)',
        r'^(\d{5,6})\s+(.+?)\s+(\d+)\s+([\d,]+\.?\d*)'
    ]
    
    for pattern in item_patterns:
        item_match = re.search(pattern, first_line)
        if item_match:
            item_data['item_code'] = item_match.group(1).strip()
            item_data['description'] = item_match.group(2).strip()
            item_data['quantity'] = item_match.group(3)
            item_data['unit_price'] = item_match.group(4).replace(',', '.')
            print(f"Found item: {item_data['item_code']} - {item_data['description']}")
            break
    
    # If still no match, try a more basic approach - split and analyze
    if not item_data['item_code']:
        parts = first_line.split()
        if len(parts) >= 4:
            # Look for a 5-6 digit number at the start
            if re.match(r'^\d{5,6}$', parts[0]):
                item_data['item_code'] = parts[0]
                # Try to find quantity and price
                for i in range(len(parts)-1, 0, -1):
                    if re.match(r'^\d+$', parts[i]):  # Quantity
                        item_data['quantity'] = parts[i]
                        # Description is everything between code and quantity
                        item_data['description'] = ' '.join(parts[1:i])
                        # Look for price before quantity
                        if i > 0 and re.match(r'^[\d,]+$', parts[i-1]):
                            item_data['unit_price'] = parts[i-1].replace(',', '.')
                        break
    
    # Extract metadata from the entire block
    for line in normalized_block:
        # Lot number
        lot_match = re.search(r'Lot number\s*([^\s/]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
        
        # Customer article number
        art_match = re.search(r'your art\.?-?no\.?:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            art_no = art_match.group(1)
            if art_no and item_data['description']:
                item_data['description'] += f" (Art-No: {art_no})"
        
        # MDL registration number
        mdl_match = re.search(r'MDL Reg\.? No\.?:\s*([^\s]+)', line, re.IGNORECASE)
        if mdl_match:
            mdl_no = mdl_match.group(1)
            if mdl_no and item_data['description']:
                item_data['description'] += f" (MDL: {mdl_no})"
    
    # If we still don't have a unit price, try to extract it from any line
    if not item_data['unit_price']:
        for line in normalized_block:
            prices = re.findall(r'\b(\d+[,.]\d{2})\b', line)
            if prices:
                item_data['unit_price'] = prices[0].replace(',', '.')
                break
    
    # Only return if we have essential data
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    print(f"Failed to parse item block: {normalized_block}")
    return None


#Hermann
def extract_hermann_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Hermann invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_hermann_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section (POS header)
                if re.search(r'POS\s+ARTICLE\s+description', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                # Alternative header pattern for different formats
                if re.search(r'POS\s+ARTICLE\s+description\s+lot number:', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for lines that start with position numbers followed by item codes (H-prefixed codes)
                if re.match(r'^\d+\s+H\d+-\d+', line_clean):  # e.g., "1 H118-25438"
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+H\d+-\d+', line_clean) or
                        re.search(r'total net|package|total/EUR|payment|delivery|Delivery|Goods remain|Complaints', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+H\d+-\d+', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+H\d+-\d+', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_hermann_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_hermann_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Hermann invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number (both PROFORMA INVOICE and COMMERCIAL INVOICE)
        inv_match = re.search(r'(?:PROFORMA|COMMERCIAL)\s+INVOICE\s*:?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Alternative invoice number pattern
        if not invoice_data['invoice_number']:
            alt_inv_match = re.search(r'INVOICE\s+(\d+)', line_clean, re.IGNORECASE)
            if alt_inv_match:
                invoice_data['invoice_number'] = alt_inv_match.group(1)
        
        # Extract customer number and date from the specific format:
        # "Cust.-No. Date Our sign Your inq. No. Your inq. date"
        # "11444 15.02.2018 sb 0006821 15.02.2018"
        if re.search(r'Cust\.-No\.\s+Date\s+Our sign\s+Your inq\. No\.\s+Your inq\. date', line_clean, re.IGNORECASE):
            # The next line should contain the actual data
            if i + 1 < len(lines):
                data_line = lines[i + 1].strip()
                # Pattern: "11444 15.02.2018 sb 0006821 15.02.2018"
                data_match = re.search(r'^(\d+)\s+(\d{2}\.\d{2}\.\d{4})\s+\w+\s+(\d+)\s+(\d{2}\.\d{2}\.\d{4})$', data_line)
                if data_match:
                    if not invoice_data['customer_number']:
                        invoice_data['customer_number'] = data_match.group(1)
                    if not invoice_data['invoice_date']:
                        invoice_data['invoice_date'] = data_match.group(2)
                    if not invoice_data['order_no']:
                        invoice_data['order_no'] = data_match.group(3)
                    if not invoice_data['order_date']:
                        invoice_data['order_date'] = data_match.group(4)
        
        # Alternative pattern for customer number and date (when not in the header table format)
        cust_date_match = re.search(r'Cust\.-No\.\s*:\s*(\d+).*Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if cust_date_match:
            if not invoice_data['customer_number']:
                invoice_data['customer_number'] = cust_date_match.group(1)
            if not invoice_data['invoice_date']:
                invoice_data['invoice_date'] = cust_date_match.group(2)
        
        # Extract invoice date separately if still missing
        if not invoice_data['invoice_date']:
            date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
            if date_match:
                invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number separately if still missing
        if not invoice_data['customer_number']:
            cust_match = re.search(r'Cust\.?-?No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
            if cust_match:
                invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.?\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
        
        # Extract OC number (order confirmation) as alternative order reference
        if not invoice_data['order_no']:
            oc_match = re.search(r'OC No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
            if oc_match:
                invoice_data['order_no'] = oc_match.group(1)
        
        # Extract your inquiry information as alternative (for the specific header format)
        if not invoice_data['order_no']:
            inq_match = re.search(r'Your inq\. No\.\s*(\d+)\s*Your inq\. date\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
            if inq_match:
                invoice_data['order_no'] = inq_match.group(1)
                invoice_data['order_date'] = inq_match.group(2)
    
    return invoice_data

def _parse_hermann_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Hermann invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data['order_no'],
        'order_date': invoice_data['order_date'],
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price
    # Pattern: "H118-25438 GORNEY RAKE retractor 7,5 cm 5 42,74 213,70"
    item_match = re.search(r'^(H\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting (with lot numbers)
    if not item_data['item_code']:
        alt_match = re.search(r'^(H\d+-\d+)\s+(.+?)\s+([A-Z0-9/-]+)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['lot'] = alt_match.group(3).strip()  # Lot number from main line
            item_data['quantity'] = alt_match.group(4)
            item_data['unit_price'] = alt_match.group(5).replace(',', '.')
    
    # More flexible pattern if above patterns fail
    if not item_data['item_code']:
        flex_match = re.search(r'^(H\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if flex_match:
            item_data['item_code'] = flex_match.group(1).strip()
            item_data['description'] = flex_match.group(2).strip()
            item_data['quantity'] = flex_match.group(3)
            item_data['unit_price'] = flex_match.group(4).replace(',', '.')
    
    # Extract metadata from the entire block
    for line in block:
        # Lot number (if not already extracted from main line)
        if not item_data['lot']:
            lot_match = re.search(r'lot number:\s*([A-Z0-9/-]+)', line, re.IGNORECASE)
            if lot_match:
                item_data['lot'] = lot_match.group(1).strip()
        
        # Customer article number
        art_match = re.search(r'your art\.?-?no\.?:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            art_no = art_match.group(1)
            if art_no and item_data['description']:
                item_data['description'] += f" (Art-No: {art_no})"
        
        # MDL/LST registration number
        mdl_match = re.search(r'(?:MDL|LST)\s+Reg\.?\s+No\.?:\s*([^\s]+)', line, re.IGNORECASE)
        if mdl_match:
            mdl_no = mdl_match.group(1)
            if mdl_no and item_data['description']:
                item_data['description'] += f" (Reg: {mdl_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'your art\.?-?no\.?|MDL Reg|LST Reg|lot number', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+H\d+-\d+', clean_line):  # Don't include lines that start like new items
                    # Check if this line contains additional description (like "with spring, 38mm wide")
                    if re.match(r'^[a-zA-Z]', clean_line):  # Starts with a letter
                        additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', first_line)
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for numbers that are likely quantities (not prices)
        numbers = re.findall(r'\b(\d+)\b', first_line)
        if len(numbers) >= 2:
            # The number before the prices is likely the quantity
            for i, num in enumerate(numbers):
                if i < len(numbers) - 1 and re.search(r'\d+[,.]\d{2}', first_line.split(num)[-1]):
                    item_data['quantity'] = num
                    break
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#HGR
def extract_hgr_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from HGR invoice format (both Rechnung and Mahnung).
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # First, determine if this is a Rechnung (invoice) or Mahnung (reminder)
            is_reminder = any('reminder' in line.lower() or 'mahnung' in line.lower() for line in lines)
            
            if is_reminder:
                # Process as payment reminder
                invoice_data = _extract_hgr_reminder_info(lines)
                # For reminders, we create a single item representing the overdue invoice
                item_data = _parse_hgr_reminder_block(lines, invoice_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
            else:
                # Process as regular invoice
                invoice_data = _extract_hgr_invoice_info(lines)
                
                # Find item blocks for regular invoices
                item_blocks = []
                current_block = []
                in_item_block = False
                in_items_section = False
                
                for i, line in enumerate(lines):
                    line_clean = line.strip()
                    
                    # Look for the start of the items section (POS header)
                    if re.search(r'POS\s+ARTICLE\s+description\s+qty\.', line_clean, re.IGNORECASE):
                        in_items_section = True
                        continue
                    
                    if not in_items_section:
                        continue
                    
                    # Look for lines that start with position numbers followed by item codes
                    if re.match(r'^\d+\s+\d+-\d+', line_clean):  # e.g., "1 6-1215/07"
                        if current_block and in_item_block:
                            item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean]
                        in_item_block = True
                    elif in_item_block:
                        # Stop when we hit summary lines or next section
                        if (re.match(r'^\d+\s+\d+-\d+', line_clean) or
                            re.search(r'total net|package|freight|total/EUR|payment|Terms of', line_clean, re.IGNORECASE)):
                            
                            item_blocks.append((current_block, invoice_data.copy()))
                            current_block = [line_clean] if re.match(r'^\d+\s+\d+-\d+', line_clean) else []
                            in_item_block = bool(re.match(r'^\d+\s+\d+-\d+', line_clean))
                        else:
                            current_block.append(line_clean)
                
                if current_block and in_item_block:
                    item_blocks.append((current_block, invoice_data.copy()))
                
                # Process each item block
                for block, inv_data in item_blocks:
                    item_data = _parse_hgr_item_block(block, inv_data, page_num)
                    if item_data:
                        extracted_data.append(item_data)
    
    return extracted_data

def _extract_hgr_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from HGR regular invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.?\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _extract_hgr_reminder_info(lines: List[str]) -> Dict[str, str]:
    """Extract information from HGR payment reminder"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': '',
        'reminder_type': '',
        'due_date': '',
        'days_overdue': '',
        'gross_amount': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract reminder type
        if '2nd reminder' in line_clean:
            invoice_data['reminder_type'] = '2nd reminder'
        elif 'reminder' in line_clean.lower() and not invoice_data['reminder_type']:
            invoice_data['reminder_type'] = '1st reminder'
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract reminder date
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)  # Using reminder date as invoice date
    
    # Extract invoice table data
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Look for the invoice table header
        if re.search(r'Invoice No\.\s+Invoice Date\s+due since\s+falling since\s+gross amount', line_clean, re.IGNORECASE):
            # The next line should contain the invoice data
            if i + 1 < len(lines):
                data_line = lines[i + 1].strip()
                # Pattern: "22461738 20.11.2024 19.01.2025 17 Tage 163,00 EUR 0,00"
                data_match = re.search(r'^(\d+)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})\s+(\d+)\s+Tage\s+([\d,]+)', data_line)
                if data_match:
                    if not invoice_data['invoice_number']:
                        invoice_data['invoice_number'] = data_match.group(1)
                    if not invoice_data['order_date']:  # Using invoice date as order date
                        invoice_data['order_date'] = data_match.group(2)
                    invoice_data['due_date'] = data_match.group(3)
                    invoice_data['days_overdue'] = data_match.group(4)
                    invoice_data['gross_amount'] = data_match.group(5).replace(',', '.')
    
    return invoice_data

def _parse_hgr_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from HGR regular invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data['order_no'],
        'order_date': invoice_data['order_date'],
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price
    # Pattern: "6-1215/07 Alms skin retractor, blunt,7cm 10 27,75 277,50"
    item_match = re.search(r'^(\S+?-\d+/\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_data['item_code'] + ' ' + item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different item code formats
    if not item_data['item_code']:
        alt_match = re.search(r'^(\S+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
        if alt_match and len(alt_match.group(1)) > 3:  # Ensure it's a reasonable item code
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract metadata from the entire block
    for line in block:
        # Lot number
        lot_match = re.search(r'Lot number\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
        
        # Customer article number
        art_match = re.search(r'your art\.?-?no\.?:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            art_no = art_match.group(1)
            if art_no and item_data['description']:
                item_data['description'] += f" (Art-No: {art_no})"
        
        # LST number
        lst_match = re.search(r'LST\s*#?:\s*([^\s]+)', line, re.IGNORECASE)
        if lst_match:
            lst_no = lst_match.group(1)
            if lst_no and item_data['description']:
                item_data['description'] += f" (LST: {lst_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Lot number|your art\.?-?no\.?|LST\s*#?', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\S+-\d+', clean_line):  # Don't include lines that start like new items
                    additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', first_line)
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

def _parse_hgr_reminder_block(lines: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse HGR payment reminder as a single item"""
    # Build description with reminder details
    description = f"Payment Reminder - {invoice_data.get('reminder_type', 'Reminder')}"
    
    # Add overdue information to description
    if invoice_data.get('days_overdue'):
        description += f" - {invoice_data['days_overdue']} days overdue"
    
    if invoice_data.get('due_date'):
        description += f" - Due since {invoice_data['due_date']}"
    
    item_data = {
        'invoice_date': invoice_data.get('order_date', ''),  # Use original invoice date
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data['invoice_number'],  # Use invoice number as order number for reminders
        'order_date': invoice_data.get('order_date', invoice_data['invoice_date']),
        'delivery_note': '',
        'item_code': 'REMINDER',
        'description': description,
        'quantity': '1',
        'unit_price': invoice_data.get('gross_amount', '0'),
        'lot': '',
        'page': page_num + 1
    }
    
    return item_data


#Holger
def extract_holger_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Holger invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_holger_invoice_info(lines)
            
            # Find item blocks - Holger items span multiple lines
            item_blocks = []
            current_block = []
            collecting_item = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for lines that start with position numbers (e.g., "1 2 G91094-21")
                if re.match(r'^\d+\s+\d+\s+[A-Z]\d', line_clean):
                    if current_block and collecting_item:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    collecting_item = True
                
                # Look for the second line of item data (e.g., "16739 0-27-3924 D094127 JZF 3617 778826221436 $15.40 $30.80")
                elif collecting_item and re.match(r'^\d{4,}\s+[\dA-Z-]', line_clean):
                    current_block.append(line_clean)
                    # After getting the second line, this item is complete
                    item_blocks.append((current_block, invoice_data.copy()))
                    current_block = []
                    collecting_item = False
                
                # Continue collecting description lines if we're in an item block
                elif collecting_item and current_block:
                    # Stop if we hit a line that looks like the start of a new section
                    if (re.match(r'^\d', line_clean) or 
                        re.search(r'Certificate:|Net amount|Shipping|Tax|Packing Slip', line_clean)):
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                        collecting_item = False
                    else:
                        current_block.append(line_clean)
            
            if current_block and collecting_item:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_holger_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_holger_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Holger invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'packing_slip': ''
    }
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number - look for "Invoice No. 3617" pattern
        inv_match = re.search(r'Invoice No\.\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date and customer number from the same line
        # Pattern: "9/26/2024 N5533" or similar
        date_cust_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+([A-Z]\d+)', line_clean)
        if date_cust_match:
            if not invoice_data['invoice_date']:
                # Convert to DD.MM.YYYY format
                us_date = date_cust_match.group(1)
                parts = us_date.split('/')
                if len(parts) == 3:
                    invoice_data['invoice_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
            
            if not invoice_data['customer_number']:
                invoice_data['customer_number'] = date_cust_match.group(2)
        
        # Extract packing slip number
        if re.search(r'Packing Slip', line_clean, re.IGNORECASE):
            # Look for number in the same line or next line
            slip_match = re.search(r'(\d+)', line_clean)
            if slip_match:
                invoice_data['packing_slip'] = slip_match.group(1)
    
    return invoice_data

def _parse_holger_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Holger invoice"""
    if not block or len(block) < 2:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data.get('order_no', ''),
        'order_date': invoice_data.get('order_date', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # First line: "1 2 G91094-21 Zenith frazier suction tube, angled, w/ finger cut-off..."
    first_line = block[0].strip()
    
    # Second line: "16739 0-27-3924 D094127 JZF 3617 778826221436 $15.40 $30.80"
    second_line = block[1].strip() if len(block) > 1 else ""
    
    # Parse first line: position, quantity, item code, and description
    first_parts = first_line.split()
    if len(first_parts) >= 3:
        # Position is first_parts[0], quantity is first_parts[1], item code is first_parts[2]
        item_data['quantity'] = first_parts[1]
        item_data['item_code'] = first_parts[2]
        
        # Description is everything after the item code
        desc_start = len(first_parts[0]) + len(first_parts[1]) + len(first_parts[2]) + 3
        item_data['description'] = first_line[desc_start:].strip()
    
    # Parse second line: PO number, lot number, MDL number, prices, etc.
    second_parts = second_line.split()
    if len(second_parts) >= 8:
        # PO number: second_parts[0] (e.g., "16739")
        if not item_data['order_no']:
            item_data['order_no'] = second_parts[0]
        
        # Lot number: second_parts[1] (e.g., "0-27-3924")
        item_data['lot'] = second_parts[1]
        
        # MDL number: second_parts[2] (e.g., "D094127")
        mdl_number = second_parts[2]
        
        # Unit price: look for $15.40 pattern (usually second to last)
        for part in second_parts:
            if part.startswith('$'):
                price = part[1:].replace(',', '')  # Remove $ and commas
                if '.' in price:  # Verify it's a decimal price
                    item_data['unit_price'] = price
                    break
        
        # Add MDL number to description
        if mdl_number and item_data['description']:
            item_data['description'] += f" (MDL: {mdl_number})"
    
    # Handle multi-line descriptions (lines beyond the first two)
    if len(block) > 2:
        additional_desc = []
        for line in block[2:]:
            clean_line = line.strip()
            if clean_line and not re.match(r'^\d', clean_line):  # Not starting with number
                additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' ' + ' '.join(additional_desc)
    
    # If we didn't find unit price in second line, try to find it anywhere in the block
    if not item_data['unit_price']:
        for line in block:
            price_match = re.search(r'\$([\d,]+\.\d{2})', line)
            if price_match:
                # Take the first price found as unit price
                item_data['unit_price'] = price_match.group(1).replace(',', '')
                break
    
    # Only return if we have essential data
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#ILG
def extract_ilg_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from ILG invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_ilg_invoice_info(lines)
            
            # Find item blocks by looking for product lines
            item_blocks = []
            current_block = []
            in_item_block = False
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section (PO/ARTICLE header)
                if re.search(r'POARTICLE\s+description\s+qty\.', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Look for lines that start with position numbers followed by item codes
                if re.match(r'^\d+\s+\d+-\w+-\d+-\d+', line_clean):  # e.g., "1 69-MC-12-130"
                    if current_block and in_item_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_item_block = True
                elif in_item_block:
                    # Stop when we hit summary lines or next section
                    if (re.match(r'^\d+\s+\d+-\w+-\d+-\d+', line_clean) or
                        re.search(r'total net|package|total/EUR|payment|delivery|Country of Origin', line_clean, re.IGNORECASE)):
                        
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d+-\w+-\d+-\d+', line_clean) else []
                        in_item_block = bool(re.match(r'^\d+\s+\d+-\w+-\d+-\d+', line_clean))
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_item_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_ilg_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_ilg_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from ILG invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE NO\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract order information
        order_match = re.search(r'your order no\.?\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['order_date'] = order_match.group(2)
    
    return invoice_data

def _parse_ilg_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from ILG invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data['order_no'],
        'order_date': invoice_data['order_date'],
        'delivery_note': invoice_data['delivery_note'],
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price
    # Pattern: "69-MC-12-130 McGulloch Suction tube 12 FR. 10 27,50 275,00"
    item_match = re.search(r'^(\d+-\w+-\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d+-\w+-\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = item_match.group(2).strip()
            item_data['quantity'] = item_match.group(3)
            item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Extract metadata from the entire block
    for line in block:
        # Lot number
        lot_match = re.search(r'lot number:\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
        
        # LST number
        lst_match = re.search(r'LST:\s*([^\s]+)', line, re.IGNORECASE)
        if lst_match:
            lst_no = lst_match.group(1)
            if lst_no and item_data['description']:
                item_data['description'] += f" (LST: {lst_no})"
        
        # Drawing number
        drawing_match = re.search(r'Drawing no\.:\s*([^\s]+)', line, re.IGNORECASE)
        if drawing_match:
            drawing_no = drawing_match.group(1)
            if drawing_no and item_data['description']:
                item_data['description'] += f" (Drawing: {drawing_no})"
        
        # Index
        index_match = re.search(r'Index:\s*([^\s]+)', line, re.IGNORECASE)
        if index_match:
            index_no = index_match.group(1)
            if index_no and item_data['description']:
                item_data['description'] += f" (Index: {index_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'lot number:|LST:|Drawing no\.:|Index:', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d+-\w+-\d+-\d+', clean_line):  # Don't include lines that start like new items
                    # Check if this line contains additional description (like "WL 130 mm")
                    if re.match(r'^[a-zA-Z]', clean_line):  # Starts with a letter
                        additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', first_line)
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for numbers that are likely quantities (not prices)
        numbers = re.findall(r'\b(\d+)\b', first_line)
        if len(numbers) >= 2:
            # The number before the prices is likely the quantity
            for i, num in enumerate(numbers):
                if i < len(numbers) - 1 and re.search(r'\d+[,.]\d{2}', first_line.split(num)[-1]):
                    item_data['quantity'] = num
                    break
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Josef Betzler (Partial)
def extract_josef_betzler_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Josef Betzler invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_josef_betzler_invoice_info(lines)
            
            # Use a simpler approach - find items directly
            item_blocks = _find_josef_betzler_items_directly(lines, invoice_data, page_num)
            
            for item_data in item_blocks:
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _find_josef_betzler_items_directly(lines: List[str], invoice_data: Dict, page_num: int) -> List[Dict]:
    """Find items directly by scanning for JB- patterns"""
    items = []
    current_order_info = {'order_no': invoice_data.get('order_no', ''), 
                         'order_date': invoice_data.get('order_date', '')}
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for Orderconfirmation to update order info
        if 'Orderconfirmation' in line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            order_match = re.search(r'Your order\s+([^\s]+)\s+dtd\.\s+(\d{2}\.\d{2}\.\d{4})', next_line, re.IGNORECASE)
            if order_match:
                current_order_info = {
                    'order_no': order_match.group(1),
                    'order_date': order_match.group(2)
                }
                i += 2  # Skip both lines
                continue
        
        # Look for your Ref.: lines followed by JB- items
        if 'your Ref.:' in line and i + 1 < len(lines):
            # Extract customer reference
            ref_match = re.search(r'your Ref\.:\s*([^\s]+)', line, re.IGNORECASE)
            customer_ref = ref_match.group(1) if ref_match else None
            
            # Check next line for JB- pattern
            next_line = lines[i + 1].strip()
            if 'JB-' in next_line:
                # This is an item - collect the item block
                item_block = [line, next_line]
                
                # Collect subsequent lines that belong to this item
                j = i + 2
                while j < len(lines):
                    next_line_text = lines[j].strip()
                    # Stop if we hit another item marker or end of section
                    if (not next_line_text or 
                        'your Ref.:' in next_line_text or 
                        'Orderconfirmation' in next_line_text or
                        'Value of goods' in next_line_text or
                        'page' in next_line_text):
                        break
                    item_block.append(next_line_text)
                    j += 1
                
                # Parse the item block
                item_data = _parse_josef_betzler_item_simple(item_block, invoice_data, current_order_info, customer_ref, page_num)
                if item_data:
                    items.append(item_data)
                
                i = j  # Move to the next position
                continue
        
        i += 1
    
    return items

def _parse_josef_betzler_item_simple(block: List[str], invoice_data: Dict, order_info: Dict, customer_ref: str, page_num: int) -> Optional[Dict]:
    """Simple parsing of Josef Betzler item"""
    if len(block) < 2:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info.get('order_no', ''),
        'order_date': order_info.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The second line should contain the item data
    item_line = block[1].strip()
    
    # Parse item line: "2 JB-4665-30 Henly Cartoid Retractor, 16 cm, 6 1/2´´, 2 ea 129,90 259,80"
    # Try multiple patterns
    patterns = [
        r'(\d+)\s+(JB-\d+-\d+)\s+(.+?)\s+(\d+)\s+ea\s+([\d,]+)\s+[\d,]+',
        r'(JB-\d+-\d+)\s+(.+?)\s+(\d+)\s+ea\s+([\d,]+)\s+[\d,]+',
        r'(\d+)\s+(JB-\d+-\d+)\s+(.+?)\s+(\d+)\s+ea\s+([\d,]+)',
        r'(JB-\d+-\d+)\s+(.+?)\s+(\d+)\s+ea\s+([\d,]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, item_line)
        if match:
            groups = match.groups()
            if len(groups) == 5:  # With position number
                item_data['item_code'] = groups[1]
                item_data['description'] = groups[2].strip()
                item_data['quantity'] = groups[3]
                item_data['unit_price'] = groups[4].replace(',', '.')
            elif len(groups) == 4:  # Without position number
                item_data['item_code'] = groups[0]
                item_data['description'] = groups[1].strip()
                item_data['quantity'] = groups[2]
                item_data['unit_price'] = groups[3].replace(',', '.')
            break
    
    # If regex failed, try simple string parsing
    if not item_data['item_code'] and 'JB-' in item_line:
        parts = item_line.split()
        for j, part in enumerate(parts):
            if part.startswith('JB-'):
                item_data['item_code'] = part
                # Try to find quantity and price
                for k in range(j+1, len(parts)):
                    if parts[k] == 'ea' and k > 0 and k + 1 < len(parts):
                        item_data['quantity'] = parts[k-1]
                        # Get price (remove comma)
                        price_str = parts[k+1].replace(',', '.')
                        if re.match(r'^\d+\.?\d*$', price_str):
                            item_data['unit_price'] = price_str
                        # Description is everything between JB- code and quantity
                        desc_start = item_line.find(part) + len(part)
                        desc_end = item_line.find(parts[k-1])
                        item_data['description'] = item_line[desc_start:desc_end].strip()
                        break
                break
    
    # Extract metadata from the block
    for line in block:
        # LST number
        lst_match = re.search(r'LST\s*([A-Z]\d+)', line, re.IGNORECASE)
        if lst_match:
            lst_no = lst_match.group(1)
            if lst_no and item_data['description']:
                item_data['description'] += f" (LST: {lst_no})"
        
        # Charge (lot number)
        charge_match = re.search(r'Charge:\s*([^\s]+)', line, re.IGNORECASE)
        if charge_match and not item_data['lot']:
            item_data['lot'] = charge_match.group(1)
        
        # Classification
        class_match = re.search(r'Classification:\s*([^\s]+)', line, re.IGNORECASE)
        if class_match:
            class_no = class_match.group(1)
            if class_no and item_data['description']:
                item_data['description'] += f" (Class: {class_no})"
        
        # Quantity from Charge line
        qty_match = re.search(r'Quantity:\s*(\d+)', line, re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    # Add customer reference to description
    if customer_ref and item_data['description']:
        item_data['description'] = f"{customer_ref} - {item_data['description']}"
    
    # Add description continuation (lines after the item line that don't contain metadata)
    desc_lines = []
    for k in range(2, len(block)):
        line_text = block[k].strip()
        if (line_text and 
            not re.search(r'LST|Charge:|Classification:|Quantity:', line_text, re.IGNORECASE) and
            len(line_text) > 3 and
            re.match(r'^[a-zA-Z]', line_text)):
            desc_lines.append(line_text)
    
    if desc_lines:
        continuation = ' '.join(desc_lines)
        if continuation and item_data['description']:
            item_data['description'] += ' - ' + continuation
    
    # Only return if we have essential data
    if item_data['item_code'] and item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

def _extract_josef_betzler_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Josef Betzler invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number (after "No.:")
        inv_match = re.search(r'No\.:\s*(\d+)', line_clean)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date (after "Date:")
        date_match = re.search(r'Date:\s*(\d{2}\.\d{2}\.\d{4})', line_clean)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number (account number after "acc.no.:")
        cust_match = re.search(r'acc\.no\.:\s*([^\s]+)', line_clean)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract your reference (main order reference)
        ref_match = re.search(r'your ref\.:\s*([^\s]+)', line_clean)
        if ref_match and not invoice_data['order_no']:
            invoice_data['order_no'] = ref_match.group(1)
        
        # Extract your reference date
        ref_date_match = re.search(r'dtd\.:\s*(\d{2}\.\d{2}\.\d{4})', line_clean)
        if ref_date_match and not invoice_data['order_date']:
            invoice_data['order_date'] = ref_date_match.group(1)
    
    return invoice_data


#KAPP
def extract_kapp_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from KAPP invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_kapp_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_info = {'order_no': '', 'order_date': ''}
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\.\s+ARTICLE\s+description\s+qty\.\s+each\s+price', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines
                if re.search(r'POS\.\s+ARTICLE|total net|package|total/EUR', line_clean, re.IGNORECASE):
                    continue
                
                # Look for order information
                order_match = re.search(r'your order no\.\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    current_order_info = {
                        'order_no': order_match.group(1),
                        'order_date': order_match.group(2)
                    }
                    continue
                
                # Look for lines that start with position numbers followed by item codes
                if re.match(r'^\d+\s+[A-Z]\d+', line_clean):  # e.g., "1 N6833-07"
                    if current_block and in_items_section:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                    current_block = [line_clean]
                
                # Continue collecting lines for the current item
                elif current_block:
                    # Stop if we hit a new item or summary section
                    if (re.match(r'^\d+\s+[A-Z]\d+', line_clean) or
                        re.search(r'total net|package|total/EUR|payment:|delivery terms', line_clean, re.IGNORECASE)):
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+[A-Z]\d+', line_clean) else []
                    else:
                        current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
            
            # Process each item block
            for block, inv_data, order_info in item_blocks:
                item_data = _parse_kapp_item_block(block, inv_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_kapp_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from KAPP invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'COMMERCIAL INVOICE\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Cust\.-No\.\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.\s*(\d+)\s*dt\.\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
    
    return invoice_data

def _parse_kapp_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from KAPP invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info.get('order_no', ''),
        'order_date': order_info.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract item code, description, quantity, unit price
    # Pattern: "N6833-07 Oldberg rongeur,straight, 18 cm ,6 mm 3 137,21 411,63"
    item_match = re.search(r'^([A-Z]\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^([A-Z]\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract metadata from the entire block
    for line in block:
        # Lot number
        lot_match = re.search(r'lot number:\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
        
        # Device Listing
        device_match = re.search(r'Device Listing:\s*([^\s]+)', line, re.IGNORECASE)
        if device_match:
            device_no = device_match.group(1)
            if device_no and item_data['description']:
                item_data['description'] += f" (Device: {device_no})"
        
        # Our item number
        our_item_match = re.search(r'Our item-no\.\s*([^\s]+)', line, re.IGNORECASE)
        if our_item_match:
            our_item_no = our_item_match.group(1)
            if our_item_no and item_data['description']:
                item_data['description'] += f" (Our Item: {our_item_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'lot number:|Device Listing:|Our item-no:', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+[A-Z]\d+', clean_line):  # Don't include lines that start like new items
                    # Check if this line contains additional description
                    if re.match(r'^[a-zA-Z]', clean_line):  # Starts with a letter
                        additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', first_line)
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for numbers that are likely quantities (not prices)
        numbers = re.findall(r'\b(\d+)\b', first_line)
        if len(numbers) >= 2:
            # The number before the prices is likely the quantity
            for i, num in enumerate(numbers):
                if i < len(numbers) - 1 and re.search(r'\d+[,.]\d{2}', first_line.split(num)[-1]):
                    item_data['quantity'] = num
                    break
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Kohler
def extract_kohler_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Kohler invoice format (both Proforma and regular invoices).
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_kohler_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_info = {'order_no': '', 'order_date': ''}
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section (different headers for Proforma vs regular)
                if (re.search(r'Pos\.\s+Ref\.\s+Description\s+Kat\.\s+Qty\.\s+Unit\s+Price\s+Total', line_clean, re.IGNORECASE) or
                    re.search(r'Pos\.\s+Ref\.\s+Description\s+Qty\.\s+Unit\s+Price\s+Total', line_clean, re.IGNORECASE)):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and summary lines
                if (re.search(r'Pos\.\s+Ref\.|total net|package|Total/EUR|Payment|Delivery|Terms of delivery', line_clean, re.IGNORECASE) or
                    line_clean == 'Kat. Qty. Unit Price Total' or
                    line_clean == 'Qty. Unit Price Total'):
                    continue
                
                # Look for order information
                order_match = re.search(r'your order no\.\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    current_order_info = {
                        'order_no': order_match.group(1),
                        'order_date': order_match.group(2)
                    }
                    continue
                
                # Look for lines that start with position numbers followed by references
                if re.match(r'^\d+\s+\d+', line_clean):  # e.g., "1 8131" or "1 8179"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                    current_block = [line_clean]
                
                # Continue collecting lines for the current item
                elif current_block:
                    # Stop if we hit a new item or summary section
                    if (re.match(r'^\d+\s+\d+', line_clean) or
                        re.search(r'total net|package|Total/EUR|Payment|Delivery|Terms of delivery', line_clean, re.IGNORECASE)):
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d+', line_clean) else []
                    else:
                        current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
            
            # Process each item block
            for block, inv_data, order_info in item_blocks:
                item_data = _parse_kohler_item_block(block, inv_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_kohler_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Kohler invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number (both PROFORMA INVOICE and regular INVOICE)
        inv_match = re.search(r'(?:PROFORMA\s+INVOICE|INVOICE)\s+NO\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'Customer No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.?\s*(\d+)\s*of\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
        
        # Extract valid until date for Proforma invoices
        valid_match = re.search(r'Valid until\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if valid_match:
            # Use valid until date as order date for Proforma invoices if no other date is found
            if not invoice_data['order_date']:
                invoice_data['order_date'] = valid_match.group(1)
    
    return invoice_data

def _parse_kohler_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Kohler invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info.get('order_no', ''),
        'order_date': order_info.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number and reference (remove them since we don't need them)
    pos_match = re.search(r'^(\d+)\s+(\d+)\s+', first_line)
    if pos_match:
        # Remove the position number and reference from the line for easier parsing
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Extract description, quantity, unit price
    # Pattern: "Mouth prop MCKESSON, for adults, large 5 20,49 102,45"
    # or: "ERICH Arch Bar 20 26,00 520,00"
    item_match = re.search(r'^(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['description'] = item_match.group(1).strip()
        item_data['quantity'] = item_match.group(2)
        item_data['unit_price'] = item_match.group(3).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['description']:
        alt_match = re.search(r'^(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['description'] = alt_match.group(1).strip()
            item_data['quantity'] = alt_match.group(2)
            item_data['unit_price'] = alt_match.group(3).replace(',', '.')
    
    # Extract metadata from the entire block
    ref_no = None
    for line in block:
        # Reference number
        ref_match = re.search(r'Ref-No\.:\s*([^\s]+)', line, re.IGNORECASE)
        if ref_match:
            ref_no = ref_match.group(1)
        
        # LST number
        lst_match = re.search(r'LST:\s*([^\s]+)', line, re.IGNORECASE)
        if lst_match:
            lst_no = lst_match.group(1)
            if lst_no and item_data['description']:
                item_data['description'] += f" (LST: {lst_no})"
        
        # Lot number
        lot_match = re.search(r'Lot number\s*(\d+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
    
    # Add reference number to description if found
    if ref_no and item_data['description']:
        item_data['description'] = f"{ref_no} - {item_data['description']}"
        item_data['item_code'] = ref_no  # Use Ref-No as item code
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'Ref-No\.:|LST:|Lot number', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d+', clean_line):  # Don't include lines that start like new items
                    # Check if this line contains additional description (like "- by pairs - black")
                    if re.match(r'^[a-zA-Z\-]', clean_line):  # Starts with a letter or hyphen
                        additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', first_line)
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for numbers that are likely quantities (not prices)
        numbers = re.findall(r'\b(\d+)\b', first_line)
        if len(numbers) >= 2:
            # The number before the prices is likely the quantity
            for i, num in enumerate(numbers):
                if i < len(numbers) - 1 and re.search(r'\d+[,.]\d{2}', first_line.split(num)[-1]):
                    item_data['quantity'] = num
                    break
    
    # Only return if we have at least description and quantity
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Max Hauser OCR needed

#MedChain Supply OCR Needed

#Medin
def extract_medin_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Medin invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_medin_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if 'Ordered Shipped Description Tax Unit Price Amount' in line_clean:
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip empty lines and header repetitions
                if not line_clean or 'Ordered Shipped' in line_clean:
                    continue
                
                # Look for item lines (they start with numbers for ordered/shipped quantities)
                if re.match(r'^\d+\s+\d+\s+[\w-]+\s+-\s+', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Look for customer information lines that belong to the current item
                elif current_block and re.search(r'Customer Order|Customer PO|Customer Part ID', line_clean):
                    current_block.append(line_clean)
                # Stop when we hit summary sections
                elif re.search(r'Terms Summary|Sub Total|Returned Goods Policy', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = []
                    break
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_medin_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_medin_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Medin invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',  # This will be extracted from Customer Part ID
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number - it's on the line after "Invoice"
        if line_clean == 'Invoice' and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.isdigit():  # Invoice number is just digits
                invoice_data['invoice_number'] = next_line
        
        # Extract invoice date - US format M/D/YYYY
        date_match = re.search(r'Invoice Date\s+(\d{1,2}/\d{1,2}/\d{4})', line_clean)
        if date_match and not invoice_data['invoice_date']:
            us_date = date_match.group(1)
            parts = us_date.split('/')
            if len(parts) == 3:
                invoice_data['invoice_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
        
        # Extract customer number from Customer Part ID (e.g., "9394-11")
        part_id_match = re.search(r'Customer Part ID:\s*([^\s]+)', line_clean)
        if part_id_match:
            invoice_data['customer_number'] = part_id_match.group(1)
        
        # Extract order information
        if 'Customer Order' in line_clean:
            # Pattern: "Customer Order SO-126507 Order Date OrderDate"
            order_match = re.search(r'Customer Order\s+([^\s]+)', line_clean)
            if order_match and not invoice_data['order_no']:
                invoice_data['order_no'] = order_match.group(1)
        
        # Extract customer PO
        po_match = re.search(r'Customer PO\s+([^\s]+)', line_clean)
        if po_match and not invoice_data['order_no']:
            invoice_data['order_no'] = po_match.group(1)
        
        # Extract packing slip (delivery note)
        packing_match = re.search(r'Packing Slip\s+([^\s]+)', line_clean)
        if packing_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = packing_match.group(1)
    
    return invoice_data

def _parse_medin_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Medin invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],  # From Customer Part ID
        'order_no': invoice_data.get('order_no', ''),
        'order_date': invoice_data.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line contains the main item data
    first_line = block[0].strip()
    
    # Parse: "1 5 20-1321 - 20.25X13X3.5 UNLIDDED STER TRY 133.0000 665.00"
    # This means: Ordered=1, Shipped=5, ItemCode=20-1321, Description=20.25X13X3.5 UNLIDDED STER TRY, UnitPrice=133.0000, Amount=665.00
    
    item_match = re.search(r'^(\d+)\s+(\d+)\s+([\w-]+)\s+-\s+(.+?)\s+([\d,]+\.\d{4})\s+([\d,]+\.\d{2})$', first_line)
    
    if item_match:
        ordered_qty = item_match.group(1)  # Ordered quantity
        shipped_qty = item_match.group(2)  # Shipped quantity (this is what we use)
        item_data['item_code'] = item_match.group(3)
        item_data['description'] = item_match.group(4).strip()
        item_data['unit_price'] = item_match.group(5).replace(',', '')  # Remove commas
        item_data['quantity'] = shipped_qty  # Use shipped quantity as the actual quantity
        
        # Add ordered quantity to description for reference
        item_data['description'] += f" (Ordered: {ordered_qty}, Shipped: {shipped_qty})"
    
    # If the detailed pattern fails, try a simpler approach
    if not item_data['item_code']:
        # Split by spaces and try to identify components
        parts = first_line.split()
        if len(parts) >= 7:
            # Look for the pattern: number number code-with-dash dash description price price
            for i in range(len(parts) - 3):
                if (parts[i].isdigit() and 
                    parts[i+1].isdigit() and 
                    '-' in parts[i+2] and 
                    parts[i+3] == '-'):
                    # Found the pattern structure
                    item_data['quantity'] = parts[i+1]  # Shipped quantity
                    item_data['item_code'] = parts[i+2]
                    # Description is everything between the dash and the prices
                    desc_start = first_line.find(parts[i+3]) + len(parts[i+3]) + 1
                    # Find where prices start (look for decimal numbers)
                    for j in range(i+4, len(parts)):
                        if '.' in parts[j]:
                            desc_end = first_line.find(parts[j])
                            item_data['description'] = first_line[desc_start:desc_end].strip()
                            # The first price is unit price
                            item_data['unit_price'] = parts[j].replace(',', '')
                            break
                    break
    
    # Extract additional metadata from the block
    customer_part_id = None
    for line in block:
        # Customer Part ID (this is actually the customer number for Medin)
        part_match = re.search(r'Customer Part ID:\s*([^\s]+)', line, re.IGNORECASE)
        if part_match:
            customer_part_id = part_match.group(1)
            # Update customer number if not already set
            if not item_data['customer_number']:
                item_data['customer_number'] = customer_part_id
        
        # Additional order information if not already captured
        order_match = re.search(r'Customer Order\s+([^\s]+)', line, re.IGNORECASE)
        if order_match and not item_data['order_no']:
            item_data['order_no'] = order_match.group(1)
        
        po_match = re.search(r'Customer PO\s+([^\s]+)', line, re.IGNORECASE)
        if po_match and not item_data['order_no']:
            item_data['order_no'] = po_match.group(1)
    
    # Add Customer Part ID to description if different from customer number
    if customer_part_id and item_data['description'] and customer_part_id != item_data['customer_number']:
        item_data['description'] += f" (Part ID: {customer_part_id})"
    
    # Normalize unit price to 2 decimal places
    if item_data['unit_price']:
        try:
            price_float = float(item_data['unit_price'])
            item_data['unit_price'] = f"{price_float:.2f}"
        except ValueError:
            pass
    
    # Only return if we have essential data
    if item_data['item_code'] and item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Microqore
def extract_microqore_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Microqore invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_microqore_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_delivery_info = {'order_no': '', 'order_date': '', 'delivery_note': ''}
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\s+Item\s+No\.\s+Desc\.\s+Quantity\s+each\s+Total', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and empty lines
                if not line_clean or re.search(r'POS\s+Item\s+No\.|EUR\s+EUR', line_clean, re.IGNORECASE):
                    continue
                
                # Look for delivery information - this contains order number and date
                delivery_match = re.search(r'Delivery(\d+)\s*/\s*\d+\s+from\s+(\d{2}\.\d{2}\.\d{4})', line_clean)
                if delivery_match:
                    current_delivery_info['order_no'] = delivery_match.group(1)  # 303861
                    current_delivery_info['order_date'] = delivery_match.group(2)  # 17.09.2024
                    current_delivery_info['delivery_note'] = delivery_match.group(1)  # Use as delivery note too
                    continue
                
                # Look for order information (alternative)
                order_match = re.search(r'Your Order No\.\s*([^\s]+)', line_clean, re.IGNORECASE)
                if order_match:
                    current_delivery_info['order_no'] = order_match.group(1)
                    continue
                
                # Look for item lines (start with numbers followed by MQ4- codes)
                if re.match(r'^\d+\s+MQ4-', line_clean):  # e.g., "10 MQ4-4060-21TC-C"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_delivery_info.copy()))
                    current_block = [line_clean]
                
                # Continue collecting lines for the current item
                elif current_block:
                    # Stop if we hit a new item, delivery info, or summary section
                    if (re.match(r'^\d+\s+MQ4-', line_clean) or
                        re.search(r'Delivery\d+', line_clean) or
                        re.search(r'Line Value|Packing costs|Gross|Steuerfreie', line_clean, re.IGNORECASE)):
                        item_blocks.append((current_block, invoice_data.copy(), current_delivery_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+MQ4-', line_clean) else []
                    else:
                        current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_delivery_info.copy()))
            
            # Process each item block
            for block, inv_data, delivery_info in item_blocks:
                item_data = _parse_microqore_item_block(block, inv_data, delivery_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_microqore_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Microqore invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number and date from the header line
        # Pattern: "20240666 17.09.2024 MW 50103 1"
        header_match = re.search(r'^(\d+)\s+(\d{2}\.\d{2}\.\d{4})\s+\w+\s+(\d+)\s+\d+$', line_clean)
        if header_match:
            if not invoice_data['invoice_number']:
                invoice_data['invoice_number'] = header_match.group(1)
            if not invoice_data['invoice_date']:
                invoice_data['invoice_date'] = header_match.group(2)
            if not invoice_data['customer_number']:
                invoice_data['customer_number'] = header_match.group(3)
        
        # Alternative pattern for invoice number and date
        if not invoice_data['invoice_number']:
            inv_match = re.search(r'INVOICE\s+(\d+)\s+(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
            if inv_match:
                invoice_data['invoice_number'] = inv_match.group(1)
                invoice_data['invoice_date'] = inv_match.group(2)
        
        # Extract customer number
        cust_match = re.search(r'Customer No\.\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
    
    return invoice_data

def _parse_microqore_item_block(block: List[str], invoice_data: Dict, delivery_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Microqore invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': delivery_info.get('order_no', invoice_data.get('order_no', '')),
        'order_date': delivery_info.get('order_date', invoice_data.get('order_date', '')),
        'delivery_note': delivery_info.get('delivery_note', invoice_data.get('delivery_note', '')),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Parse the item line: "10 MQ4-4060-21TC-C castroviejo needle holder, tungsten carbide 15pieces"
    # The unit price is on the next line: "110,75 1.661,25"
    item_match = re.search(r'^(\d+)\s+(MQ4-\S+)\s+(.+?)\s+(\d+)pieces$', first_line)
    
    if item_match:
        item_data['quantity'] = item_match.group(4)  # Quantity from "15pieces"
        item_data['item_code'] = item_match.group(2)
        item_data['description'] = item_match.group(3).strip()
    
    # If the first pattern fails, try a more flexible approach
    if not item_data['item_code']:
        parts = first_line.split()
        if len(parts) >= 3:
            # Look for MQ4- pattern
            for i, part in enumerate(parts):
                if part.startswith('MQ4-') and i > 0 and i + 1 < len(parts):
                    # Previous part should be the first number, look for "pieces"
                    if parts[i-1].isdigit():
                        # Find where "pieces" appears
                        for j in range(i+1, len(parts)):
                            if 'pieces' in parts[j]:
                                # Extract quantity from the pieces word
                                qty_match = re.search(r'(\d+)pieces', parts[j])
                                if qty_match:
                                    item_data['quantity'] = qty_match.group(1)
                                # Description is everything between MQ4 code and pieces
                                desc_start = first_line.find(part) + len(part) + 1
                                desc_end = first_line.find(parts[j])
                                item_data['description'] = first_line[desc_start:desc_end].strip()
                                item_data['item_code'] = part
                                break
                        break
    
    # Look for unit price in the next line(s)
    for i in range(1, len(block)):
        line = block[i].strip()
        # Look for price pattern: "110,75 1.661,25"
        price_match = re.search(r'^([\d,]+)\s+[\d,\.]+$', line)
        if price_match:
            item_data['unit_price'] = price_match.group(1).replace(',', '.')
            break
    
    # If still no unit price found, check the first line again
    if not item_data['unit_price']:
        # Maybe the prices are on the same line
        price_match = re.search(r'(\d+)pieces\s+([\d,]+)\s+[\d,\.]+', first_line)
        if price_match:
            item_data['quantity'] = price_match.group(1)
            item_data['unit_price'] = price_match.group(2).replace(',', '.')
    
    # Extract metadata from the entire block
    drawing_no = None
    for line in block:
        # Drawing number
        drawing_match = re.search(r'Drawing\s+([^\s]+)', line, re.IGNORECASE)
        if drawing_match:
            drawing_no = drawing_match.group(1)
        
        # Lot information
        lot_match = re.search(r'Lot(\d+)\s+Lot-Code(\w+)', line, re.IGNORECASE)
        if lot_match:
            lot_number = lot_match.group(1)
            lot_code = lot_match.group(2)
            item_data['lot'] = f"{lot_number}-{lot_code}"
        
        # Alternative lot pattern
        if not item_data['lot']:
            alt_lot_match = re.search(r'(\d+)\s+x\s+Lot(\d+)\s+Lot-Code(\w+)', line, re.IGNORECASE)
            if alt_lot_match:
                lot_qty = alt_lot_match.group(1)
                lot_number = alt_lot_match.group(2)
                lot_code = alt_lot_match.group(3)
                item_data['lot'] = f"{lot_number}-{lot_code}"
                # Add lot quantity to description
                if item_data['description']:
                    item_data['description'] += f" (Lot Qty: {lot_qty})"
        
        # Customer reference numbers (like G4355-31, C6638-39)
        ref_match = re.search(r'\(([A-Z]\d+-\d+)\)', line)
        if ref_match:
            ref_no = ref_match.group(1)
            if ref_no and item_data['description']:
                item_data['description'] += f" (Ref: {ref_no})"
    
    # Add drawing number to description if found
    if drawing_no and item_data['description']:
        item_data['description'] += f" (Drawing: {drawing_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that contain prices or metadata
            if (line and 
                not re.search(r'^\d+[,.]\d+\s+[\d,\.]+$', line) and  # Not a price line
                not re.search(r'Drawing|Lot|Delivery|Line Value', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+MQ4-', line) and
                re.match(r'^[a-zA-Z]', line)):  # Starts with a letter
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data
    if item_data['description'] and item_data['quantity'] and item_data['unit_price']:
        return item_data
    
    return None

#NDC OCR Needed

#Otto Ruttgers
def extract_otto_ruttgers_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Otto Ruttgers invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_otto_ruttgers_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_info = {'order_no': '', 'order_date': ''}
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\.ARTICLE\s+description\s+your order no\.\s+qty\.\s+each\s+price', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and summary lines
                if (re.search(r'POS\.ARTICLE|carry-over|total net|package|freight|total/EUR', line_clean, re.IGNORECASE) or
                    line_clean == 'description your order no. qty. each price'):
                    continue
                
                # Look for order information
                order_match = re.search(r'your order no\.\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    current_order_info = {
                        'order_no': order_match.group(1),
                        'order_date': order_match.group(2)
                    }
                    # Start a new block for this order
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                    current_block = []
                    continue
                
                # Look for customer article number
                art_match = re.search(r'your art\.-no\.:\s*([^\s;]+)', line_clean, re.IGNORECASE)
                if art_match and current_block:
                    # This continues the current item block
                    current_block.append(line_clean)
                    continue
                
                # Look for lines that start with position numbers followed by item codes
                if re.match(r'^\d+\s+[A-Z]', line_clean):  # e.g., "1 HMIMCU-3K" or "1 HBPMCU-1015/3LRSurg"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                    current_block = [line_clean]
                
                # Look for lines that might be continuation of item descriptions (start with item codes)
                elif re.match(r'^[A-Z][\w/-]+\s+', line_clean) and current_block:
                    # This might be a continuation line for the current item
                    current_block.append(line_clean)
                
                # Continue collecting lines for the current item (description continuations, LOT info, etc.)
                elif current_block and line_clean:
                    # Stop if we hit a new item or summary section
                    if (re.match(r'^\d+\s+[A-Z]', line_clean) or
                        re.search(r'carry-over|total net|package|freight|total/EUR', line_clean, re.IGNORECASE)):
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+[A-Z]', line_clean) else []
                    else:
                        # Only add if it looks like description continuation or metadata
                        if (re.match(r'^[a-zA-Z]', line_clean) or  # Starts with letter
                            re.search(r'LOT\s*\d+', line_clean, re.IGNORECASE) or  # Lot information
                            re.search(r'your art\.-no\.:', line_clean, re.IGNORECASE)):  # Article number
                            current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
            
            # Process each item block
            for block, inv_data, order_info in item_blocks:
                item_data = _parse_otto_ruttgers_item_block(block, inv_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _parse_otto_ruttgers_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Otto Ruttgers invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info.get('order_no', invoice_data.get('order_no', '')),
        'order_date': order_info.get('order_date', invoice_data.get('order_date', '')),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Try multiple patterns to handle different formats
    
    # Pattern 1: Standard format "HMIMCU-3K Surgical Scalpelhandle for mini 16186 200 St. 7,12 1.424,00"
    item_match = re.search(r'^([A-Z][\w/-]+)\s+(.+?)\s+(\d+)\s+([^\s]+)\s+([\d,]+)\s+([\d,\.]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(5).replace(',', '.')
    
    # Pattern 2: Format with order number in description "HBPMCU-1015/3LRSurg. Scalpel handle EN 27740 No. 4200987135 300 pcs. 7,44 2.232,00"
    if not item_data['item_code']:
        alt_match = re.search(r'^([A-Z][\w/-]+)\s+(.+?)\s+No\.\s*\d+\s+(\d+)\s+([^\s]+)\s+([\d,]+)\s+([\d,\.]+)$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(5).replace(',', '.')
    
    # Pattern 3: More flexible pattern
    if not item_data['item_code']:
        flex_match = re.search(r'^([A-Z][\w/-]+)\s+(.+?)\s+(\d+)\s+([^\s]+)\s+([\d,]+)', first_line)
        if flex_match:
            item_data['item_code'] = flex_match.group(1).strip()
            item_data['description'] = flex_match.group(2).strip()
            item_data['quantity'] = flex_match.group(3)
            item_data['unit_price'] = flex_match.group(5).replace(',', '.')
    
    # Pattern 4: Even more flexible - just look for item code and prices
    if not item_data['item_code']:
        # Find the item code (starts with capital letter, contains letters/numbers/dashes/slashes)
        code_match = re.search(r'([A-Z][\w/-]+)', first_line)
        if code_match:
            item_data['item_code'] = code_match.group(1)
            # Try to find quantity and price
            prices = re.findall(r'([\d,]+\.?\d{0,2})', first_line)
            if len(prices) >= 2:
                item_data['unit_price'] = prices[-2].replace(',', '.')  # Second last is unit price
            # Find quantity (number before pcs., St., etc.)
            qty_match = re.search(r'(\d+)\s+(pcs\.|St\.)', first_line, re.IGNORECASE)
            if qty_match:
                item_data['quantity'] = qty_match.group(1)
            # Description is everything between item code and quantity/price
            code_pos = first_line.find(item_data['item_code']) + len(item_data['item_code'])
            if item_data['quantity']:
                qty_pos = first_line.find(item_data['quantity'])
                item_data['description'] = first_line[code_pos:qty_pos].strip()
            else:
                # If no quantity found, take everything after code until prices
                price_pos = first_line.find(prices[0]) if prices else len(first_line)
                item_data['description'] = first_line[code_pos:price_pos].strip()
    
    # Extract metadata from the entire block
    customer_art_no = None
    for line in block:
        # Customer article number
        art_match = re.search(r'your art\.-no\.:\s*([^\s;]+)', line, re.IGNORECASE)
        if art_match:
            customer_art_no = art_match.group(1)
        
        # Lot number
        lot_match = re.search(r'LOT\s*([^;]+);', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1).strip()
    
    # Add customer article number to description if found
    if customer_art_no and item_data['description']:
        item_data['description'] += f" (Art-No: {customer_art_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Only include lines that don't look like metadata or new items
            if (line and 
                not re.search(r'your art\.-no\.:|LOT\s*[^;]+;', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+[A-Z]', line) and
                re.match(r'^[a-zA-Z\d]', line)):  # Starts with letter or number
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', ' '.join(block))
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for quantity pattern with unit (St., pcs., etc.)
        qty_match = re.search(r'(\d+)\s+(pcs\.|St\.)', ' '.join(block), re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
        else:
            # Just look for a number that could be quantity
            numbers = re.findall(r'\b(\d+)\b', first_line)
            if len(numbers) >= 2:
                item_data['quantity'] = numbers[1]  # Second number is often quantity
    
    # Only return if we have essential data
    if item_data['item_code'] and item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

def _extract_otto_ruttgers_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Otto Ruttgers invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number, customer number, and date from header line
        # Pattern: "240268 48515 26.03.2024 1"
        header_match = re.search(r'^(\d+)\s+(\d+)\s+(\d{2}\.\d{2}\.\d{4})\s+\d+$', line_clean)
        if header_match:
            if not invoice_data['invoice_number']:
                invoice_data['invoice_number'] = header_match.group(1)
            if not invoice_data['customer_number']:
                invoice_data['customer_number'] = header_match.group(2)
            if not invoice_data['invoice_date']:
                invoice_data['invoice_date'] = header_match.group(3)
        
        # Alternative pattern for invoice number
        inv_match = re.search(r'INVOICE NO\.\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Alternative pattern for customer number
        cust_match = re.search(r'Cust\.-No\.\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Alternative pattern for date
        date_match = re.search(r'Date\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.\s*(\d+)\s*at\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
    
    return invoice_data


#Phoenix Instruments
def extract_phoenix_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Phoenix Instruments invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_phoenix_invoice_info(lines)
            
            # Find item blocks - Phoenix has a specific 2-line per item structure
            item_blocks = []
            current_item_lines = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if 'Item Number Alias item Description Ordered Shipped Back Ordered Price Amount' in line_clean:
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and summary lines
                if (re.search(r'Item Number|Net Invoice|Less Discount|Freight|Tax|Tracking number|Invoice Total', line_clean, re.IGNORECASE) or
                    'Continued' in line_clean):
                    continue
                
                # Look for item number lines (start with numbers or P followed by numbers-dash-numbers)
                if re.match(r'^(\d+-\d+|[A-Z]\d+-\d+)', line_clean) and not re.search(r'Whse:', line_clean):
                    # If we have a complete item (2 lines), save it
                    if len(current_item_lines) == 2:
                        item_blocks.append((current_item_lines, invoice_data.copy()))
                    current_item_lines = [line_clean]
                # Look for alias item lines (they contain Whse: information)
                elif current_item_lines and re.search(r'Whse:', line_clean):
                    current_item_lines.append(line_clean)
                    # This completes the item block
                    item_blocks.append((current_item_lines, invoice_data.copy()))
                    current_item_lines = []
                # Stop if we hit summary section
                elif re.search(r'Net Invoice|Less Discount|Freight|Tax|Tracking number|Invoice Total', line_clean, re.IGNORECASE):
                    if current_item_lines:
                        item_blocks.append((current_item_lines, invoice_data.copy()))
                    break
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_phoenix_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_phoenix_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Phoenix Instruments invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number (remove -IN suffix)
        inv_match = re.search(r'Invoice Number:\s*([^\s]+)', line_clean)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1).replace('-IN', '')
        
        # Extract invoice date (US format: M/D/YYYY)
        date_match = re.search(r'Invoice Date:\s*(\d{1,2}/\d{1,2}/\d{4})', line_clean)
        if date_match and not invoice_data['invoice_date']:
            us_date = date_match.group(1)
            parts = us_date.split('/')
            if len(parts) == 3:
                invoice_data['invoice_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
        
        # Extract customer number
        cust_match = re.search(r'Customer Number:\s*([^\s]+)', line_clean)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract order number
        order_match = re.search(r'Order Number:\s*([^\s]+)', line_clean)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
        
        # Extract order date (US format: M/D/YYYY)
        order_date_match = re.search(r'Order Date\s*(\d{1,2}/\d{1,2}/\d{4})', line_clean)
        if order_date_match and not invoice_data['order_date']:
            us_date = order_date_match.group(1)
            parts = us_date.split('/')
            if len(parts) == 3:
                invoice_data['order_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
        
        # Extract customer PO (delivery note)
        po_match = re.search(r'Customer P\.O\.\s*(\d+)', line_clean)
        if po_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = po_match.group(1)
    
    return invoice_data

def _parse_phoenix_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Phoenix Instruments invoice"""
    if not block or len(block) < 2:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data.get('order_no', ''),
        'order_date': invoice_data.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # Line 1: "106-5324 5.00 0.00 5.00 18.69 0.00"
    first_line = block[0].strip()
    
    # Line 2: "G1764-35 Whse: 000"
    second_line = block[1].strip()
    
    # Parse first line - extract item number, quantities, and prices
    first_parts = first_line.split()
    if len(first_parts) >= 6:
        item_data['item_code'] = first_parts[0]  # e.g., "106-5324"
        
        # Use Shipped quantity (second number) - this is what was actually sent
        shipped_qty = first_parts[1]  # "0.00" or "1.00" etc.
        ordered_qty = first_parts[0] if first_parts[0].replace('-', '').isdigit() else first_parts[2]
        back_ordered_qty = first_parts[3] if len(first_parts) > 3 else "0.00"
        
        # Use shipped quantity if available, otherwise use ordered quantity
        if shipped_qty != '0.00':
            item_data['quantity'] = shipped_qty
        else:
            item_data['quantity'] = ordered_qty
        
        item_data['unit_price'] = first_parts[4]  # e.g., "18.69"
    
    # Parse second line - extract alias item and warehouse
    second_parts = second_line.split()
    if second_parts:
        alias_item = second_parts[0]  # e.g., "G1764-35"
        
        # Use alias item as the description
        item_data['description'] = alias_item
        
        # Extract warehouse as lot number
        whse_match = re.search(r'Whse:\s*(\d+)', second_line)
        if whse_match:
            item_data['lot'] = f"Whse:{whse_match.group(1)}"
    
    # For items with additional description in the second line
    if len(second_parts) > 2:
        # There might be additional description text before "Whse:"
        desc_text = ' '.join(second_parts[1:-2])  # Skip first (alias) and last parts (Whse: 000)
        if desc_text and desc_text != 'Whse:':
            item_data['description'] = f"{alias_item} - {desc_text}"
    
    # Only return items with non-zero quantities
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0.00'):
        return item_data
    
    return None


#Precision Medical
def extract_precision_medical_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Precision Medical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_precision_medical_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section (table header)
                if re.search(r'QTY\s+QTY\s+BACK\s+PMM PN\s*/\s*DESCRIPTION\s+UNIT\s+TOTAL', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                if re.search(r'Ordered\s+Shipped\s+Order\s+Customer PN\s+PRICE', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and summary lines
                if (re.search(r'QTY\s+QTY\s+BACK|Ordered\s+Shipped|SUBTOTAL|EXCISE TAX|HANDLING FEE|TOTAL', line_clean, re.IGNORECASE) or
                    'THANK YOU FOR YOUR ORDER!' in line_clean):
                    continue
                
                # Look for item lines (they contain quantities and prices)
                if re.match(r'^\d+\s+EA\s+\d+\s+-\s+', line_clean):  # e.g., "2 EA 2 - 5096-10/UR6107-21"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Look for DATE CODE lines that belong to the current item
                elif current_block and re.match(r'DATE CODE:', line_clean, re.IGNORECASE):
                    current_block.append(line_clean)
                # Stop if we hit summary section
                elif re.search(r'SUBTOTAL|EXCISE TAX|HANDLING FEE|TOTAL', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = []
                    break
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_precision_medical_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_precision_medical_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Precision Medical invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'INVOICE Number:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date (Month DD, YYYY format)
        date_match = re.search(r'Date:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            # Convert "October 29, 2024" to "29.10.2024"
            us_date = date_match.group(1)
            try:
                from datetime import datetime
                dt = datetime.strptime(us_date, '%B %d, %Y')
                invoice_data['invoice_date'] = dt.strftime('%d.%m.%Y')
            except ValueError:
                # Fallback: try different format
                try:
                    dt = datetime.strptime(us_date, '%b %d, %Y')
                    invoice_data['invoice_date'] = dt.strftime('%d.%m.%Y')
                except ValueError:
                    # Keep original format if conversion fails
                    invoice_data['invoice_date'] = us_date
        
        # Extract order number
        order_match = re.search(r'ORDER NO\.\s*(\d+)', line_clean, re.IGNORECASE)
        if order_match and not invoice_data['order_no']:
            invoice_data['order_no'] = order_match.group(1)
            invoice_data['delivery_note'] = order_match.group(1)  # Use order number as delivery note
        
        # Extract ship date (US format: MM/DD/YYYY)
        ship_date_match = re.search(r'SHIP DATE\s*(\d{1,2}/\d{1,2}/\d{4})', line_clean, re.IGNORECASE)
        if ship_date_match and not invoice_data['order_date']:
            us_date = ship_date_match.group(1)
            parts = us_date.split('/')
            if len(parts) == 3:
                invoice_data['order_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
        
        # Extract customer number (from the number below ORDER NO.)
        # Pattern: "340-070-917" appears below the order information
        cust_match = re.search(r'^\d{3}-\d{3}-\d{3}$', line_clean)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(0)
    
    return invoice_data

def _parse_precision_medical_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Precision Medical invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data.get('order_no', ''),
        'order_date': invoice_data.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line contains the main item data
    first_line = block[0].strip()
    
    # Parse: "2 EA 2 - 5096-10/UR6107-21 Fansler Operating Speculum, Slotted Tube, 1-3/8" DIA, 2-3/8" LONG $110.00 $220.00"
    item_match = re.search(r'^(\d+)\s+EA\s+(\d+)\s+-\s+([^\s]+)\s+(.+?)\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})$', first_line)
    
    if item_match:
        ordered_qty = item_match.group(1)  # Ordered quantity
        shipped_qty = item_match.group(2)  # Shipped quantity
        item_data['item_code'] = item_match.group(3)  # e.g., "5096-10/UR6107-21"
        item_data['description'] = item_match.group(4).strip()  # Description
        item_data['unit_price'] = item_match.group(5).replace(',', '')  # Unit price
        item_data['quantity'] = shipped_qty  # Use shipped quantity
        
        # Add ordered quantity to description for reference
        item_data['description'] = f"{item_data['item_code']} - {item_data['description']} (Ordered: {ordered_qty}, Shipped: {shipped_qty})"
    
    # Alternative pattern if the first one fails
    if not item_data['item_code']:
        # Try a simpler approach - split and analyze
        parts = first_line.split()
        if len(parts) >= 7:
            # Look for the pattern: number EA number - code description $price $total
            for i in range(len(parts) - 4):
                if (parts[i].isdigit() and 
                    parts[i+1] == 'EA' and 
                    parts[i+2].isdigit() and 
                    parts[i+3] == '-'):
                    item_data['quantity'] = parts[i+2]  # Shipped quantity
                    item_data['item_code'] = parts[i+4]  # Item code
                    
                    # Find the description (everything between code and $)
                    desc_start = first_line.find(parts[i+4]) + len(parts[i+4]) + 1
                    # Find where prices start
                    dollar_pos = first_line.find('$', desc_start)
                    if dollar_pos != -1:
                        item_data['description'] = first_line[desc_start:dollar_pos].strip()
                    
                    # Find prices
                    prices = re.findall(r'\$([\d,]+\.\d{2})', first_line)
                    if prices:
                        item_data['unit_price'] = prices[0].replace(',', '')
                    
                    break
    
    # Extract date code from the block
    for line in block:
        date_code_match = re.search(r'DATE CODE:\s*([^\s]+)', line, re.IGNORECASE)
        if date_code_match:
            item_data['lot'] = f"DateCode:{date_code_match.group(1)}"
            break
    
    # Only return if we have essential data
    if item_data['item_code'] and item_data['description'] and item_data['quantity']:
        return item_data
    
    return None

#Rebstock
def extract_rebstock_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Rebstock invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_rebstock_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_info = {'order_no': '', 'order_date': ''}
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\s+ARTICLE\s+DESCRIPTION\s+QTY\.\s+UNIT\s+TOTAL', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and summary lines
                if (re.search(r'POS\s+ARTICLE|TOTAL/EUR|Payment terms|Delivery terms|Shipment', line_clean, re.IGNORECASE) or
                    line_clean == 'DESCRIPTION QTY. UNIT TOTAL'):
                    continue
                
                # Look for order information
                order_match = re.search(r'Your order no\.\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    current_order_info = {
                        'order_no': order_match.group(1),
                        'order_date': order_match.group(2)
                    }
                    continue
                
                # Look for lines that start with position numbers followed by item codes
                if re.match(r'^\d+\s+\d{2}-\d{2}-\d{3}', line_clean):  # e.g., "1 06-06-917"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                    current_block = [line_clean]
                
                # Continue collecting lines for the current item
                elif current_block:
                    # Stop if we hit a new item or summary section
                    if (re.match(r'^\d+\s+\d{2}-\d{2}-\d{3}', line_clean) or
                        re.search(r'TOTAL/EUR|Payment terms|Delivery terms', line_clean, re.IGNORECASE)):
                        item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
                        current_block = [line_clean] if re.match(r'^\d+\s+\d{2}-\d{2}-\d{3}', line_clean) else []
                    else:
                        current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_info.copy()))
            
            # Process each item block
            for block, inv_data, order_info in item_blocks:
                item_data = _parse_rebstock_item_block(block, inv_data, order_info, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_rebstock_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Rebstock invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number
        inv_match = re.search(r'COMMERCIAL INVOICE\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'DATE\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number
        cust_match = re.search(r'CUST\.-NO\.\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract delivery note
        delivery_match = re.search(r'Delivery Note No\.\s*(\d+)\s*of\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
    
    return invoice_data

def _parse_rebstock_item_block(block: List[str], invoice_data: Dict, order_info: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Rebstock invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_info.get('order_no', invoice_data.get('order_no', '')),
        'order_date': order_info.get('order_date', invoice_data.get('order_date', '')),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line should contain the main item data
    first_line = block[0].strip()
    
    # Extract position number (remove it since we don't need it)
    pos_match = re.search(r'^(\d+)\s+', first_line)
    if pos_match:
        first_line = first_line[len(pos_match.group(0)):].strip()
    
    # Parse the item line: "06-06-917 CASPAR vertebral body dissector 205 mm 1 pcs. 89,90 89,90"
    item_match = re.search(r'^(\d{2}-\d{2}-\d{3})\s+(.+?)\s+(\d+)\s+pcs\.\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()
        item_data['description'] = item_match.group(2).strip()
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d{2}-\d{2}-\d{3})\s+(.+?)\s+(\d+)\s+pcs\.\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract metadata from the entire block
    customer_art_no = None
    lst_no = None
    for line in block:
        # Customer article number
        art_match = re.search(r'your art\.-no\.:\s*([^\s]+)', line, re.IGNORECASE)
        if art_match:
            customer_art_no = art_match.group(1)
        
        # LST number
        lst_match = re.search(r'LST No\.:\s*([^\s]+)', line, re.IGNORECASE)
        if lst_match:
            lst_no = lst_match.group(1)
        
        # Lot number
        lot_match = re.search(r'Lot No\.\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
    
    # Add customer article number to description if found
    if customer_art_no and item_data['description']:
        item_data['description'] += f" (Art-No: {customer_art_no})"
    
    # Add LST number to description if found
    if lst_no and item_data['description']:
        item_data['description'] += f" (LST: {lst_no})"
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for line in block[1:]:
            # Only include lines that don't look like metadata
            if not re.search(r'your art\.-no\.:|LST No\.:|Lot No\.', line, re.IGNORECASE):
                clean_line = line.strip()
                if clean_line and not re.match(r'^\d+\s+\d{2}-\d{2}-\d{3}', clean_line):  # Don't include lines that start like new items
                    # Check if this line contains additional description
                    if re.match(r'^[a-zA-Z]', clean_line):  # Starts with a letter
                        additional_desc.append(clean_line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+[,.]\d{2})\b', first_line)
        if len(prices) >= 2:  # Usually there are two prices: unit price and total
            item_data['unit_price'] = prices[0].replace(',', '.')  # First price is unit price
    
    # Extract quantity from alternative patterns if still missing
    if not item_data['quantity']:
        # Look for quantity pattern with "pcs."
        qty_match = re.search(r'(\d+)\s+pcs\.', first_line, re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    # Only return if we have essential data
    if item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Rica
def extract_rica_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Rica Surgical invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_rica_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section (table header)
                if re.search(r'Quantity\s+B/O\s+Item Code\s+Description\s+Price Each\s+Amount', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and summary lines
                if (re.search(r'Quantity\s+B/O|UPS Package|Sales Tax|Total USD', line_clean, re.IGNORECASE) or
                    'Phone # Fax # Web Site' in line_clean):
                    continue
                
                # Look for item lines (they contain quantities and item codes)
                if re.match(r'^\d+\s+\d+\s+[A-Z]', line_clean):  # e.g., "20 0 WSR-6"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean and not re.match(r'^\d', line_clean):
                    # Stop if we hit a new section
                    if re.search(r'UPS Package|Sales Tax|Total USD', line_clean, re.IGNORECASE):
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                        break
                    else:
                        current_block.append(line_clean)
                # Stop if we hit summary section
                elif re.search(r'UPS Package|Sales Tax|Total USD', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = []
                    break
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_rica_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_rica_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Rica Surgical invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'order_date': '',
        'delivery_note': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number and date from header
        # Pattern: "09/20/2024 110669"
        header_match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d+)', line_clean)
        if header_match:
            if not invoice_data['invoice_date']:
                # Convert US date format to European format DD.MM.YYYY
                us_date = header_match.group(1)
                parts = us_date.split('/')
                if len(parts) == 3:
                    invoice_data['invoice_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
            if not invoice_data['invoice_number']:
                invoice_data['invoice_number'] = header_match.group(2)
        
        # Extract order number
        ord_match = re.search(r'Ord Number\s+(\d+)', line_clean, re.IGNORECASE)
        if ord_match and not invoice_data['order_no']:
            invoice_data['order_no'] = ord_match.group(1)
        
        # Extract P.O. Number (delivery note)
        po_match = re.search(r'P\.O\. Number\s+([^\s]+)', line_clean, re.IGNORECASE)
        if po_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = po_match.group(1)
            invoice_data['order_no'] = po_match.group(1)  # Also use as order number
        
        # Extract tracking number as alternative delivery note
        tracking_match = re.search(r'Tracking #:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if tracking_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = tracking_match.group(1)
    
    return invoice_data

def _parse_rica_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Rica Surgical invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data.get('order_no', ''),
        'order_date': invoice_data.get('order_date', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot': '',
        'page': page_num + 1
    }
    
    # The first line contains the main item data
    first_line = block[0].strip()
    
    # Parse: "20 0 WSR-6 WEINSTEIN RACK STRINGER 6" LONG 2.75" WIDE 10.32 206.40"
    item_match = re.search(r'^(\d+)\s+\d+\s+([^\s]+)\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$', first_line)
    
    if item_match:
        item_data['quantity'] = item_match.group(1)
        item_data['item_code'] = item_match.group(2)  # e.g., "WSR-6"
        item_data['description'] = item_match.group(3).strip()
        item_data['unit_price'] = item_match.group(4)  # e.g., "10.32"
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^(\d+)\s+\d+\s+([^\s]+)\s+(.+?)\s+([\d,]+\.\d{2})', first_line)
        if alt_match:
            item_data['quantity'] = alt_match.group(1)
            item_data['item_code'] = alt_match.group(2)
            item_data['description'] = alt_match.group(3).strip()
            item_data['unit_price'] = alt_match.group(4)
    
    # If still no match, try a more flexible approach
    if not item_data['item_code']:
        parts = first_line.split()
        if len(parts) >= 5:
            # Look for the pattern: number number code description price price
            for i in range(2, len(parts) - 2):
                if re.match(r'^[A-Z]-', parts[i]) or re.match(r'^[A-Z]{2,}', parts[i]):  # Item code pattern
                    item_data['quantity'] = parts[0]
                    item_data['item_code'] = parts[i]
                    
                    # Description is everything between code and prices
                    code_pos = first_line.find(parts[i]) + len(parts[i])
                    # Find prices (look for decimal numbers)
                    prices = []
                    for j in range(i+1, len(parts)):
                        if re.match(r'^\d+\.\d{2}$', parts[j]):
                            prices.append(parts[j])
                    
                    if prices:
                        price_pos = first_line.find(prices[0])
                        item_data['description'] = first_line[code_pos:price_pos].strip()
                        item_data['unit_price'] = prices[0]
                    break
    
    # Extract lot number from the block
    for line in block:
        lot_match = re.search(r'LOT#\s*([^\s]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot']:
            item_data['lot'] = lot_match.group(1)
    
    # For multi-line descriptions, combine them
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that contain lot numbers or look like new items
            if (line and 
                not re.search(r'LOT#', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+\d+\s+[A-Z]', line) and
                not re.search(r'UPS Package|Sales Tax|Total USD', line, re.IGNORECASE)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Extract unit price from alternative patterns if still missing
    if not item_data['unit_price']:
        prices = re.findall(r'\b(\d+\.\d{2})\b', first_line)
        if prices:
            item_data['unit_price'] = prices[0]  # First price is unit price
    
    # Only return if we have essential data and non-zero quantity
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None

#Rominger Invoice not available 

#Rudischhauser
def extract_rudischhauser_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Rudischhauser invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_rudischhauser_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_po = ""
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'pos\s+item\s+description\s+quantity.*€.*each.*€.*total',
                             line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header/summary lines
                if (re.search(r'pos\s+item|Total net|Total amount|Packaging|Carry-over',
                              line_clean, re.IGNORECASE) or
                    'Rudischhauser Surgical' in line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_po))
                        current_block = []
                    continue
                
                # Look for PO number lines
                po_match = re.search(r'Your P\.O\. no\.\s+([^\s-]+)', line_clean, re.IGNORECASE)
                if po_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_po))
                    current_po = po_match.group(1)
                    current_block = []
                    continue
                
                # Look for item lines (allow multiple letters in code)
                if re.match(r'^\d+\s+[A-Z]+.*\d', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_po))
                    current_block = [line_clean]
                # Continue collecting description lines
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_po))
            
            # Process each item block
            for block, inv_data, po_no in item_blocks:
                item_data = _parse_rudischhauser_item_block(block, inv_data, po_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _parse_rudischhauser_item_block(block: List[str], invoice_data: Dict, po_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Rudischhauser invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': po_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot_number': '',
        'page': page_num + 1
    }
    
    # Parse first line for item code
    first_line = block[0].strip()
    first_parts = first_line.split()
    if len(first_parts) >= 3:
        item_data['item_code'] = " ".join(first_parts[1:])
    
    # Look for description + pcs + €
    for line in block:
        line_clean = line.strip()
        desc_match = re.search(
            r'(.+?)\s+(\d+)\s+pcs\.\s+([\d,]+)\s*€',
            line_clean
        )
        if desc_match:
            item_data['description'] = desc_match.group(1).strip()
            item_data['quantity'] = desc_match.group(2)
            item_data['unit_price'] = desc_match.group(3).replace(',', '.')
            break
    
    # If still missing description, try fallback
    if not item_data['description']:
        for line in block:
            if 'pcs.' in line:
                parts = line.split()
                for j, part in enumerate(parts):
                    if part == 'pcs.' and j >= 2:
                        item_data['description'] = ' '.join(parts[:j-1])
                        item_data['quantity'] = parts[j-1]
                        price_parts = parts[j+1:]
                        prices = [p.replace(',', '.') for p in price_parts if re.match(r'^\d+,\d{2}$', p)]
                        if prices:
                            item_data['unit_price'] = prices[0]
                        break
    
    # Extract lot number
    for line in block:
        lot_match = re.search(r'Lot number\s*([^/\n]+)', line, re.IGNORECASE)
        if lot_match:
            item_data['lot_number'] = lot_match.group(1).strip()
            break
    
    # Additional description lines
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            if (line and 
                not re.search(r'pcs\.|[\d,]+\s*€|Lot number|^\d+\s+[A-Z]', line) and
                line != item_data['description']):
                additional_desc.append(line)
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None

def _extract_rudischhauser_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Rudischhauser invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'supplier_no': '',
        'dev_no': '',
        'our_reference': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "Novo Surgical Inc. INVOICE : 9240991"
        inv_match = re.search(r'INVOICE\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract customer number: "Customer No. : 11406"
        cust_match = re.search(r'Customer No\.\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract invoice date: "Date : 18.09.2024"
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract supplier number: "supplier no. : 02-2500029"
        supp_match = re.search(r'supplier no\.\s*:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if supp_match:
            invoice_data['supplier_no'] = supp_match.group(1)
        
        # Extract DEV number: "DEV: 8010300"
        dev_match = re.search(r'DEV:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if dev_match:
            invoice_data['dev_no'] = dev_match.group(1)
        
        # Extract our reference: "Our reference : WT"
        ref_match = re.search(r'Our reference\s*:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if ref_match:
            invoice_data['our_reference'] = ref_match.group(1)
    
    return invoice_data


#Rudolf Storz
def extract_rudolfstorz_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Rudolf Storz invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_rudolfstorz_invoice_info(lines)
            
            item_blocks = []
            current_block = []
            in_items_section = False
            current_po = ""
            
            for line in lines:
                line_clean = line.strip()
                
                # Detect item header
                if re.search(r'POS\s+ARTICLE\s+description\s+qty.*EUR', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip carry-over and totals
                if re.search(r'carry-over|total net|total/EUR|package', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_po))
                        current_block = []
                    continue
                
                # Detect "your order no."
                po_match = re.search(r'your order no\.\s*([^\s-]+)', line_clean, re.IGNORECASE)
                if po_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_po))
                    current_po = po_match.group(1)
                    current_block = []
                    continue
                
                # Detect item line (starts with pos number)
                if re.match(r'^\d+\s+\S+', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_po))
                    current_block = [line_clean]
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_po))
            
            # Process each block
            for block, inv_data, po_no in item_blocks:
                item_data = _parse_rudolfstorz_item_block(block, inv_data, po_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_rudolfstorz_invoice_info(lines: List[str]) -> Dict:
    """Extract invoice-level metadata from Rudolf Storz invoice."""
    invoice_data = {
        'invoice_date': '',
        'invoice_number': '',
        'customer_number': ''
    }
    
    for i, line in enumerate(lines):
        # Invoice number + date
        inv_match = re.search(r'INVOICE\s+(\d+)\s+Date\s+(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if inv_match:
            invoice_data['invoice_number'] = inv_match.group(1)
            invoice_data['invoice_date'] = inv_match.group(2)
        
        # Customer number may be on the following line after "Cust.-No."
        if "Cust.-No." in line and i + 1 < len(lines):
            next_line = lines[i + 1]
            # Preferred pattern: "PM 12214"
            cust_match = re.search(r'PM\s+(\d+)', next_line, re.IGNORECASE)
            if cust_match:
                invoice_data['customer_number'] = cust_match.group(1)
            else:
                # Fallback: last number on the line
                fallback_match = re.search(r'(\d+)(?=\s*page:)', next_line, re.IGNORECASE)
                if fallback_match:
                    invoice_data['customer_number'] = fallback_match.group(1)
    
    return invoice_data

def _parse_rudolfstorz_item_block(block: List[str], invoice_data: Dict, po_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Rudolf Storz invoice."""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': po_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot_number': '',
        'page': page_num + 1
    }
    
    first_line = block[0].strip()
    parts = first_line.split()
    if len(parts) >= 6:
        # Example: "1 558001 Cooley Atrial Valve Retractors 1 pcs. 80,55 80,55"
        item_data['item_code'] = parts[1]
        item_data['description'] = " ".join(parts[2:-4])  # everything until qty
        item_data['quantity'] = parts[-4]  # numeric qty (e.g., "1")
        item_data['unit_price'] = parts[-2].replace(',', '.')  # "80.55"
    
    # Look for additional description + lot number
    for line in block[1:]:
        if re.search(r'Chargen-/Lot-Nr\.\s*(.+)', line, re.IGNORECASE):
            lot_match = re.search(r'Chargen-/Lot-Nr\.\s*(.+)', line, re.IGNORECASE)
            if lot_match:
                item_data['lot_number'] = lot_match.group(1).strip()
        else:
            if line and not re.match(r'^\d+\s+\S+', line):
                item_data['description'] += " " + line.strip()
    
    if item_data['item_code'] and item_data['description'] and item_data['quantity']:
        return item_data
    
    return None


#Ruhof
def extract_ruhof_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Ruhof invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split("\n")
            invoice_data = _extract_ruhof_invoice_info(lines)
            
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for line in lines:
                line_clean = line.strip()
                
                # Detect item header
                if re.search(r'UNITS\s+UOM\s+ITEM\s+CODE\s+DESCRIPTION', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop parsing when totals start
                if re.search(r'Net Invoice:|Invoice Total:', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break
                
                # Detect item line: starts with a number qty + UOM + item code
                if re.match(r'^\d+\s+\S+\s+\S+', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                elif current_block and line_clean:
                    # continuation line → add to description
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Parse each item block
            for block, inv_data in item_blocks:
                item_data = _parse_ruhof_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_ruhof_invoice_info(lines: List[str]) -> Dict:
    """Extract invoice-level metadata from Ruhof invoice."""
    invoice_data = {
        'invoice_date': '',
        'invoice_number': '',
        'customer_number': '',
        'order_no': '',
        'po_number': ''
    }
    
    for line in lines:
        # Invoice header line
        inv_match = re.search(
            r'(\d{7,}-IN)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\S+)\s+(\d+)',
            line
        )
        if inv_match:
            invoice_data['invoice_number'] = inv_match.group(1)      # e.g. 4969153-IN
            invoice_data['invoice_date'] = inv_match.group(2)        # e.g. 4/29/2024
            invoice_data['order_no'] = inv_match.group(3)            # e.g. 0890258
            invoice_data['customer_number'] = inv_match.group(5)     # e.g. 00-0031456
            invoice_data['po_number'] = inv_match.group(6)           # e.g. 0016494
    
    return invoice_data

def _parse_ruhof_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse a Ruhof invoice item block (may span multiple lines).
    Example block:
    [
        '2 EACH 34560-21 PREPZYME w/BIOCLEAN TECH 2 16.91 33.82',
        '(32oz/946ml with foam sprayer)'
    ]
    """
    if not block:
        return None

    # First line contains structured fields
    first_line = block[0]

    match = re.match(
        r'^(\d+)\s+(\w+)\s+([\w-]+)\s+(.+?)\s+(\d+)\s+([\d.]+)\s+([\d.]+)$',
        first_line
    )
    if not match:
        return None

    qty, _, item_code, description, pkgs, unit_price, _ = match.groups()

    # If there are continuation lines, append them to description
    if len(block) > 1:
        continuation = " ".join(block[1:]).strip()
        description = f"{description} {continuation}"

    return {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "customer_number": invoice_data.get("customer_number", ""),
        "po_number": invoice_data.get("po_number", ""),
        "quantity": qty,
        "item_code": item_code,
        "description": description.strip(),
        "pkgs": pkgs,
        "unit_price": unit_price,
        "page_number": page_num + 1  # optional
        # uom removed
        # amount removed
    }


#S.u.A. Martin
def extract_sua_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from S.u.A. Martin invoice format.
    Returns a list of dictionaries for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_data = _extract_sua_invoice_info(lines)

            item_blocks = []
            current_block = []
            in_items_section = False

            for line in lines:
                line_clean = line.strip()

                # Detect start of item section
                if re.search(r'POS\.\s+ARTICLE\s+description\s+qty', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue

                if not in_items_section:
                    continue

                # Stop parsing when totals appear
                if re.search(r'total\s+net|total/EUR|package|payment', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break

                # Detect item line: starts with item no + code
                if re.match(r'^\d+\s+\S+\s+\S+', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                elif current_block and line_clean:
                    # continuation line → part of description
                    current_block.append(line_clean)

            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))

            # Parse blocks
            for block, inv_data in item_blocks:
                item_data = _parse_sua_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_sua_invoice_info(lines: List[str]) -> Dict:
    """Extract invoice-level metadata from S.u.A. Martin invoice."""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'dev_no': '',
        'dii_no': ''
    }

    for line in lines:
        if "INVOICE NO." in line:
            m = re.search(r'INVOICE NO.\s*:(\S+)', line)
            if m:
                invoice_data['invoice_number'] = m.group(1)

        if "Cust.-No." in line:
            m = re.search(r'Cust.-No.\s*:(\S+)', line)
            if m:
                invoice_data['customer_number'] = m.group(1)

        if "Date" in line:
            m = re.search(r'Date\s*:(\S+)', line)
            if m:
                invoice_data['invoice_date'] = m.group(1)

        if "DEV-No." in line:
            m = re.search(r'DEV-No.\s*:(\S+)', line)
            if m:
                invoice_data['dev_no'] = m.group(1)

        if "DII-NO." in line:
            m = re.search(r'DII-NO.\s*:(\S+)', line)
            if m:
                invoice_data['dii_no'] = m.group(1)

    return invoice_data

def _parse_sua_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse an item block from S.u.A. Martin invoices.
    Each block may span multiple lines, starting with "your order no.".
    """
    if not block:
        return None

    order_number = ""
    order_date = ""
    art_number = ""
    lot_number = ""
    description_lines = []
    qty = ""
    unit_price = ""

    for line in block:
        line = line.strip()

        # Extract order no. and date
        match_order = re.match(r"your order no\. (\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})", line, re.I)
        if match_order:
            order_number, order_date = match_order.groups()
            continue

        # Extract line with qty + unit price (ignore total)
        match_item = re.match(
            r"^\d+\s+SAM\s+[A-Z0-9/ ]+\s+(\d+)\s+([\d,.]+)\s+[\d,.]+$", line
        )
        if match_item:
            qty, unit_price = match_item.groups()
            continue

        # Extract art number
        match_art = re.search(r"your art\.:\s*([A-Za-z0-9-]+)", line, re.I)
        if match_art:
            art_number = match_art.group(1)
            continue

        # Extract lot number
        match_lot = re.search(r"Lot number\s+([A-Za-z0-9/ ]+)", line, re.I)
        if match_lot:
            lot_number = match_lot.group(1)
            continue

        # Otherwise treat as description
        if line and not line.lower().startswith("lot-code"):
            description_lines.append(line)

    description = " ".join(description_lines).strip()

    return {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "customer_number": invoice_data.get("customer_number", ""),
        "order_number": order_number,
        "order_date": order_date,
        "art_number": art_number,
        "lot_number": lot_number,
        "description": description,
        "quantity": qty,
        "unit_price": unit_price,
        "page_number": page_num + 1
    }

#Schmid
def extract_schmid_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Schmid invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")

            # Extract invoice-level info
            invoice_data = _extract_schmid_invoice_info(lines)

            # Identify item blocks
            item_blocks = []
            current_block = []
            in_items_section = False

            for i, line in enumerate(lines):
                line_clean = line.strip()

                # Start of items section
                if re.search(r'POS\s+article\s+description\s+qty', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue

                if not in_items_section:
                    continue

                # Stop when totals/summary begins
                if re.search(r'total\s+net|total/EUR|payment|delivery|package', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = []
                    break

                # Item start (line with pos number and qty + prices)
                if re.match(r'^\d+\s+[A-Za-z0-9-]+.*\d+[\.,]\d+\s+\d+[\.,]\d+$', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Continuation lines (descriptions, lot, art, etc.)
                elif current_block and line_clean:
                    current_block.append(line_clean)

            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))

            # Process each block
            for block, inv_data in item_blocks:
                item_data = _parse_schmid_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_schmid_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice-level information from Schmid invoice"""
    invoice_data = {
        "invoice_number": "",
        "invoice_date": "",
        "customer_number": "",
        "order_no": "",
        "order_date": "",
        "delivery_note": ""
    }

    for line in lines:
        line_clean = line.strip()

        inv_match = re.search(r'INVOICE NO\.\s*:\s*(\d+)', line_clean, re.I)
        if inv_match and not invoice_data["invoice_number"]:
            invoice_data["invoice_number"] = inv_match.group(1)

        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.I)
        if date_match and not invoice_data["invoice_date"]:
            invoice_data["invoice_date"] = date_match.group(1)

        cust_match = re.search(r'Cust\.-No\.\s*:\s*(\d+)', line_clean, re.I)
        if cust_match and not invoice_data["customer_number"]:
            invoice_data["customer_number"] = cust_match.group(1)

        dn_match = re.search(r'Delivery Note No\.\s*(\d+)', line_clean, re.I)
        if dn_match and not invoice_data["delivery_note"]:
            invoice_data["delivery_note"] = dn_match.group(1)

        ord_match = re.search(r'your order no\.\s*(\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.I)
        if ord_match and not invoice_data["order_no"]:
            invoice_data["order_no"], invoice_data["order_date"] = ord_match.groups()

    return invoice_data

def _parse_schmid_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse an individual item block from Schmid invoices.
    """
    if not block:
        return None

    quantity = ""
    description_lines = []
    unit_price = ""
    art_number = ""
    lot_number = ""
    order_number = ""
    order_date = ""

    # First line with qty + description + unit price + line total
    first_line = block[0].strip()
    match = re.match(r'^\d+\s+[A-Z0-9/-]+\s+(.+?)\s+(\d+)\s+([\d,.]+)\s+[\d,.]+$', first_line)
    if match:
        description_lines.append(match.group(1).strip())
        quantity = match.group(2)
        unit_price = match.group(3)

    for line in block[1:]:
        line = line.strip()

        # Extract order number & date
        order_match = re.search(r'your order no\.\s*(\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line, re.I)
        if order_match:
            order_number, order_date = order_match.groups()
            continue

        # Extract art number
        art_match = re.search(r'your art\.-no\.\s*:\s*([A-Za-z0-9-]+)', line, re.I)
        if art_match:
            art_number = art_match.group(1)
            continue

        # Extract lot number
        lot_match = re.search(r'lot number[:\s]+([A-Za-z0-9/-]+)', line, re.I)
        if lot_match:
            lot_number = lot_match.group(1)
            continue

        # Otherwise treat as description continuation
        if line and not re.match(r'^\d+\s+[A-Z0-9/-]+', line):
            description_lines.append(line)

    description = " ".join(description_lines).strip()

    return {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "customer_number": invoice_data.get("customer_number", ""),
        "order_number": order_number,
        "order_date": order_date,
        "delivery_note": invoice_data.get("delivery_note", ""),
        "art_number": art_number,
        "lot_number": lot_number,
        "description": description,
        "quantity": quantity,
        "unit_price": unit_price,
        "page_number": page_num + 1
    }


#SGS North America
def extract_sgs_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from SGS North America invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_data = _extract_sgs_invoice_info(lines)

            in_items_section = False
            item_blocks = []

            for line in lines:
                line_clean = line.strip()

                # Start when we hit the column headers
                if re.search(r'Quantity\s+Net Amount\s+Amount', line_clean, re.I):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # Stop when we reach summary section
                if re.search(r'Sub-Total|Net \$|Total', line_clean, re.I):
                    break

                # Skip empty or irrelevant lines
                if not line_clean or "Alternative Currency" in line_clean:
                    continue

                item_blocks.append((line_clean, invoice_data.copy()))

            # Parse item lines
            for block, inv_data in item_blocks:
                item_data = _parse_sgs_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_sgs_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice-level info from SGS North America invoices."""
    invoice_data = {
        "invoice_number": "",
        "invoice_date": "",
        "client_name": "",
        "account_number": "",
        "our_reference": "",
        "client_reference": "",
        "po_number": ""
    }

    for line in lines:
        line_clean = line.strip()

        inv_match = re.search(r'INVOICE No[:\s]+(\d+)', line_clean, re.I)
        if inv_match:
            invoice_data["invoice_number"] = inv_match.group(1)

        date_match = re.search(r'Issue Date\s*:\s*(.+)', line_clean, re.I)
        if date_match:
            invoice_data["invoice_date"] = date_match.group(1).strip()

        client_match = re.search(r'Client\s+(.+)', line_clean, re.I)
        if client_match and not invoice_data["client_name"]:
            invoice_data["client_name"] = client_match.group(1).strip()

        acct_match = re.search(r'Account No\.\s*:\s*([^\s]+)', line_clean, re.I)
        if acct_match:
            invoice_data["account_number"] = acct_match.group(1)

        ref_match = re.search(r'Our Refer\. No\.\s*:\s*(.+)', line_clean, re.I)
        if ref_match:
            invoice_data["our_reference"] = ref_match.group(1).strip()

        client_ref_match = re.search(r'Client Ref No\.\s*:\s*(.+)', line_clean, re.I)
        if client_ref_match:
            invoice_data["client_reference"] = client_ref_match.group(1).strip()

        po_match = re.search(r'PO No\.\s*:\s*(.+)', line_clean, re.I)
        if po_match:
            invoice_data["po_number"] = po_match.group(1).strip()

    return invoice_data

def _parse_sgs_item_block(line: str, invoice_data: Dict, page_num: int) -> Dict:
    """
    Parse a single SGS invoice item line into structured data.
    """
    item_data = invoice_data.copy()
    item_data["page"] = page_num + 1

    # Example line:
    # "Aug 16, 2022 - Surveillance Audit (10) 1.50 3,150.00 3,150.00"
    match = re.match(r"(.+?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)$", line)
    if match:
        desc, qty, net, total = match.groups()
        item_data.update({
            "description": desc.strip(),
            "quantity": qty.strip(),
            "net": net.strip(),
            "total": total.strip(),
        })
        return item_data

    # Expenses like "Taxi 112.28 112.28"
    match = re.match(r"(Taxi|Meal|Hotel|Rental Car|Flights)\s+([\d.,]+)\s+([\d.,]+)$", line, re.I)
    if match:
        desc, net, total = match.groups()
        item_data.update({
            "description": desc.strip(),
            "quantity": "1",  # implied
            "net": net.strip(),
            "total": total.strip(),
        })
        return item_data

    # Page 2 extras: "Processing Fee 7.5% 123.82 123.82"
    match = re.match(r"(Processing Fee.*?|Reporting.*?)\s+([\d.,]+)\s+([\d.,]+)$", line, re.I)
    if match:
        desc, net, total = match.groups()
        item_data.update({
            "description": desc.strip(),
            "quantity": "1",  # implied
            "net": net.strip(),
            "total": total.strip(),
        })
        return item_data

    return None


#SIBEL
def extract_sibel_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from SIBEL invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_data = _extract_sibel_invoice_info(lines)

            in_items_section = False
            item_blocks = []

            for line in lines:
                line_clean = line.strip()

                # Start when we hit the column headers
                if re.search(r'Pos\.\s+Item N°\s+Description', line_clean, re.I):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # Stop when we reach totals
                if re.search(r'Total ExVAT|VAT|Total InVAT', line_clean, re.I):
                    break

                if not line_clean:
                    continue

                item_blocks.append((line_clean, invoice_data.copy()))

            # Parse each item block
            for block, inv_data in item_blocks:
                item_data = _parse_sibel_item_block(block, inv_data, page_num, text)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_sibel_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice-level info from SIBEL invoices."""
    invoice_data = {
        "invoice_number": "",
        "invoice_date": ""
    }

    for line in lines:
        line_clean = line.strip()

        inv_match = re.search(r'N°\s+(\d+)', line_clean, re.I)
        if inv_match:
            invoice_data["invoice_number"] = inv_match.group(1)

        date_match = re.search(r'Date\s+(\d{2}/\d{2}/\d{4})', line_clean, re.I)
        if date_match:
            invoice_data["invoice_date"] = date_match.group(1)

    return invoice_data

def _parse_sibel_item_block(line: str, invoice_data: Dict, page_num: int, full_text: str) -> Dict:
    """
    Parse a single SIBEL invoice item line.
    Example:
    "1 18-2-0176-0010 DEBAKEY MICRO CLAMP... 1 1 510,88 510,88"
    """
    item_data = invoice_data.copy()
    item_data["page"] = page_num + 1

    # Regex: Pos, ItemNo, Description, Qty, Unit, UnitPrice, Total
    match = re.match(
        r"(\d+)\s+([\w\-]+)\s+(.+?)\s+(\d+)\s+([\w]+)\s+([\d,]+)\s+([\d,]+)$",
        line
    )
    if match:
        pos, item_no, desc, qty, unit, unit_price, total = match.groups()
        item_data.update({
            "item_number": item_no.strip(),
            "description": desc.strip(),
            "quantity": qty.strip(),
            "unit": unit.strip(),
            "unit_price": unit_price.strip()
        })

        # Optional: Article Reference
        art_no_match = re.search(r"Your article ref\.\s*:\s*([A-Za-z0-9\-\/]+)", full_text, re.I)
        if art_no_match:
            item_data["article_number"] = art_no_match.group(1)

        # Optional: Lot Number
        lot_match = re.search(r"LOT\s*:\s*([A-Za-z0-9\-\/]+)", full_text, re.I)
        if lot_match:
            item_data["lot_number"] = lot_match.group(1)

        return item_data

    return None


#Siema
def extract_siema_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Siema (Siegfried Martin) invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data: List[Dict] = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_info = _extract_siema_invoice_info(lines)

            in_items_section = False
            current_block: List[str] = []
            item_blocks: List[tuple] = []

            # context that applies to subsequent items until changed
            current_order = ""
            current_order_date = ""
            current_lst = ""
            current_ref = ""

            for line in lines:
                line_clean = line.strip()

                # detect start of the items table
                if re.search(r'POS\s+ARTICLE\s+description', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # stop parsing when totals appear
                if re.search(r'total\s+net|total/EUR|total\/EUR', line_clean, re.IGNORECASE):
                    if current_block:
                        inv_copy = invoice_info.copy()
                        inv_copy['order_number'] = current_order
                        inv_copy['order_date'] = current_order_date
                        inv_copy['lst_number'] = current_lst
                        inv_copy['ref_no'] = current_ref
                        item_blocks.append((current_block, inv_copy))
                        current_block = []
                    break

                # update order context
                ord_match = re.search(r'your order no\.\s*(\d+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if ord_match:
                    current_order, current_order_date = ord_match.groups()
                    continue

                # update LST and ref context (these usually appear before item lines)
                lst_match = re.search(r'\bLST[:\s]*([A-Za-z0-9 \-\/]+)', line_clean, re.IGNORECASE)
                if lst_match:
                    current_lst = lst_match.group(1).strip()
                    continue

                ref_match = re.search(r'your ref\.no\.\s*[:\s]*([A-Za-z0-9\-\/]+)', line_clean, re.IGNORECASE)
                if ref_match:
                    current_ref = ref_match.group(1).strip()
                    continue

                # handle carry-over: finalize block and keep parsing
                if re.search(r'carry-over', line_clean, re.IGNORECASE):
                    if current_block:
                        inv_copy = invoice_info.copy()
                        inv_copy['order_number'] = current_order
                        inv_copy['order_date'] = current_order_date
                        inv_copy['lst_number'] = current_lst
                        inv_copy['ref_no'] = current_ref
                        item_blocks.append((current_block, inv_copy))
                        current_block = []
                    continue

                # detect item start lines: e.g. "1 SM ... 5 59,15 295,75"
                if re.match(r'^\d+\s+SM\b.*\s+\d+\s+[\d\.,]+\s+[\d\.,]+$', line_clean):
                    if current_block:
                        inv_copy = invoice_info.copy()
                        inv_copy['order_number'] = current_order
                        inv_copy['order_date'] = current_order_date
                        inv_copy['lst_number'] = current_lst
                        inv_copy['ref_no'] = current_ref
                        item_blocks.append((current_block, inv_copy))
                    current_block = [line_clean]
                    continue

                # continuation lines for the current item
                if current_block and line_clean:
                    current_block.append(line_clean)

            # append any final block left
            if current_block:
                inv_copy = invoice_info.copy()
                inv_copy['order_number'] = current_order
                inv_copy['order_date'] = current_order_date
                inv_copy['lst_number'] = current_lst
                inv_copy['ref_no'] = current_ref
                item_blocks.append((current_block, inv_copy))

            # parse item blocks
            for block, inv_data in item_blocks:
                item_data = _parse_siema_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_siema_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice-level metadata from Siema invoice (invoice number, date, cust-no)."""
    invoice_data = {
        "invoice_number": "",
        "invoice_date": "",
        "customer_number": ""
    }

    for line in lines:
        lc = line.strip()

        inv_match = re.search(r'INVOICE NO\.\s*:\s*([A0-9-]+)', lc, re.IGNORECASE)
        if inv_match and not invoice_data["invoice_number"]:
            invoice_data["invoice_number"] = inv_match.group(1).strip()

        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', lc, re.IGNORECASE)
        if date_match and not invoice_data["invoice_date"]:
            invoice_data["invoice_date"] = date_match.group(1).strip()

        cust_match = re.search(r'Cust\.-No\.\s*:\s*([0-9\-]+)', lc, re.IGNORECASE)
        if cust_match and not invoice_data["customer_number"]:
            invoice_data["customer_number"] = cust_match.group(1).strip()

    return invoice_data

def _parse_siema_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse a multi-line Siema item block and return a dict.

    Expected block example:
      [
        '1 SM Diethrich-Hegemann Scissors 13.5 cm, 5 59,15 295,75',
        '0402-13.5/600 laterally angled, 60 degrees,',
        'sharp, round',
        'satin finish crosswise/satin finish crosswise',
        'Lot number 91312',
        'Drawing No./versionZG X402-13.5 / E'
      ]
    """
    if not block:
        return None

    out = {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "customer_number": invoice_data.get("customer_number", ""),
        "order_number": invoice_data.get("order_number", ""),
        "order_date": invoice_data.get("order_date", ""),
        "lst_number": invoice_data.get("lst_number", ""),
        "ref_no": invoice_data.get("ref_no", ""),
        "item_number": "",
        "description": "",
        "quantity": "",
        "unit_price": "",
        "lot_number": "",
        "page": page_num + 1
    }

    first_line = block[0].strip()

    # Extract trailing qty and unit price from first line (we ignore line-total)
    tail_match = re.search(r'(\d+)\s+([\d\.,]+)\s+[\d\.,]+\s*$', first_line)
    if tail_match:
        qty = tail_match.group(1)
        unit_price_raw = tail_match.group(2)
        # normalize German-style numbers to dot-decimal (e.g. "59,15" -> "59.15", "1.086,12"->"1086.12")
        unit_price_norm = unit_price_raw.replace('.', '').replace(',', '.') if ('.' in unit_price_raw and ',' in unit_price_raw) else unit_price_raw.replace(',', '.')
        out['quantity'] = qty
        out['unit_price'] = unit_price_norm
        left = first_line[:tail_match.start()].strip()
    else:
        # fallback if qty/price not found
        left = re.sub(r'^\d+\s+SM\s+', '', first_line, flags=re.IGNORECASE).strip()

    # remove leading position + "SM" token if present
    left = re.sub(r'^\d+\s+SM\s+', '', left, flags=re.IGNORECASE).strip()
    description_parts: List[str] = [left] if left else []

    # Try inline item number (Case 2), e.g. "5 SM 0754/600 ..."
    inline_match = re.search(r'\bSM\s+([0-9]{2,5}(?:[-/][\dA-Za-z\.\-/]+)?)', first_line, re.IGNORECASE)
    if inline_match:
        code = inline_match.group(1).strip()
        out['item_number'] = f"SM {code}"
        # remove code from description if it remained
        description_parts = [re.sub(re.escape(code), '', p, flags=re.IGNORECASE).strip() for p in description_parts]

    # scan continuation lines to find item-number on next line (Case 1), ref_no, lst, lot, drawing, etc.
    for i, ln in enumerate(block[1:], start=1):
        ln_strip = ln.strip()

        # LST inside block (rare) - override invoice-level if present
        lst_m = re.search(r'\bLST[:\s]*([A-Za-z0-9 \-\/]+)', ln_strip, re.IGNORECASE)
        if lst_m:
            out['lst_number'] = lst_m.group(1).strip()
            continue

        # reference number inside block (rare) - override
        ref_m = re.search(r'your ref\.no\.\s*[:\s]*([A-Za-z0-9\-\/]+)', ln_strip, re.IGNORECASE)
        if ref_m:
            out['ref_no'] = ref_m.group(1).strip()
            continue

        # lot number
        lot_m = re.search(r'Lot\s*number\s*[:\s]*([A-Za-z0-9\-/]+)', ln_strip, re.IGNORECASE)
        if lot_m:
            out['lot_number'] = lot_m.group(1).strip()
            continue

        # Case 1: second line starts with item code like "0402-13.5/600 ..."
        itemnum_m = re.match(r'^([0-9]{2,5}[-/][\dA-Za-z\.\-/]+)\b(.*)$', ln_strip)
        if itemnum_m and not out['item_number']:
            code = itemnum_m.group(1).strip()
            rest = itemnum_m.group(2).strip()
            out['item_number'] = f"SM {code}"
            if rest:
                description_parts.append(rest)
            continue

        # If a line starts with something like "0402-13.5/600" that got split differently, handle it
        itemnum_loose = re.search(r'([0-9]{2,5}[-/][\dA-Za-z\.\-/]+)', ln_strip)
        if itemnum_loose and not out['item_number']:
            # be conservative: accept only if it's near start
            if ln_strip.startswith(itemnum_loose.group(1)):
                out['item_number'] = f"SM {itemnum_loose.group(1).strip()}"
                rest = ln_strip.replace(itemnum_loose.group(1), '').strip()
                if rest:
                    description_parts.append(rest)
                continue

        # skip known meta-lines that we do not want in description
        if re.search(r'Customs tariff|Country of origin|special item|carry-over', ln_strip, re.IGNORECASE):
            continue

        # drawing line -> include in description
        if re.search(r'Drawing\s+No\.', ln_strip, re.IGNORECASE):
            description_parts.append(ln_strip)
            continue

        # otherwise treat as description continuation
        description_parts.append(ln_strip)

    # Finalize description
    description_clean = " - ".join([p for p in description_parts if p]).strip()
    out['description'] = re.sub(r'\s+', ' ', description_clean).strip()

    # Only return if we have essential data
    if out['quantity'] and out['description']:
        return out

    return None


#SignTech
def extract_sigtech_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from SignTech invoice format (SignTech).
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data: List[Dict] = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_data = _extract_sigtech_invoice_info(lines)

            in_items_section = False
            current_block: List[str] = []
            item_blocks: List[tuple] = []

            for line in lines:
                line_clean = line.strip()

                # detect start of items table by column header row
                if re.search(r'qty\.\s+ord\s+qty\.\s+ship\.|qty\.\s+ord\s+qty\.', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # stop when totals appear
                if re.search(r'Sales Amt\.|Total/\$|Total \$', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break

                # detect item start:
                # e.g. "3 3 0 EACH G1080-76 three-way luer-lock, ... 58.00 174.00"
                if re.match(r'^\d+\s+\d+\s+\d+\s+\S+\s+[A-Z0-9-]+\b', line_clean):
                    # finalize previous
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    continue

                # continuation lines (description, Lot No., Country of origin)
                if current_block and line_clean:
                    current_block.append(line_clean)

            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))

            # parse blocks
            for block, inv_data in item_blocks:
                item_data = _parse_sigtech_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_sigtech_invoice_info(lines: List[str]) -> Dict[str, str]:
    """
    Extract invoice-level info for SignTech invoices.
    Returns dict with keys:
      invoice_number, invoice_date, order_number, order_date,
      customer_number, customer_po, purchase_order_no, ship_date, ship_via
    """
    invoice_data = {
        "invoice_number": "",
        "invoice_date": "",
        "order_number": "",
        "order_date": "",
        "customer_number": "",
        "customer_po": "",
        "purchase_order_no": "",
        "ship_date": "",
        "ship_via": ""
    }

    for i, line in enumerate(lines):
        lc = line.strip()

        # Line that follows header "INVOICE DATE INVOICE NO. PAGE"
        m_date_no = re.match(r'^\s*(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+\d+', lc)
        if m_date_no:
            invoice_data["invoice_date"] = m_date_no.group(1)
            invoice_data["invoice_number"] = m_date_no.group(2)
            continue

        # The ORDER line containing many fields (Order No, Order Date, Customer No, Customer P.O., Purchase Order No, Ship Date, Ship Via)
        # e.g. "32850 4/29/2024 12146 0016497 0016497 4/29/2024 UPS Ground"
        m_orderline = re.match(
            r'^\s*(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+([^\s]+)\s+([^\s]+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(.+)$',
            lc
        )
        if m_orderline:
            invoice_data["order_number"] = m_orderline.group(1)
            invoice_data["order_date"] = m_orderline.group(2)
            invoice_data["customer_number"] = m_orderline.group(3)
            invoice_data["customer_po"] = m_orderline.group(4)
            invoice_data["purchase_order_no"] = m_orderline.group(5)
            invoice_data["ship_date"] = m_orderline.group(6)
            invoice_data["ship_via"] = m_orderline.group(7).strip()
            continue

        # fallback: small variations like extra whitespace or missing fields
        # try to catch "ORDER NO." header followed by data on next line
        if re.search(r'ORDER NO\.', lc, re.IGNORECASE) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^\s*(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+([^\s]+)\s+([^\s]+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(.+)$', next_line)
            if m:
                invoice_data["order_number"] = m.group(1)
                invoice_data["order_date"] = m.group(2)
                invoice_data["customer_number"] = m.group(3)
                invoice_data["customer_po"] = m.group(4)
                invoice_data["purchase_order_no"] = m.group(5)
                invoice_data["ship_date"] = m.group(6)
                invoice_data["ship_via"] = m.group(7).strip()

    return invoice_data

def _parse_sigtech_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse a SignTech item block (multi-line).
    Returns structured dict with invoice + item details.
    """
    if not block:
        return None

    out: Dict[str, str] = {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "order_number": invoice_data.get("order_number", ""),
        "order_date": invoice_data.get("order_date", ""),
        "customer_number": invoice_data.get("customer_number", ""),
        "customer_po": invoice_data.get("customer_po", ""),
        "purchase_order_no": invoice_data.get("purchase_order_no", ""),
        "ship_date": invoice_data.get("ship_date", ""),
        "ship_via": invoice_data.get("ship_via", ""),
        "qty_ordered": "",
        "qty_shipped": "",
        "qty_backorder": "",
        "unit": "",
        "item_number": "",
        "description": "",
        "unit_price": "",
        "ext_price": "",
        "lot_number": "",
        "country_of_origin": "",
        "page": page_num + 1
    }

    first_line = block[0].strip()
    description_parts: List[str] = []

    # primary pattern: qtys, unit, item_no, description, prices
    m = re.match(
        r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+([A-Z0-9-]+)\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$',
        first_line
    )
    if m:
        out['qty_ordered'] = m.group(1)
        out['qty_shipped'] = m.group(2)
        out['qty_backorder'] = m.group(3)
        out['unit'] = m.group(4)
        out['item_number'] = m.group(5)
        desc_fragment = m.group(6).strip()
        out['unit_price'] = m.group(7).replace(',', '')
        out['ext_price'] = m.group(8).replace(',', '')
        description_parts.append(desc_fragment)
    else:
        # fallback: try extracting trailing prices
        combined = " ".join(block)
        tail = re.search(r'([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$', combined)
        if tail:
            out['unit_price'] = tail.group(1).replace(',', '')
            out['ext_price'] = tail.group(2).replace(',', '')
            head = combined[:tail.start()].strip()
            head_first_line = head.splitlines()[0]
            m2 = re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+([A-Z0-9-]+)\s*(.*)$', head_first_line)
            if m2:
                out['qty_ordered'] = m2.group(1)
                out['qty_shipped'] = m2.group(2)
                out['qty_backorder'] = m2.group(3)
                out['unit'] = m2.group(4)
                out['item_number'] = m2.group(5)
                description_parts.append(m2.group(6).strip())
                description_parts += head.splitlines()[1:]
            else:
                description_parts.append(head)
        else:
            description_parts.append(first_line)

    # handle continuation lines
    for ln in block[1:]:
        ln_s = ln.strip()
        lot_m = re.search(r'Lot\s*No\.?\s*[:\s]*([A-Za-z0-9\-]+)', ln_s, re.IGNORECASE)
        if lot_m:
            out['lot_number'] = lot_m.group(1).strip()
            continue
        co_m = re.search(r'Country of origin[:\s]*([A-Za-z ]+)', ln_s, re.IGNORECASE)
        if co_m:
            out['country_of_origin'] = co_m.group(1).strip()
            continue
        description_parts.append(ln_s)

    # finalize description
    desc_clean = " - ".join([d for d in description_parts if d])
    desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
    out['description'] = desc_clean

    # Defensive: check that at least item number + some qty exist
    if out['item_number'] and not (out['qty_ordered'] or out['qty_shipped'] or out['qty_backorder']):
        # still allow but loggable point – qtys missing
        pass

    # Must have at least item_number + description
    if out['item_number'] and out['description']:
        return out

    return None


#Simmank OCR Needed

#SIS
def extract_sis_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from SIS invoice format.
    Returns list of dicts (one per item line).
    """
    extracted_data: List[Dict] = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_data = _extract_sis_invoice_info(lines)

            in_items_section = False
            current_block: List[str] = []
            item_blocks: List[tuple] = []

            for line in lines:
                line_clean = line.strip()

                # detect start of items table
                if re.search(r'^Item\s+Qty\.\s+Price\s+Ext\.?', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # stop when totals appear
                if re.search(r'Subtotal|Total Due', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break

                # item line: description ending with qty + price + ext
                if re.match(r'^.+\s+\d+\s+\$\d+[\d,]*\.\d{2}\s+\$\d+[\d,]*\.\d{2}$', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    continue

                # continuation line (e.g. "Labor Hour to refinish...")
                if current_block and line_clean:
                    current_block.append(line_clean)

            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))

            # parse item blocks
            for block, inv_data in item_blocks:
                item_data = _parse_sis_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_sis_invoice_info(lines: List[str]) -> Dict[str, str]:
    """
    Extract invoice-level info for SIS invoices.
    """
    invoice_data = {
        "invoice_number": "",
        "invoice_date": "",
        "po_number": "",
        "order_date": "",
        "ship_date": "",
        "bill_to": "",
        "ship_to": ""
    }

    for i, line in enumerate(lines):
        lc = line.strip()

        m_ship = re.search(r'Date Shipped\s+\.{5,}\s*([\d/]+)', lc)
        if m_ship:
            invoice_data["ship_date"] = m_ship.group(1)
            continue

        m_inv = re.search(r'Invoice #\s+\.{5,}\s*(\S+)', lc)
        if m_inv:
            invoice_data["invoice_number"] = m_inv.group(1)
            continue

        m_po = re.search(r'P\.O\.\s+\.{5,}\s*(\S+)', lc)
        if m_po:
            invoice_data["po_number"] = m_po.group(1)
            continue

        m_order = re.search(r'Order Date\s+\.{5,}\s*([\d/]+)', lc)
        if m_order:
            invoice_data["order_date"] = m_order.group(1)
            continue

        # Bill To / Ship To block
        if lc.startswith("Bill To:"):
            bill_lines, ship_lines = [], []
            # join next few lines until dashed separator
            j = i + 1
            while j < len(lines) and not re.match(r'^[_]{5,}', lines[j]):
                if "Ship To:" in lines[j]:
                    j += 1
                    continue
                if "NOVO" in lines[j] or "USA" in lines[j] or "DRIVE" in lines[j]:
                    # heuristic: alternate bill vs ship based on indent
                    if "Ship" in lines[i]:
                        ship_lines.append(lines[j].strip())
                    else:
                        bill_lines.append(lines[j].strip())
                j += 1
            invoice_data["bill_to"] = " ".join(bill_lines).strip()
            invoice_data["ship_to"] = " ".join(ship_lines).strip()

    return invoice_data

def _parse_sis_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse SIS item block into structured dict.
    """
    if not block:
        return None

    out: Dict[str, str] = {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "po_number": invoice_data.get("po_number", ""),
        "order_date": invoice_data.get("order_date", ""),
        "ship_date": invoice_data.get("ship_date", ""),
        "bill_to": invoice_data.get("bill_to", ""),
        "ship_to": invoice_data.get("ship_to", ""),
        "description": "",
        "quantity": "",
        "unit_price": "",
        "ext_price": "",
        "page": page_num + 1
    }

    first_line = block[0].strip()
    # e.g. "Retractor Blade 1 $85.00 $85.00"
    m = re.match(r'^(.+?)\s+(\d+)\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})$', first_line)
    if m:
        out["description"] = m.group(1).strip()
        out["quantity"] = m.group(2)
        out["unit_price"] = m.group(3).replace(",", "")
        out["ext_price"] = m.group(4).replace(",", "")

    # append continuation lines to description
    for ln in block[1:]:
        out["description"] += " - " + ln.strip()

    return out if out["description"] else None


#Sitec
def extract_sitec_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Sitec invoice format.
    Returns list of dicts (one per item line).
    """
    extracted_data: List[Dict] = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            invoice_data = _extract_sitec_invoice_info(lines)

            in_items_section = False
            current_block: List[str] = []
            item_blocks: List[tuple] = []

            for line in lines:
                line_clean = line.strip()

                # detect start of items table
                if re.search(r'^S\.\#\s+Product Description', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # stop at totals
                if re.search(r'^TOTAL PIECES', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break

                # detect item start (serial # + item number)
                if re.match(r'^\d+\s+[A-Z0-9-]+', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    continue

                # continuation lines: description, LST
                if current_block and line_clean:
                    current_block.append(line_clean)

            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))

            # parse item blocks
            for block, inv_data in item_blocks:
                item_data = _parse_sitec_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_sitec_invoice_info(lines: List[str]) -> Dict[str, str]:
    invoice_data = {
        "invoice_number": "",
        "invoice_date": "",
        "country_of_origin": "PAKISTAN"  # default as per samples
    }

    for line in lines:
        lc = line.strip()
        m_inv = re.search(r'INVOICE NO\.\s*(\S+)', lc, re.IGNORECASE)
        if m_inv:
            invoice_data["invoice_number"] = m_inv.group(1).strip()
            continue
        m_date = re.search(r'DATE[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})', lc, re.IGNORECASE)
        if m_date:
            invoice_data["invoice_date"] = m_date.group(1).strip()
            continue
        m_country = re.search(r'Country of Origin[:\s]*(\S+)', lc, re.IGNORECASE)
        if m_country:
            invoice_data["country_of_origin"] = m_country.group(1).strip()
            continue

    return invoice_data

def _parse_sitec_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """
    Parse Sitec item block (multi-line) into structured dict.
    Removed columns: ext_price, serial_number, country_of_origin
    """
    if not block:
        return None

    out: Dict[str, str] = {
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_date": invoice_data.get("invoice_date", ""),
        "item_number": "",
        "description": "",
        "order_number": "",
        "quantity": "",
        "unit_price": "",
        "lst_number": "",
        "page": page_num + 1
    }

    # first line contains item_number, description, order#, qty, unit_price
    first_line = block[0].strip()

    # pattern: item_number description order# qty unit_price ext_price
    m = re.match(
        r'^\d+\s+([A-Z0-9-]+)\s+(.+?)\s+(\d+)\s+(\d+)\s+([\d,]+\.\d{2})',
        first_line
    )
    if m:
        out["item_number"] = m.group(1)
        out["description"] = m.group(2).strip()
        out["order_number"] = m.group(3)
        out["quantity"] = m.group(4)
        out["unit_price"] = m.group(5).replace(",", "")
    else:
        # fallback parsing
        tokens = first_line.split()
        if len(tokens) >= 6:
            out["item_number"] = tokens[1]
            out["order_number"] = tokens[-3]
            out["quantity"] = tokens[-2]
            out["unit_price"] = tokens[-1].replace(",", "")
            desc_tokens = tokens[2:-3]
            out["description"] = " ".join(desc_tokens)

    # continuation lines: description or LST
    for ln in block[1:]:
        ln_s = ln.strip()
        if ln_s.upper().startswith("LST"):
            out["lst_number"] = ln_s
        else:
            out["description"] += " - " + ln_s

    return out if out["item_number"] else None


#SMT
def extract_smt_invoice_data(pdf_content: bytes) -> List[Dict]:
    extracted_data: List[Dict] = []

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")
            invoice_info = _extract_smt_invoice_info(lines)

            current_block: List[str] = []
            item_blocks: List[List[str]] = []

            in_items_section = False
            for line in lines:
                line_clean = line.strip()

                # Start of items section
                if re.search(r'POS\s+ARTICLE\s+Description', line_clean):
                    in_items_section = True
                    continue
                if not in_items_section:
                    continue

                # Stop at totals
                if re.search(r'TOTAL PIECES|Total/EUR|Value of goods', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append(current_block)
                        current_block = []
                    break

                # Detect new item start (lines like "1 13-01-20-1800-10P")
                if re.match(r'^\d+\s+[A-Z0-9\-]', line_clean):
                    if current_block:
                        item_blocks.append(current_block)
                    current_block = [line_clean]
                elif current_block:
                    current_block.append(line_clean)

            if current_block:
                item_blocks.append(current_block)

            # Parse items
            for block in item_blocks:
                item_data = _parse_smt_item_block(block, invoice_info, page_num)
                if item_data:
                    extracted_data.append(item_data)

    return extracted_data

def _extract_smt_invoice_info(lines: List[str]) -> Dict[str, str]:
    """
    Extract invoice-level info (invoice number, invoice date, order number/date, LST number)
    """
    info = {
        "invoice_number": "",
        "invoice_date": "",
        "order_number": "",
        "order_date": "",
        "lst_number": ""
    }

    for line in lines:
        line_clean = line.strip()

        # Invoice number: "INVOICE NO. : 436413"
        m_invoice = re.search(r'INVOICE NO\.?\s*:\s*([A-Z0-9\-]+)', line_clean, re.IGNORECASE)
        if m_invoice and not info["invoice_number"]:
            info["invoice_number"] = m_invoice.group(1).strip()
            continue

        # Invoice date: "Date : 17.09.2024"
        m_inv_date = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if m_inv_date and not info["invoice_date"]:
            info["invoice_date"] = m_inv_date.group(1).strip()
            continue

        # Order number and order date: "Your order no. 0017037 - 13.09.2024"
        # FIXED: Removed the colon that doesn't exist in the actual text
        m_order = re.search(r'Your order no\.?\s*([A-Z0-9\-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if m_order and not info["order_number"]:
            info["order_number"] = m_order.group(1).strip()
            info["order_date"] = m_order.group(2).strip()
            continue

        # LST number: "LST Reg. No.: D104403 / 87 LXH"
        if "LST Reg. No." in line_clean:
            lst_m = re.search(r'LST Reg\. No\.?\s*:\s*(.+)', line_clean, re.IGNORECASE)
            if lst_m and not info["lst_number"]:
                info["lst_number"] = lst_m.group(1).strip()
                continue

    return info

def _parse_smt_item_block(block: List[str], invoice_info: Dict[str, str], page_num: int) -> Optional[Dict]:
    if not block:
        return None

    out: Dict[str, str] = {
        "invoice_number": invoice_info.get("invoice_number", ""),
        "invoice_date": invoice_info.get("invoice_date", ""),
        "order_number": invoice_info.get("order_number", ""),
        "order_date": invoice_info.get("order_date", ""),
        "lst_number": invoice_info.get("lst_number", ""),
        "item_number": "",
        "description": "",
        "quantity": "",
        "unit_price": "",
        "total_price": "",
        "lot_number": "",
        "page": str(page_num + 1)
    }

    # Parse first line - examples:
    # "1 13-01-20-1800-10P Kirschner Bow, Hooks for 10 Pack 8,35 83,50"
    # "1 13-01-20-1800 kirschner bow, large, 4 pcs. 203,27 813,08"
    first_line = block[0].strip()
    
    # More flexible pattern to handle different formats
    # The format is: POS ITEM_NUMBER DESCRIPTION QUANTITY UNIT_PRICE TOTAL_PRICE
    m = re.match(r'^(\d+)\s+([A-Z0-9\-]+)\s+(.+?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)$', first_line)
    if m:
        out["item_number"] = m.group(2).strip()
        out["description"] = m.group(3).strip()
        out["quantity"] = m.group(4).replace(",", ".")
        out["unit_price"] = m.group(5).replace(",", ".")
        out["total_price"] = m.group(6).replace(",", ".")
    else:
        # Alternative pattern for when total price might be missing or different spacing
        parts = first_line.split()
        if len(parts) >= 5:
            out["item_number"] = parts[1]
            
            # Find where prices start (look for numbers with commas)
            price_indices = []
            for i, part in enumerate(parts):
                if re.match(r'^\d+,\d{2}$', part):
                    price_indices.append(i)
            
            if len(price_indices) >= 2:
                # Description is everything between item number and first price
                desc_start = 2
                desc_end = price_indices[0]
                out["description"] = ' '.join(parts[desc_start:desc_end])
                out["quantity"] = parts[price_indices[0]].replace(",", ".")
                out["unit_price"] = parts[price_indices[1]].replace(",", ".")
                if len(price_indices) >= 3:
                    out["total_price"] = parts[price_indices[2]].replace(",", ".")

    # Process continuation lines for lot number and additional description
    description_parts = [out["description"]] if out["description"] else []
    
    for ln in block[1:]:
        ln_s = ln.strip()

        # Lot number: "Lot number 00981164"
        lot_m = re.search(r'Lot number\s*([A-Za-z0-9\-/\s]+)', ln_s, re.IGNORECASE)
        if lot_m and not out["lot_number"]:
            out["lot_number"] = lot_m.group(1).strip()
            continue

        # Skip lines that are just "Index: A" or other metadata
        if re.match(r'Index:\s*[A-Z]', ln_s, re.IGNORECASE):
            continue
            
        # Skip empty lines and price-related lines
        if ln_s and not re.search(r'Value of goods|Package|Total/EUR', ln_s, re.IGNORECASE):
            description_parts.append(ln_s)

    # Combine description parts
    if description_parts:
        desc_clean = " - ".join([d for d in description_parts if d])
        desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
        out["description"] = desc_clean

    # Only return if we have essential data
    if out["item_number"] and out["description"] and out["quantity"]:
        return out

    return None


#Spiegel (via Simmank) OCR Needed

#Stengelin
def extract_stengelin_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Stengelin invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_stengelin_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_no = ""
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\s+ITEM NO\.\s+Article\s+piece\s+U-Price\s+EUR', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'item amount|package|total amount/EUR|Country of origin', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no))
                        current_block = []
                    break
                
                # Look for order number lines
                order_match = re.search(r'your order no\.\s*([^\s/]+)(?:/(\d{2}\.\d{2}\.\d{4}))?\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no))
                        current_block = []
                    current_order_no = order_match.group(1)
                    continue
                
                # Look for item lines (they start with numbers like "10 03.510-38")
                if re.match(r'^\d+\s+\d{2}\.\d{3}-\d{2}', line_clean):  # e.g., "10 03.510-38"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_no))
            
            # Process each item block
            for block, inv_data, order_no in item_blocks:
                item_data = _parse_stengelin_item_block(block, inv_data, order_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_stengelin_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Stengelin invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'dev_no': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "USA - WESTMONT, IL 60559 I N V O I C E NO. : 4500357"
        # The invoice number can appear in the middle of the address line
        inv_match = re.search(r'I N V O I C E\s*NO\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "Date : 25.02.2025"
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number: "Cust.-No. : 12413"
        cust_match = re.search(r'Cust\.?-No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract DEV number: "DEV-No. 9611278"
        dev_match = re.search(r'DEV-?No\.?\s*(\d+)', line_clean, re.IGNORECASE)
        if dev_match and not invoice_data['dev_no']:
            invoice_data['dev_no'] = dev_match.group(1)
    
    return invoice_data

def _parse_stengelin_item_block(block: List[str], invoice_data: Dict, order_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Stengelin invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'dev_no': invoice_data.get('dev_no', ''),
        'order_no': order_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'lot_number': '',
        'lst_number': '',
        'page': page_num + 1
    }
    
    # Parse first line: "10 03.510-38 N8821-17 Shoulder Retractor, 38 mm 3 40,57 121,71"
    first_line = block[0].strip()
    
    # Parse the item line
    item_match = re.search(r'^\d+\s+(\d{2}\.\d{3}-\d{2})\s+([^\s]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1)  # e.g., "03.510-38"
        item_data['description'] = item_match.group(3).strip()
        item_data['quantity'] = item_match.group(4)
        item_data['unit_price'] = item_match.group(5).replace(',', '.')
        item_data['total_price'] = item_match.group(6).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+(\d{2}\.\d{3}-\d{2})\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1)
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
            item_data['total_price'] = alt_match.group(5).replace(',', '.')
    
    # Extract lot number and LST number from the block
    for line in block:
        # Lot number: "lot number 04404842"
        lot_match = re.search(r'lot number\s*([A-Za-z0-9\-]+)', line, re.IGNORECASE)
        if lot_match and not item_data['lot_number']:
            item_data['lot_number'] = lot_match.group(1).strip()
        
        # LST number: "LST-NO:: A 337061 - GAD"
        lst_match = re.search(r'LST-?NO::?\s*(.+)', line, re.IGNORECASE)
        if lst_match and not item_data['lst_number']:
            item_data['lst_number'] = lst_match.group(1).strip()
    
    # For multi-line descriptions, combine additional lines
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that contain lot numbers, LST numbers, or other metadata
            if (line and 
                not re.search(r'lot number|LST-?NO|Datecode|Package No', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+\d{2}\.\d{3}-\d{2}', line)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data and non-zero quantity
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None


#Steris 
def extract_steris_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from STERIS invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_steris_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if 'ORDERED BACK ORD. SHIPPED' in line_clean:
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'SHIPPING & HANDLING CHARGES|SUBTOTAL|TAX TOTAL|Visit shop.steris.com', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break
                
                # Look for item lines (they start with numbers like "1 1.1 30808")
                if re.match(r'^\d+\s+\d+\.\d+\s+\d+', line_clean):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_steris_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_steris_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from STERIS invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'order_no': '',
        'sales_order_no': '',
        'ship_date': '',
        'tracking_number': ''
    }
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extract invoice number: "Phone 440-354-2600 12858942"
        if 'Phone 440-354-2600' in line_clean and not invoice_data['invoice_number']:
            # Extract the 8-digit number after the phone number
            inv_match = re.search(r'Phone 440-354-2600\s*(\d{8})', line_clean)
            if inv_match:
                invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "20-SEP-24" from the DATE PAGE line
        if 'DATE PAGE' in line_clean and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            date_match = re.search(r'(\d{2}-[A-Z]{3}-\d{2})', next_line)
            if date_match and not invoice_data['invoice_date']:
                date_str = date_match.group(1)
                # Convert date format
                month_map = {
                    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
                }
                try:
                    day, month, year = date_str.split('-')
                    if len(year) == 2:
                        year = '20' + year
                    invoice_data['invoice_date'] = f"{day}.{month_map.get(month.upper(), '01')}.{year}"
                except (ValueError, AttributeError):
                    invoice_data['invoice_date'] = date_str
        
        # Extract customer number: "399024" from the CUSTOMER NUMBER line
        if 'CUSTOMER NUMBER' in line_clean and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            cust_match = re.search(r'(\d+)\s+\d+', next_line)  # "399024 52247"
            if cust_match and not invoice_data['customer_number']:
                invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract purchase order number: "0017068" from PURCHASE ORDER NUMBER
        if 'PURCHASE ORDER NUMBER' in line_clean and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r'^\d+$', next_line):
                invoice_data['order_no'] = next_line
        
        # Extract sales order number: "18009881" from SALES ORDER NUMBER
        if 'SALES ORDER NUMBER' in line_clean and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r'^\d+$', next_line):
                invoice_data['sales_order_no'] = next_line
        
        # Extract ship date: "SHIP DATE 20-SEP-24"
        if 'SHIP DATE' in line_clean:
            ship_match = re.search(r'SHIP DATE\s*(\d{2}-[A-Z]{3}-\d{2})', line_clean, re.IGNORECASE)
            if ship_match:
                date_str = ship_match.group(1)
                try:
                    day, month, year = date_str.split('-')
                    if len(year) == 2:
                        year = '20' + year
                    invoice_data['ship_date'] = f"{day}.{month_map.get(month.upper(), '01')}.{year}"
                except (ValueError, AttributeError):
                    invoice_data['ship_date'] = date_str
        
        # Extract tracking number: "1Z67X3680394280668"
        tracking_match = re.search(r'(1Z[A-Z0-9]{16})', line_clean)
        if tracking_match and not invoice_data['tracking_number']:
            invoice_data['tracking_number'] = tracking_match.group(1)
    
    return invoice_data

def _parse_steris_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from STERIS invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': invoice_data.get('order_no', ''),
        'sales_order_no': invoice_data.get('sales_order_no', ''),
        'ship_date': invoice_data.get('ship_date', ''),
        'tracking_number': invoice_data.get('tracking_number', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'total_price': '',
        'page': page_num + 1
    }
    
    # First line: "1 1.1 30808 FLAT CAP VENT BROWN TINT DIA 0.625 X 25 25 0.00 14.84 371.00"
    first_line = block[0]
    
    # Parse using specific pattern for STERIS format
    # Format: ITEM ORDER ITEM_CODE DESCRIPTION QTY_ORDERED QTY_SHIPPED QTY_BACKORDER UNIT_PRICE TOTAL
    item_match = re.search(r'^\d+\s+\d+\.\d+\s+(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+[\d.]+\s+([\d.]+)\s+([\d.]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1)  # "30808"
        item_data['description'] = item_match.group(2).strip()  # "FLAT CAP VENT BROWN TINT DIA 0.625 X"
        item_data['quantity'] = item_match.group(4)  # Second "25" is quantity shipped
        item_data['unit_price'] = item_match.group(5)  # "14.84"
        item_data['total_price'] = item_match.group(6)  # "371.00"
    
    # If regex fails, try manual parsing
    if not item_data['item_code']:
        parts = first_line.split()
        if len(parts) >= 10:
            # Find the 5-digit item code
            for i, part in enumerate(parts):
                if re.match(r'^\d{5}$', part) and i >= 2:
                    item_data['item_code'] = part
                    
                    # Find where the numbers start (quantities and prices)
                    num_indices = []
                    for j in range(i+1, len(parts)):
                        if re.match(r'^\d+\.?\d*$', parts[j]):
                            num_indices.append(j)
                    
                    if len(num_indices) >= 5:
                        # The pattern is: description QTY_ORDERED QTY_SHIPPED QTY_BACKORDER UNIT_PRICE TOTAL
                        item_data['quantity'] = parts[num_indices[1]]  # Quantity shipped
                        item_data['unit_price'] = parts[num_indices[3]]  # Unit price
                        item_data['total_price'] = parts[num_indices[4]]  # Total price
                    
                    # Extract description
                    desc_end = num_indices[0] if num_indices else len(parts)
                    desc_parts = parts[i+1:desc_end]
                    item_data['description'] = ' '.join(desc_parts)
                    break
    
    # Add continuation lines to description (like "1IN [100/PK]")
    if len(block) > 1 and item_data['description']:
        for i in range(1, len(block)):
            line = block[i].strip()
            if line and not re.search(r'SHIPPING|SUBTOTAL|TAX', line, re.IGNORECASE):
                item_data['description'] += ' - ' + line
    
    # Only return if we have essential data
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None


#Stork
def extract_stork_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Stork invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_stork_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_no = ""
            current_lst_no = ""
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'Pos\.\s+Article\s+No\.\s+description\s+qty\.\s+each\s+price', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'total net|Shipping charges|total/EUR|payment', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst_no))
                        current_block = []
                    break
                
                # Look for order number lines
                order_match = re.search(r'your order no\.\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst_no))
                        current_block = []
                    current_order_no = order_match.group(1)
                    continue
                
                # Look for LST number lines
                lst_match = re.search(r'LST\.\s*No\.:\s*(.+)', line_clean, re.IGNORECASE)
                if lst_match:
                    current_lst_no = lst_match.group(1).strip()
                    continue
                
                # Look for item lines (they start with numbers like "1 54.468-01")
                if re.match(r'^\d+\s+\d{2}\.\d{3}-\d{2}', line_clean):  # e.g., "1 54.468-01"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst_no))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst_no))
            
            # Process each item block
            for block, inv_data, order_no, lst_no in item_blocks:
                item_data = _parse_stork_item_block(block, inv_data, order_no, lst_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_stork_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Stork invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "INVOICE NO. : 2230535"
        inv_match = re.search(r'INVOICE\s*NO\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "Date : 25.09.2023"
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number: "Cust.-No. : 12410"
        cust_match = re.search(r'Cust\.?-No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
    
    return invoice_data

def _parse_stork_item_block(block: List[str], invoice_data: Dict, order_no: str, lst_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Stork invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'order_no': order_no,
        'lst_no': lst_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'serial_number': '',
        'page': page_num + 1
    }
    
    # Parse first line: "1 54.468-01 Day Ear Hook Blunt 16.0cm 10 13,30 133,00"
    first_line = block[0].strip()
    
    # Parse the item line
    item_match = re.search(r'^\d+\s+(\d{2}\.\d{3}-\d{2})\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1)  # e.g., "54.468-01"
        item_data['description'] = item_match.group(2).strip()  # e.g., "Day Ear Hook Blunt 16.0cm"
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
        # Removed total_price extraction
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+(\d{2}\.\d{3}-\d{2})\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1)
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract serial number from the block: "S.Nr. 02182119 / Schmelze: 4021-5,0-011"
    for line in block:
        serial_match = re.search(r'S\.Nr\.\s*([^/\s]+)(?:\s*/\s*Schmelze:\s*([^/\s]+))?', line, re.IGNORECASE)
        if serial_match and not item_data['serial_number']:
            item_data['serial_number'] = serial_match.group(1).strip()
            if serial_match.group(2):
                item_data['serial_number'] += ' / ' + serial_match.group(2).strip()
    
    # For multi-line descriptions, combine additional lines (like "E7327-62")
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that contain serial numbers or look like new items
            if (line and 
                not re.search(r'S\.Nr\.|Schmelze:', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+\d{2}\.\d{3}-\d{2}', line) and
                not re.search(r'total net|Shipping charges', line, re.IGNORECASE)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data and non-zero quantity
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None


#Tontarra
def extract_tontarra_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Tontarra invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_tontarra_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_no = ""
            current_lst = ""
            current_hs_code = ""
            current_art_no = ""
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'Pos\.\s+Art\.No\.\s+Description\s+Lot number\s+qty\.\s+each\s+price', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'total net|packaging|total/EUR|terms of payment', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_hs_code, current_art_no))
                        current_block = []
                    break
                
                # Look for order number lines
                order_match = re.search(r'your order\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_hs_code, current_art_no))
                        current_block = []
                    current_order_no = order_match.group(1)
                    continue
                
                # Look for LST number lines
                lst_match = re.search(r'LST:\s*(.+)', line_clean, re.IGNORECASE)
                if lst_match:
                    current_lst = lst_match.group(1).strip()
                    continue
                
                # Look for HS code lines
                hs_match = re.search(r'HS code:\s*([^\s]+)', line_clean, re.IGNORECASE)
                if hs_match:
                    current_hs_code = hs_match.group(1).strip()
                    continue
                
                # Look for article number lines
                art_match = re.search(r'your art\.no\.:\s*([^\s]+)', line_clean, re.IGNORECASE)
                if art_match:
                    current_art_no = art_match.group(1).strip()
                    continue
                
                # Look for item lines (they start with numbers like "10 249-072-05ATCC" or "20 TONO/249-072-04")
                # ONLY CHANGE: Added forward slash to the pattern
                if re.match(r'^\d+\s+[A-Z0-9/-]', line_clean):  # e.g., "10 249-072-05ATCC" or "20 TONO/249-072-04"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_hs_code, current_art_no))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_hs_code, current_art_no))
            
            # Process each item block
            for block, inv_data, order_no, lst_no, hs_code, art_no in item_blocks:
                item_data = _parse_tontarra_item_block(block, inv_data, order_no, lst_no, hs_code, art_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_tontarra_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Tontarra invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'our_ref': '',
        'dev_no': '',
        'delivery_note': '',
        'delivery_date': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "INVOICE No. : 24243554"
        inv_match = re.search(r'INVOICE\s*No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "DATE : 24.09.2024"
        date_match = re.search(r'DATE\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number: "Customer : 17096"
        cust_match = re.search(r'Customer\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract our reference: "Our ref. : SUS"
        ref_match = re.search(r'Our ref\.?\s*:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if ref_match and not invoice_data['our_ref']:
            invoice_data['our_ref'] = ref_match.group(1)
        
        # Extract DEV number: "DEV: 9680515"
        dev_match = re.search(r'DEV:\s*(\d+)', line_clean, re.IGNORECASE)
        if dev_match and not invoice_data['dev_no']:
            invoice_data['dev_no'] = dev_match.group(1)
        
        # Extract delivery note and date: "DELIVERY NOTE No. 23244261 date 23.09.2024"
        delivery_match = re.search(r'DELIVERY NOTE\s*No\.?\s*(\d+)\s*date\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if delivery_match and not invoice_data['delivery_note']:
            invoice_data['delivery_note'] = delivery_match.group(1)
            invoice_data['delivery_date'] = delivery_match.group(2)
    
    return invoice_data

def _parse_tontarra_item_block(block: List[str], invoice_data: Dict, order_no: str, lst_no: str, hs_code: str, art_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Tontarra invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'our_ref': invoice_data.get('our_ref', ''),
        'dev_no': invoice_data.get('dev_no', ''),
        'delivery_note': invoice_data.get('delivery_note', ''),
        'delivery_date': invoice_data.get('delivery_date', ''),
        'order_no': order_no,
        'lst_no': lst_no,
        'hs_code': hs_code,
        'art_no': art_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot_number': '',
        'page': page_num + 1
    }
    
    # Parse first line: "10 249-072-05ATCC SWING-SYSTEM ® KERRISON Punch 82402970 3 699,40 1.154,01"
    # Or: "20 TONO/249-072-04 KERRISON SWING Rongeur; 40° up cut; T01-82102604 2 402,34 804,68"
    first_line = block[0].strip()
    
    # KEEP ORIGINAL REGEX PATTERNS BUT MAKE THEM MORE FLEXIBLE
    # Original pattern with extended character set for item codes
    item_match = re.search(r'^\d+\s+([A-Z0-9/-]+)\s+(.+?)\s+([A-Z0-9-]+)\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1)  # e.g., "249-072-05ATCC" or "TONO/249-072-04"
        item_data['description'] = item_match.group(2).strip()  # e.g., "SWING-SYSTEM ® KERRISON Punch"
        item_data['lot_number'] = item_match.group(3)  # e.g., "82402970" or "T01-82102604"
        item_data['quantity'] = item_match.group(4)
        item_data['unit_price'] = item_match.group(5).replace('.', '').replace(',', '.')  # Handle "699,40"
    
    # Alternative pattern for different formatting - KEEP ORIGINAL BUT EXTEND CHARACTER SET
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+([A-Z0-9/-]+)\s+(.+?)\s+([A-Z0-9-]+)\s+(\d+)\s+([\d.,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1)
            item_data['description'] = alt_match.group(2).strip()
            item_data['lot_number'] = alt_match.group(3)
            item_data['quantity'] = alt_match.group(4)
            item_data['unit_price'] = alt_match.group(5).replace('.', '').replace(',', '.')
    
    # FALLBACK: If still no match, use the original manual parsing approach
    if not item_data['item_code']:
        parts = first_line.split()
        if len(parts) >= 7:
            # The first part is the position number, second part is the item code
            item_data['item_code'] = parts[1]
            
            # Find where the lot number starts (look for alphanumeric codes)
            lot_number_index = -1
            for i in range(2, len(parts)):
                if re.match(r'^[A-Z0-9-]+$', parts[i]) and len(parts[i]) >= 6:
                    lot_number_index = i
                    break
            
            if lot_number_index != -1:
                # Description is everything between item code and lot number
                desc_parts = parts[2:lot_number_index]
                item_data['description'] = ' '.join(desc_parts)
                item_data['lot_number'] = parts[lot_number_index]
                
                # Quantities and prices come after lot number
                if len(parts) >= lot_number_index + 4:
                    item_data['quantity'] = parts[lot_number_index + 1]
                    item_data['unit_price'] = parts[lot_number_index + 2].replace('.', '').replace(',', '.')
    
    # For multi-line descriptions, combine additional lines - KEEP ORIGINAL LOGIC
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that look like new items or summary sections
            if (line and 
                not re.match(r'^\d+\s+[A-Z0-9/-]', line) and
                not re.search(r'total net|packaging|total/EUR', line, re.IGNORECASE)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data and non-zero quantity - KEEP ORIGINAL LOGIC
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None


#Total Titanium
def extract_total_titanium_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Total Titanium invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_total_titanium_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section (after the dashed line)
                if re.search(r'-{20,}Part # / Description-{20,}', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'Sub-total:|Shipping/Handling Charges:|Invoice Total:', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break
                
                # Look for item lines (they start with codes like "H-0397 -")
                if re.match(r'^[A-Z]-\d{4}\s+-', line_clean):  # e.g., "H-0397 -"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean and not re.match(r'^Job Traveler', line_clean, re.IGNORECASE):
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_total_titanium_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_total_titanium_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Total Titanium invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "Invoice #: 515947"
        inv_match = re.search(r'Invoice\s*#?:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "Invoice Date: 11/27/2024"
        date_match = re.search(r'Invoice Date:\s*(\d{1,2}/\d{1,2}/\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            # Convert US date format to European format DD.MM.YYYY
            us_date = date_match.group(1)
            parts = us_date.split('/')
            if len(parts) == 3:
                invoice_data['invoice_date'] = f"{parts[1]}.{parts[0]}.{parts[2]}"
        
        # Extract order number: "PO Number:0017242"
        po_match = re.search(r'PO Number:\s*(\d+)', line_clean, re.IGNORECASE)
        if po_match and not invoice_data['order_no']:
            invoice_data['order_no'] = po_match.group(1)
    
    return invoice_data

def _parse_total_titanium_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Total Titanium invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': invoice_data.get('order_no', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'page': page_num + 1
    }
    
    # Parse first line: "H-0397 - Paton Spatula and Spoon DBL-Ended 6mm Teardrop- 3 $64.68/ EA $194.04"
    first_line = block[0].strip()
    
    # Parse the item line
    item_match = re.search(r'^([A-Z]-\d{4})\s+-\s+(.+?)\s+(\d+)\s+\$([\d.]+)/\s*EA\s+\$([\d.]+)$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1)  # e.g., "H-0397"
        item_data['description'] = item_match.group(2).strip()  # e.g., "Paton Spatula and Spoon DBL-Ended 6mm Teardrop-"
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4)
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^([A-Z]-\d{4})\s+-\s+(.+?)\s+(\d+)\s+\$([\d.]+)/', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1)
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4)
    
    # If still no match, try a more flexible approach
    if not item_data['item_code']:
        parts = first_line.split()
        if len(parts) >= 4:
            # Look for the item code pattern "H-0397"
            for i, part in enumerate(parts):
                if re.match(r'^[A-Z]-\d{4}$', part):
                    item_data['item_code'] = part
                    
                    # Find quantity and price (look for numbers and dollar signs)
                    for j in range(i+1, len(parts)-2):
                        if (parts[j+1].startswith('$') and 
                            re.match(r'^\d+$', parts[j]) and 
                            '/ EA' in ' '.join(parts[j+1:j+3])):
                            item_data['quantity'] = parts[j]
                            # Extract price from "$64.68/ EA"
                            price_match = re.search(r'\$([\d.]+)', parts[j+1])
                            if price_match:
                                item_data['unit_price'] = price_match.group(1)
                            
                            # Description is everything between code and quantity
                            desc_parts = parts[i+1:j]
                            item_data['description'] = ' '.join(desc_parts)
                            break
                    break
    
    # For multi-line descriptions, combine additional lines
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that look like new items or summary sections
            if (line and 
                not re.match(r'^[A-Z]-\d{4}\s+-', line) and
                not re.match(r'^Job Traveler', line, re.IGNORECASE) and
                not re.search(r'Sub-total:|Shipping/Handling|Invoice Total:', line, re.IGNORECASE)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data and non-zero quantity
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None

#Ulrich Swiss OCR Needed

#Vinzenz Sattler
def extract_vinzenz_sattler_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Vinzenz Sattler invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_vinzenz_sattler_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_no = ""
            current_listing_no = ""
            current_your_item_no = ""
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'Order\s+Item\s+Qty\.\s+each\s+Total', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'Line Value|Package|Gross|Mandatory Notes', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_listing_no, current_your_item_no))
                        current_block = []
                    break
                
                # Look for order number lines: "0016929 / 10 - 22.08.2024"
                order_match = re.search(r'(\d{7})(?:\s+corrected)?\s*/\s*\d+\s*-\s*\d{2}\.\d{2}\.\d{4}', line_clean)
                if order_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_listing_no, current_your_item_no))
                        current_block = []
                    current_order_no = order_match.group(1)
                    continue
                
                # Look for listing number lines: "Listing No. B115819/79GAD"
                listing_match = re.search(r'Listing No\.\s*([^\s]+)', line_clean, re.IGNORECASE)
                if listing_match:
                    current_listing_no = listing_match.group(1).strip()
                    continue
                
                # Look for "Your Item No." lines: "Your Item No. C6668-50G"
                your_item_match = re.search(r'Your Item No\.\s*([^\s]+)', line_clean, re.IGNORECASE)
                if your_item_match:
                    current_your_item_no = your_item_match.group(1).strip()
                    continue
                
                # Look for item lines (they start with position numbers like "10 Item No. S 315 3206")
                if re.match(r'^\d+\s+Item No\.', line_clean):  # e.g., "10 Item No. S 315 3206"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_listing_no, current_your_item_no))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean:
                    # Check if this is a new order section
                    if re.search(r'\d{7}\s*/\s*\d+\s*-\s*\d{2}\.\d{2}\.\d{4}', line_clean):
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_listing_no, current_your_item_no))
                        current_block = []
                    else:
                        current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_listing_no, current_your_item_no))
            
            # Process each item block
            for block, inv_data, order_no, listing_no, your_item_no in item_blocks:
                item_data = _parse_vinzenz_sattler_item_block(block, inv_data, order_no, listing_no, your_item_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_vinzenz_sattler_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Vinzenz Sattler invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'dev_no': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "Invoice No. 2240447"
        inv_match = re.search(r'Invoice No\.?\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "from 18.09.2024"
        date_match = re.search(r'from\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number: "Customer No. 24004"
        cust_match = re.search(r'Customer No\.?\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract DEV number: "DEV : 8010376"
        dev_match = re.search(r'DEV\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if dev_match and not invoice_data['dev_no']:
            invoice_data['dev_no'] = dev_match.group(1)
    
    return invoice_data

def _parse_vinzenz_sattler_item_block(block: List[str], invoice_data: Dict, order_no: str, listing_no: str, your_item_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Vinzenz Sattler invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'dev_no': invoice_data.get('dev_no', ''),
        'order_no': order_no,
        'listing_no': listing_no,
        'your_item_no': your_item_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot_number': '',
        'page': page_num + 1
    }
    
    # Parse first line: "10 Item No. S 315 3206 10pcs. 15,26 152,60"
    first_line = block[0].strip()
    
    # Parse the item line - more flexible pattern
    item_match = re.search(r'^\d+\s+Item No\.\s+([A-Z]\s+\d+\s+\d+(?:\s+[A-Z]+)?)\s+(\d+)pcs\.\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(1).strip()  # e.g., "S 315 3206"
        item_data['quantity'] = item_match.group(2)
        item_data['unit_price'] = item_match.group(3).replace(',', '.')
    
    # Alternative pattern for different item code formats
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+Item No\.\s+([^\s]+(?:\s+[^\s]+)*)\s+(\d+)pcs\.\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = alt_match.group(1).strip()
            item_data['quantity'] = alt_match.group(2)
            item_data['unit_price'] = alt_match.group(3).replace(',', '.')
    
    # Extract lot number from the block: "Lot 10 x F 315 3206/88"
    for line in block:
        lot_match = re.search(r'Lot\s+\d+\s*x\s*([^\s/]+(?:\s*[^\s/]+)*)', line, re.IGNORECASE)
        if lot_match and not item_data['lot_number']:
            item_data['lot_number'] = lot_match.group(1).strip()
            break
    
    # Extract description from the entire block
    description_parts = []
    in_description = False
    
    for line in block:
        line_clean = line.strip()
        
        # Look for "Desc." lines
        if 'Desc.' in line_clean:
            desc_match = re.search(r'Desc\.\s*(.+)', line_clean, re.IGNORECASE)
            if desc_match:
                description_parts.append(desc_match.group(1).strip())
            in_description = True
        # Continue description if we're in a description section and line doesn't contain other metadata
        elif in_description and line_clean and not re.search(r'Lot\s+\d+\s*x|Item No\.|Listing No\.|Your Item No\.', line_clean, re.IGNORECASE):
            description_parts.append(line_clean)
        # Stop description if we hit lot number or other metadata
        elif re.search(r'Lot\s+\d+\s*x', line_clean, re.IGNORECASE):
            in_description = False
    
    # If no explicit "Desc." found, try to extract from continuation lines after item line
    if not description_parts and len(block) > 1:
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that contain metadata
            if (line and 
                not re.search(r'Lot\s+\d+\s*x|Listing No\.|Your Item No\.', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+Item No\.', line)):
                description_parts.append(line)
    
    if description_parts:
        item_data['description'] = ' - '.join(description_parts)
    
    # Only return if we have essential data and non-zero quantity
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None


#Vollrath
def extract_vollrath_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Vollrath invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_vollrath_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'Ordered\s+Shipped\s+U/M\s+Catalog No\.\s+Item Description', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'The following picking lists|Terms|Conditions|Seller warrants', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                    break
                
                # Look for item lines (they start with numbers)
                if re.match(r'^\d+\s+\d+\s+[A-Z]{2}\s+', line_clean):  # e.g., "11 11 EA 30042M"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean and not re.match(r'^\d+\s+\d+\s+[A-Z]{2}\s+', line_clean):
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_vollrath_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_vollrath_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Vollrath invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'order_no': '',
        'order_date': ''
    }
    
    # Look for the header line first
    header_found = False
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Find the header line
        if re.search(r'Customer Order Number.*Invoice No\.', line_clean):
            header_found = True
            continue
        
        # The next line after the header contains the data
        if header_found and re.match(r'^\d{7}\s+', line_clean):
            # This is the data line: "0016052 01/17/24 Sales Order 4468802 RI 01/19/24"
            parts = line_clean.split()
            
            # Extract fields based on expected positions
            if len(parts) >= 6:
                # Order number: "0016052" (first field)
                invoice_data['order_no'] = parts[0]
                
                # Order date: "01/17/24" -> "17.01.2024" (second field)
                if len(parts) > 1:
                    order_date = parts[1]
                    order_parts = order_date.split('/')
                    if len(order_parts) == 3:
                        year = '20' + order_parts[2] if len(order_parts[2]) == 2 else order_parts[2]
                        invoice_data['order_date'] = f"{order_parts[1]}.{order_parts[0]}.{year}"
                
                # Find invoice number - look for 7-digit number after "Sales Order"
                for j, part in enumerate(parts):
                    if part == 'Sales' and j + 2 < len(parts):
                        if re.match(r'^\d{7}$', parts[j + 2]):
                            invoice_data['invoice_number'] = parts[j + 2]
                            break
                
                # If not found with "Sales Order", look for any 7-digit number
                if not invoice_data['invoice_number']:
                    for part in parts:
                        if re.match(r'^\d{7}$', part) and part != invoice_data['order_no']:
                            invoice_data['invoice_number'] = part
                            break
                
                # Find invoice date - look for date pattern at the end
                for part in reversed(parts):
                    if re.match(r'^\d{2}/\d{2}/\d{2}$', part):
                        invoice_parts = part.split('/')
                        if len(invoice_parts) == 3:
                            year = '20' + invoice_parts[2] if len(invoice_parts[2]) == 2 else invoice_parts[2]
                            invoice_data['invoice_date'] = f"{invoice_parts[1]}.{invoice_parts[0]}.{year}"
                        break
            
            # Reset header flag after processing
            header_found = False
    
    # Alternative approach if the above fails - look for specific patterns
    if not invoice_data['invoice_number'] or not invoice_data['invoice_date']:
        for line in lines:
            line_clean = line.strip()
            
            # Look for invoice number pattern
            if not invoice_data['invoice_number']:
                inv_match = re.search(r'(\d{7})(?:\s+[A-Z]+\s+\d{2}/\d{2}/\d{2})?$', line_clean)
                if inv_match and inv_match.group(1) != invoice_data['order_no']:
                    invoice_data['invoice_number'] = inv_match.group(1)
            
            # Look for invoice date pattern at the end of lines
            if not invoice_data['invoice_date']:
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})$', line_clean)
                if date_match:
                    date_parts = date_match.group(1).split('/')
                    if len(date_parts) == 3:
                        year = '20' + date_parts[2] if len(date_parts[2]) == 2 else date_parts[2]
                        invoice_data['invoice_date'] = f"{date_parts[1]}.{date_parts[0]}.{year}"
    
    return invoice_data

def _parse_vollrath_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Vollrath invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'order_no': invoice_data.get('order_no', ''),
        'order_date': invoice_data.get('order_date', ''),
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'page': page_num + 1
    }
    
    # Parse first line: "11 11 EA 30042M STERILIZATION TRAY/BATH SET 4" PAN 22 GA 45.9000 EA 504.90"
    first_line = block[0].strip()
    
    # Use regex to parse the specific structure
    # Format: QTY QTY EA ITEM_CODE DESCRIPTION UNIT_PRICE EA TOTAL
    item_match = re.search(r'^(\d+)\s+\d+\s+EA\s+([A-Z0-9]+)\s+(.+?)\s+([\d.]+)\s+EA\s+[\d.]+$', first_line)
    
    if item_match:
        item_data['quantity'] = item_match.group(1)  # First number is quantity
        item_data['item_code'] = item_match.group(2)  # e.g., "30042M"
        item_data['description'] = item_match.group(3).strip()  # e.g., "STERILIZATION TRAY/BATH SET 4" PAN 22 GA"
        item_data['unit_price'] = item_match.group(4)  # e.g., "45.9000"
    
    # Alternative pattern if the first one fails
    if not item_data['item_code']:
        # Try splitting and manual parsing
        parts = first_line.split()
        if len(parts) >= 7:
            # First part is quantity: "11"
            item_data['quantity'] = parts[0]
            
            # Find "EA" positions to locate fields
            ea_positions = [i for i, part in enumerate(parts) if part == 'EA']
            
            if len(ea_positions) >= 2:
                # Item code is after first "EA"
                if ea_positions[0] + 1 < len(parts):
                    item_data['item_code'] = parts[ea_positions[0] + 1]
                
                # Unit price is before second "EA"
                if ea_positions[1] - 1 >= 0:
                    item_data['unit_price'] = parts[ea_positions[1] - 1]
                
                # Description is between item code and unit price
                desc_start = ea_positions[0] + 2
                desc_end = ea_positions[1] - 1
                if desc_end > desc_start:
                    item_data['description'] = ' '.join(parts[desc_start:desc_end])
    
    # For multi-line descriptions, combine additional lines (like "9393-09")
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that look like new items or summary sections
            if (line and 
                not re.match(r'^\d+\s+\d+\s+[A-Z]{2}\s+', line) and
                not re.search(r'The following picking lists|Terms|Conditions', line, re.IGNORECASE)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data and non-zero quantity
    # Skip broken case charges and other non-product items
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0' and
        not re.search(r'Broken Case Charge', item_data['description'], re.IGNORECASE)):
        return item_data
    
    return None


#WEBA
def extract_weba_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from WEBA invoice format.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            
            # Extract invoice-level info
            invoice_data = _extract_weba_invoice_info(lines)
            
            # Find item blocks
            item_blocks = []
            current_block = []
            in_items_section = False
            current_order_no = ""
            current_lst = ""
            current_art_no = ""
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'POS\s+ARTICLE/\s+description\s+qty\.\s+each\s+price', line_clean):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Stop at summary sections
                if re.search(r'total net|package:|total/EUR|carry-over|T O T A L:', line_clean, re.IGNORECASE):
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_art_no))
                        current_block = []
                    break
                
                # Look for order number lines
                order_match = re.search(r'your order no\.\s*([^\s-]+)\s*-\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
                if order_match:
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_art_no))
                        current_block = []
                    current_order_no = order_match.group(1)
                    continue
                
                # Look for LST number lines
                lst_match = re.search(r'LST:\s*([^\s-]+(?:\s*-\s*[^\s]+)?)', line_clean, re.IGNORECASE)
                if lst_match:
                    current_lst = lst_match.group(1).strip()
                    continue
                
                # Look for article number lines
                art_match = re.search(r'your art\.-?no\.:\s*([^\s]+)', line_clean, re.IGNORECASE)
                if art_match:
                    current_art_no = art_match.group(1).strip()
                    continue
                
                # Look for item lines (they start with numbers like "10 WB 70-013")
                if re.match(r'^\d+\s+WB\s+', line_clean):  # e.g., "10 WB 70-013"
                    if current_block:
                        item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_art_no))
                    current_block = [line_clean]
                # Continue collecting description lines for the current item
                elif current_block and line_clean:
                    current_block.append(line_clean)
            
            if current_block:
                item_blocks.append((current_block, invoice_data.copy(), current_order_no, current_lst, current_art_no))
            
            # Process each item block
            for block, inv_data, order_no, lst_no, art_no in item_blocks:
                item_data = _parse_weba_item_block(block, inv_data, order_no, lst_no, art_no, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

def _extract_weba_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from WEBA invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer_number': '',
        'dev_no': '',
        'our_sign': '',
        'cred_no': ''
    }
    
    for line in lines:
        line_clean = line.strip()
        
        # Extract invoice number: "INVOICE NO. : 510916"
        inv_match = re.search(r'INVOICE\s*NO\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date: "Date : 27.06.2023"
        date_match = re.search(r'Date\s*:\s*(\d{2}\.\d{2}\.\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer number: "Cust.-No. : 56644"
        cust_match = re.search(r'Cust\.?-No\.?\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer_number']:
            invoice_data['customer_number'] = cust_match.group(1)
        
        # Extract DEV number: "DEV : 8010282"
        dev_match = re.search(r'DEV\s*:\s*(\d+)', line_clean, re.IGNORECASE)
        if dev_match and not invoice_data['dev_no']:
            invoice_data['dev_no'] = dev_match.group(1)
        
        # Extract our sign: "Our sign : TSC"
        sign_match = re.search(r'Our sign\s*:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if sign_match and not invoice_data['our_sign']:
            invoice_data['our_sign'] = sign_match.group(1)
        
        # Extract credit number: "Cred.No. : 02-2500101"
        cred_match = re.search(r'Cred\.?No\.?\s*:\s*([^\s]+)', line_clean, re.IGNORECASE)
        if cred_match and not invoice_data['cred_no']:
            invoice_data['cred_no'] = cred_match.group(1)
    
    return invoice_data

def _parse_weba_item_block(block: List[str], invoice_data: Dict, order_no: str, lst_no: str, art_no: str, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from WEBA invoice"""
    if not block:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer_number': invoice_data['customer_number'],
        'dev_no': invoice_data.get('dev_no', ''),
        'our_sign': invoice_data.get('our_sign', ''),
        'cred_no': invoice_data.get('cred_no', ''),
        'order_no': order_no,
        'lst_no': lst_no,
        'art_no': art_no,
        'item_code': '',
        'description': '',
        'quantity': '',
        'unit_price': '',
        'lot_number': '',
        'page': page_num + 1
    }
    
    # Parse first line: "10 WB 70-013 Citelly Rongeur 2,0 mm bite 1 185,60 185,60"
    first_line = block[0].strip()
    
    # Parse the item line
    item_match = re.search(r'^\d+\s+WB\s+([^\s]+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+[\d,]+$', first_line)
    
    if item_match:
        item_data['item_code'] = "WB " + item_match.group(1)  # e.g., "WB 70-013"
        item_data['description'] = item_match.group(2).strip()  # e.g., "Citelly Rongeur 2,0 mm bite"
        item_data['quantity'] = item_match.group(3)
        item_data['unit_price'] = item_match.group(4).replace(',', '.')
    
    # Alternative pattern for different formatting
    if not item_data['item_code']:
        alt_match = re.search(r'^\d+\s+WB\s+([^\s]+)\s+(.+?)\s+(\d+)\s+([\d,]+)', first_line)
        if alt_match:
            item_data['item_code'] = "WB " + alt_match.group(1)
            item_data['description'] = alt_match.group(2).strip()
            item_data['quantity'] = alt_match.group(3)
            item_data['unit_price'] = alt_match.group(4).replace(',', '.')
    
    # Extract lot number from the block: "Lot number 07/2016-023 / WE"
    for line in block:
        lot_match = re.search(r'Lot number\s*([^/\n]+(?:\s*/\s*[^/\n]+)*)', line, re.IGNORECASE)
        if lot_match and not item_data['lot_number']:
            item_data['lot_number'] = lot_match.group(1).strip()
            break
    
    # For multi-line descriptions, combine additional lines
    if len(block) > 1 and item_data['description']:
        additional_desc = []
        for i in range(1, len(block)):
            line = block[i].strip()
            # Skip lines that contain lot numbers or look like new items
            if (line and 
                not re.search(r'Lot number', line, re.IGNORECASE) and
                not re.match(r'^\d+\s+WB\s+', line) and
                not re.search(r'total net|package:|carry-over', line, re.IGNORECASE)):
                additional_desc.append(line)
        
        if additional_desc:
            item_data['description'] += ' - ' + ' '.join(additional_desc)
    
    # Only return if we have essential data and non-zero quantity
    if (item_data['item_code'] and item_data['description'] and 
        item_data['quantity'] and item_data['quantity'] != '0'):
        return item_data
    
    return None


#Y&W
def extract_yw_invoice_data(pdf_content: bytes) -> List[Dict]:
    """
    Extract data from Y&W invoice format.
    Handles both layout variations automatically.
    Returns a list of dictionaries containing the extracted data for each line item.
    """
    extracted_data = []
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Determine invoice format based on content
        if "ITEM# QTY LOT# DESCRIPTION" in full_text:
            return _extract_yw_format_v2(full_text)
        else:
            return _extract_yw_format_v1(full_text)

def _extract_yw_format_v1(full_text: str) -> List[Dict]:
    """Extract data from Y&W Format V1 (like Invoice #95597)"""
    extracted_data = []
    lines = full_text.split("\n")
    
    # Extract invoice-level info
    invoice_data = _extract_yw_invoice_info(lines)
    
    # Find all item sections across all pages
    item_sections = _extract_item_sections_v1(lines)
    
    # Track processed items to avoid duplicates
    processed_items = set()
    
    # Process each item section
    for item_lines in item_sections:
        item_data = _parse_yw_item_lines_v1(item_lines, invoice_data)
        if item_data:
            # Create a unique key for this item to avoid duplicates
            item_key = f"{item_data['item_number']}_{item_data['item_code']}_{item_data['order_no']}_{item_data['packing_list']}"
            
            if item_key not in processed_items:
                processed_items.add(item_key)
                extracted_data.append(item_data)
    
    return extracted_data

def _extract_item_sections_v1(lines: List[str]) -> List[List[str]]:
    """Extract item sections from V1 format"""
    item_sections = []
    current_section = []
    in_items_section = False
    found_items = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Look for the start of the items section
        if re.search(r'Item\s+Quantity\s+Description\s+Revision\s+Unit Price\s+Amount', line_clean):
            in_items_section = True
            found_items = True
            continue
        
        if not in_items_section:
            continue
        
        # Stop at summary sections (but only after we've found items)
        if found_items and re.search(r'Sub-total:|Sales Tax:|Shipping Charges:|Invoice Total:', line_clean, re.IGNORECASE):
            if current_section:
                item_sections.append(current_section)
                current_section = []
            in_items_section = False
            continue
        
        # Look for item lines (they start with numbers like "1 2 E7210-44E")
        if re.match(r'^\d+\s+\d+\s+[A-Z]', line_clean):  # e.g., "1 2 E7210-44E"
            if current_section:
                item_sections.append(current_section)
            current_section = [line_clean]
        elif current_section and line_clean:
            # Continue collecting lines for the current item
            # Skip page headers/footers
            if not _is_page_header_footer(line_clean):
                current_section.append(line_clean)
    
    if current_section:
        item_sections.append(current_section)
    
    return item_sections

def _is_page_header_footer(line: str) -> bool:
    """Check if a line is a page header or footer"""
    line_clean = line.strip()
    # Page headers/footers typically contain dates, page numbers, or report generated info
    if (re.search(r'Report Generated:', line_clean, re.IGNORECASE) or
        re.search(r'Page \d+ of \d+', line_clean, re.IGNORECASE) or
        re.search(r'\d{1,2}:\d{2}:\d{2}[AP]M', line_clean, re.IGNORECASE)):
        return True
    return False

def _parse_yw_item_lines_v1(item_lines: List[str], invoice_data: Dict) -> Optional[Dict]:
    """Parse item lines from V1 format"""
    if not item_lines:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer': invoice_data['customer'],
        'po_number': invoice_data['po_number'],
        'lot_no': invoice_data['lot_no'],
        'order_no': '',
        'packing_list': '',
        'item_number': '',
        'quantity': '',
        'item_code': '',
        'description': '',
        'unit_price': '',
    }
    
    # Parse first line (main item line)
    first_line = item_lines[0].strip()
    
    # Improved regex pattern for V1 format
    # Pattern for: "1 2 E7210-44E - FARRIOR EAR SPEC, OVAL ANGLED $200.00/ LOT $200.00"
    item_match = re.search(r'^(\d+)\s+(\d+)\s+([A-Z][A-Z0-9-]+)\s*-?\s*(.+?)\s*\$?([\d,]+\.\d{2})/?\s*[A-Z]+\s*\$?[\d,]+\.\d{2}', first_line)
    
    if not item_match:
        # Alternative pattern for different formatting
        item_match = re.search(r'^(\d+)\s+(\d+)\s+([A-Z][A-Z0-9-]+)\s*(.+?)\s*\$?([\d,]+\.\d{2})', first_line)
    
    if item_match:
        item_data['item_number'] = item_match.group(1)
        item_data['quantity'] = item_match.group(2)
        item_data['item_code'] = item_match.group(3)
        item_data['description'] = item_match.group(4).strip()
        item_data['unit_price'] = item_match.group(5).replace(',', '')
    
    # Process additional lines for description continuation and order/packing info
    for line in item_lines[1:]:
        line_clean = line.strip()
        
        # Skip page headers/footers
        if _is_page_header_footer(line_clean):
            continue
            
        # Look for order number
        order_match = re.search(r'Order No:\s*(\d+)', line_clean, re.IGNORECASE)
        if order_match and not item_data['order_no']:
            item_data['order_no'] = order_match.group(1)
            continue
        
        # Look for packing list
        packing_match = re.search(r'Packing List:\s*(\d+)', line_clean, re.IGNORECASE)
        if packing_match and not item_data['packing_list']:
            item_data['packing_list'] = packing_match.group(1)
            continue
        
        # If line doesn't contain order/packing info and is not empty, add to description
        if (line_clean and 
            not re.search(r'Order No:|Packing List:', line_clean, re.IGNORECASE) and
            not re.match(r'^\d+\s+\d+\s+[A-Z]', line_clean) and
            not _is_page_header_footer(line_clean)):
            item_data['description'] += ' ' + line_clean
    
    # Clean up description - remove price patterns if they ended up in description
    item_data['description'] = re.sub(r'\$?[\d,]+\.\d{2}/?\s*[A-Z]*\s*\$?[\d,]*\.?\d*', '', item_data['description']).strip()
    item_data['description'] = re.sub(r'\s+', ' ', item_data['description']).strip()
    
    return item_data if item_data['item_code'] and item_data['quantity'] else None

def _extract_yw_format_v2(full_text: str) -> List[Dict]:
    """Extract data from Y&W Format V2 (like Invoice #96833)"""
    extracted_data = []
    lines = full_text.split("\n")
    
    # Extract invoice-level info
    invoice_data = _extract_yw_invoice_info(lines)
    
    # Find all item sections
    item_sections = _extract_item_sections_v2(lines)
    
    # Track processed items to avoid duplicates
    processed_items = set()
    
    # Process each item section
    for item_lines in item_sections:
        item_data = _parse_yw_item_lines_v2(item_lines, invoice_data)
        if item_data:
            # Create a unique key for this item to avoid duplicates
            item_key = f"{item_data['item_number']}_{item_data['item_code']}_{item_data['order_no']}_{item_data['packing_list']}"
            
            if item_key not in processed_items:
                processed_items.add(item_key)
                extracted_data.append(item_data)
    
    return extracted_data

def _extract_item_sections_v2(lines: List[str]) -> List[List[str]]:
    """Extract item sections from V2 format"""
    item_sections = []
    current_section = []
    in_items_section = False
    found_items = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Look for the start of the items section in V2 format
        if re.search(r'Item\s+Quantity\s+Description\s+Revision\s+Unit Price\s+Amount', line_clean):
            in_items_section = True
            found_items = True
            continue
        
        if not in_items_section:
            # Also check for the ITEM# QTY LOT# DESCRIPTION format
            if re.search(r'ITEM#\s+QTY\s+LOT#\s+DESCRIPTION', line_clean):
                in_items_section = True
                found_items = True
            continue
        
        # Stop at summary sections (but only after we've found items)
        if found_items and re.search(r'Sub-total:|Sales Tax:|Shipping Charges:|Invoice Total:', line_clean, re.IGNORECASE):
            if current_section:
                item_sections.append(current_section)
                current_section = []
            in_items_section = False
            continue
        
        # Look for item lines in V2 format
        if re.match(r'^\d+\s+\d+\s+NOVO SURGICAL INSTRUMENTS', line_clean):
            if current_section:
                item_sections.append(current_section)
            current_section = [line_clean]
        elif current_section and line_clean:
            # Continue collecting lines for the current item
            # Skip page headers/footers
            if not _is_page_header_footer(line_clean):
                current_section.append(line_clean)
    
    if current_section:
        item_sections.append(current_section)
    
    return item_sections

def _parse_yw_item_lines_v2(item_lines: List[str], invoice_data: Dict) -> Optional[Dict]:
    """Parse item lines from V2 format"""
    if not item_lines:
        return None
    
    item_data = {
        'invoice_date': invoice_data['invoice_date'],
        'invoice_number': invoice_data['invoice_number'],
        'customer': invoice_data['customer'],
        'po_number': invoice_data['po_number'],
        'lot_no': invoice_data['lot_no'],
        'order_no': '',
        'packing_list': '',
        'item_number': '',
        'quantity': '',
        'item_code': 'NOVO SURGICAL INSTRUMENTS',
        'description': '',
        'unit_price': '',
    }
    
    # Parse first line
    first_line = item_lines[0].strip()
    
    # Pattern for: "1 6 NOVO SURGICAL INSTRUMENTS - Ebonize $200.00/ LOT $200.00"
    item_match = re.search(r'^(\d+)\s+(\d+)\s+NOVO SURGICAL INSTRUMENTS\s*-?\s*(.+?)\s*\$?([\d,]+\.\d{2})/?\s*[A-Z]+\s*\$?[\d,]+\.\d{2}', first_line)
    
    if item_match:
        item_data['item_number'] = item_match.group(1)
        item_data['quantity'] = item_match.group(2)
        item_data['description'] = f"NOVO SURGICAL INSTRUMENTS - {item_match.group(3).strip()}"
        item_data['unit_price'] = item_match.group(4).replace(',', '')
    
    # Process additional lines for order/packing info
    for line in item_lines[1:]:
        line_clean = line.strip()
        
        # Skip page headers/footers
        if _is_page_header_footer(line_clean):
            continue
            
        # Look for order number
        order_match = re.search(r'Order No:\s*(\d+)', line_clean, re.IGNORECASE)
        if order_match and not item_data['order_no']:
            item_data['order_no'] = order_match.group(1)
            continue
        
        # Look for packing list
        packing_match = re.search(r'Packing List:\s*(\d+)', line_clean, re.IGNORECASE)
        if packing_match and not item_data['packing_list']:
            item_data['packing_list'] = packing_match.group(1)
            continue
    
    return item_data if item_data['quantity'] else None

def _extract_yw_invoice_info(lines: List[str]) -> Dict[str, str]:
    """Extract invoice information from Y&W invoice"""
    invoice_data = {
        'invoice_number': '',
        'invoice_date': '',
        'customer': '',
        'po_number': '',
        'lot_no': '',
        'ship_to_address': '',
        'sold_to_address': '',
        'terms': '',
        'salesman': ''
    }
    
    ship_to_lines = []
    sold_to_lines = []
    in_ship_to = False
    in_sold_to = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Skip page headers/footers
        if _is_page_header_footer(line_clean):
            continue
            
        # Extract invoice number
        inv_match = re.search(r'Invoice Number:\s*(\d+)', line_clean, re.IGNORECASE)
        if inv_match and not invoice_data['invoice_number']:
            invoice_data['invoice_number'] = inv_match.group(1)
        
        # Extract invoice date
        date_match = re.search(r'Invoice Date:\s*(\d{2}/\d{2}/\d{4})', line_clean, re.IGNORECASE)
        if date_match and not invoice_data['invoice_date']:
            invoice_data['invoice_date'] = date_match.group(1)
        
        # Extract customer
        cust_match = re.search(r'Customer:\s*([^\n]+)', line_clean, re.IGNORECASE)
        if cust_match and not invoice_data['customer']:
            invoice_data['customer'] = cust_match.group(1).strip()
        
        # Extract PO number
        po_match = re.search(r'PO Number:\s*([^\n]+)', line_clean, re.IGNORECASE)
        if po_match and not invoice_data['po_number']:
            invoice_data['po_number'] = po_match.group(1).strip()
        
        # Extract JOB/LOT numbers - renamed to lot_no
        job_match = re.search(r'JOB/LOT#\s*([^\n]+)', line_clean, re.IGNORECASE)
        if job_match and not invoice_data['lot_no']:
            invoice_data['lot_no'] = job_match.group(1).strip()
        
        # Extract terms
        terms_match = re.search(r'Terms:\s*([^\n]+)', line_clean, re.IGNORECASE)
        if terms_match and not invoice_data['terms']:
            invoice_data['terms'] = terms_match.group(1).strip()
        
        # Extract salesman
        salesman_match = re.search(r'Salesman:\s*([^\n]+)', line_clean, re.IGNORECASE)
        if salesman_match and not invoice_data['salesman']:
            invoice_data['salesman'] = salesman_match.group(1).strip()
        
        # Extract ship to address
        if 'Ship' in line_clean and 'To:' in line_clean:
            in_ship_to = True
            in_sold_to = False
            continue
        elif 'Sold' in line_clean and 'To:' in line_clean:
            in_sold_to = True
            in_ship_to = False
            continue
        elif 'Invoice Number:' in line_clean:
            in_ship_to = False
            in_sold_to = False
        
        if in_ship_to and line_clean and not any(x in line_clean for x in ['Ship', 'To:']):
            ship_to_lines.append(line_clean)
        elif in_sold_to and line_clean and not any(x in line_clean for x in ['Sold', 'To:']):
            sold_to_lines.append(line_clean)
    
    # Combine address lines
    if ship_to_lines:
        invoice_data['ship_to_address'] = ' '.join(ship_to_lines).strip()
    if sold_to_lines:
        invoice_data['sold_to_address'] = ' '.join(sold_to_lines).strip()
    
    return invoice_data


def process_pdfs(pdf_files, vendor):
    """
    Process multiple PDF files and return combined data
    """
    all_data = []
    progress_bar = st.progress(0)

    for index, pdf_file in enumerate(pdf_files):
        pdf_content = pdf_file.read()

        if vendor == "Bumüller GmbH":
            data = extract_bumuller_invoice_data(pdf_content)
        elif vendor == "Avalign German Specialty Instruments":
            data = extract_avalign_invoice_data(pdf_content)
        elif vendor == "A. Milazzo Medizintechnik GmbH":
            data = extract_amilazzo_invoice_data(pdf_content)
        elif vendor == "Ackermann":
            data = extract_ackermann_invoice_data(pdf_content)
        elif vendor == 'Betzler':
            data = extract_betzler_invoice_data(pdf_content)
        elif vendor == 'Hipp':
            data = extract_hipp_invoice_data(pdf_content)
        elif vendor == 'Aspen':
            data = extract_aspen_invoice_data(pdf_content)
        elif vendor == 'Bahadir':
            data = extract_bahadir_invoice_data(pdf_content)
        elif vendor == 'Bauer & Haselbarth':
            data = extract_bauer_hasselbarth_invoice_data(pdf_content)
        elif vendor == 'Biselli':
            data = extract_biselli_invoice_data(pdf_content)
        elif vendor == 'Blache':
            data = extract_blache_invoice_data(pdf_content)
        elif vendor == 'Carl Teufel':
            data = extract_carl_teufel_invoice_data(pdf_content)
        elif vendor == 'Chirmed':
            data = extract_chirmed_invoice_data(pdf_content)
        elif vendor == 'CM Instrumente':
            data = extract_cm_instrumente_invoice_data(pdf_content)
        elif vendor == 'CMF':
            data = extract_cmf_invoice_data(pdf_content)
        elif vendor == 'Dannoritzer':
            data = extract_dannoritzer_invoice_data(pdf_content)
        elif vendor == 'Dausch':
            data = extract_dausch_invoice_data(pdf_content)
        elif vendor == 'Denzel':
            data = extract_denzel_invoice_data(pdf_content)
        elif vendor == 'Efinger':
            data = extract_efinger_invoice_data(pdf_content)
        elif vendor == 'ELMED':
            data = extract_elmed_invoice_data(pdf_content)
        elif vendor == 'Ermis MedTech':
            data = extract_ermis_invoice_data(pdf_content)
        elif vendor == 'ESMA':
            data = extract_esma_invoice_data(pdf_content)
        elif vendor == 'EUROMED':
            data = extract_euromed_invoice_data(pdf_content)
        elif vendor == 'Faulhaber':
            data = extract_faulhaber_invoice_data(pdf_content)
        elif vendor == 'Fetzer':
            data = extract_fetzer_invoice_data(pdf_content)
        elif vendor == 'Gebrüder':
            data = extract_gebruder_invoice_data(pdf_content)
        elif vendor == 'Geister':
            data = extract_geister_invoice_data(pdf_content)
        elif vendor == 'Georg Alber':
            data = extract_georgalber_invoice_data(pdf_content)
        elif vendor == 'Getsch+Hiller':
            data = extract_getschhiller_invoice_data(pdf_content)
        elif vendor == 'Gordon Brush':
            data = extract_gordonbrush_invoice_data(pdf_content)
        elif vendor == 'Gunter Bissinger Medizintechnik GmbH':
            data = extract_bissinger_invoice_data(pdf_content)
        elif vendor == 'Hafner':
            data = extract_hafner_invoice_data(pdf_content)
        elif vendor == 'Heiss-Medical':
            data = extract_heissmedical_invoice_data(pdf_content)
        elif vendor == 'Hermann':
            data = extract_hermann_invoice_data(pdf_content)
        elif vendor == 'HGR':
            data = extract_hgr_invoice_data(pdf_content)
        elif vendor == 'Holger':
            data = extract_holger_invoice_data(pdf_content)
        elif vendor == 'ILG':
            data = extract_ilg_invoice_data(pdf_content)
        elif vendor == 'Josef Betzler':
            data = extract_josef_betzler_invoice_data(pdf_content)
        elif vendor == 'KAPP':
            data = extract_kapp_invoice_data(pdf_content)
        elif vendor == 'Kohler':
            data = extract_kohler_invoice_data(pdf_content)
        elif vendor == 'Medin':
            data = extract_medin_invoice_data(pdf_content)
        elif vendor == 'Microqore':
            data = extract_microqore_invoice_data(pdf_content)
        elif vendor == 'Otto Ruttgers':
            data = extract_otto_ruttgers_invoice_data(pdf_content)
        elif vendor == 'Phoenix Instruments':
            data = extract_phoenix_invoice_data(pdf_content)
        elif vendor == 'Precision Medical':
            data = extract_precision_medical_invoice_data(pdf_content)
        elif vendor == 'Rebstock':
            data = extract_rebstock_invoice_data(pdf_content)
        elif vendor == 'Rica':
            data = extract_rica_invoice_data(pdf_content)
        elif vendor == 'Rudischhauser':
            data = extract_rudischhauser_invoice_data(pdf_content)
        elif vendor == 'Rudolf Storz':
            data = extract_rudolfstorz_invoice_data(pdf_content)
        elif vendor == 'Ruhof':
            data = extract_ruhof_invoice_data(pdf_content)
        elif vendor == 'S.u.A. Martin':
            data = extract_sua_invoice_data(pdf_content)
        elif vendor == 'Schmid':
            data = extract_schmid_invoice_data(pdf_content)
        elif vendor == 'SGS North America':
            data = extract_sgs_invoice_data(pdf_content)
        elif vendor == 'SIBEL':
            data = extract_sibel_invoice_data(pdf_content)
        elif vendor == 'Siema':
            data = extract_siema_invoice_data(pdf_content)
        elif vendor == 'SignTech':
            data = extract_sigtech_invoice_data(pdf_content)
        elif vendor == 'SIS':
            data = extract_sis_invoice_data(pdf_content)
        elif vendor == 'Sitec':
            data = extract_sitec_invoice_data(pdf_content)
        elif vendor == 'SMT':
            data = extract_smt_invoice_data(pdf_content)
        elif vendor == 'Stengelin':
            data = extract_stengelin_invoice_data(pdf_content)
        elif vendor == 'Steris':
            data = extract_steris_invoice_data(pdf_content)
        elif vendor == 'Stork':
            data = extract_stork_invoice_data(pdf_content)
        elif vendor == 'Tontarra':
            data = extract_tontarra_invoice_data(pdf_content)
        elif vendor == 'Total Titanium':
            data = extract_total_titanium_invoice_data(pdf_content)
        elif vendor == 'Vinzenz Sattler':
            data = extract_vinzenz_sattler_invoice_data(pdf_content)
        elif vendor == 'Vollrath':
            data = extract_vollrath_invoice_data(pdf_content)
        elif vendor == 'WEBA':
            data = extract_weba_invoice_data(pdf_content)
        elif vendor == 'Y&W':
            data = extract_yw_invoice_data(pdf_content)
        else:
            continue
        all_data.extend(data)

        # Update progress bar
        progress = (index + 1) / len(pdf_files)
        progress_bar.progress(progress)

    progress_bar.empty()
    return all_data
    

# Streamlit interface
st.title("Invoice Data Extraction Tool")

# Vendor selection dropdown
vendor_options = [
    "Bumüller GmbH",
    "Avalign German Specialty Instruments",
    "A. Milazzo Medizintechnik GmbH",
    "Ackermann",
    "Betzler",
    "Hipp",
    "Aspen",
    "Bahadir",
    "Bauer & Haselbarth",
    "Biselli",
    "Blache",
    "Carl Teufel",
    "Chirmed",
    "CM Instrumente",
    "CMF",
    "Dannoritzer",
    "Dausch",
    "Denzel",
    "Efinger",
    "ELMED",
    "Ermis MedTech",
    "ESMA",
    "EUROMED",
    "Faulhaber",
    "Fetzer",
    "Gebrüder",
    "Geister",
    "Georg Alber",
    "Getsch+Hiller",
    "Gordon Brush",
    "Gunter Bissinger Medizintechnik GmbH",
    "Hafner",
    "Heiss-Medical",
    "Hermann",
    "HGR",
    "Holger",
    "ILG",
    "Josef Betzler",
    "KAPP",
    "Kohler",
    "Medin",
    "Microqore",
    "Otto Ruttgers",
    "Phoenix Instruments",
    "Precision Medical",
    "Rebstock",
    "Rica",
    "Rudischhauser",
    "Rudolf Storz",
    "Ruhof",
    "S.u.A. Martin",
    "Schmid",
    "SGS North America",
    "SIBEL",
    "Siema",
    "SignTech",
    "SIS",
    "Sitec",
    "SMT",
    "Stengelin",
    "Steris",
    "Stork",
    "Tontarra",
    "Total Titanium",
    "Vinzenz Sattler",
    "Vollrath",
    "WEBA",
    "Y&W"



]
selected_vendor = st.selectbox("Select Vendor", vendor_options)

# Multiple file uploader
uploaded_files = st.file_uploader("Upload PDF Invoice(s)", type="pdf", accept_multiple_files=True)


if uploaded_files:
    st.write(f"Uploaded {len(uploaded_files)} file(s)")

    # Process button
    if st.button("Process Invoices"):
        try:
            with st.spinner('Processing invoices...'):
                # Extract data based on selected vendor
                extracted_data = process_pdfs(uploaded_files, selected_vendor)

                if extracted_data:
                    # Display extracted data
                    df = pd.DataFrame(extracted_data)

                    # Show success message
                    st.success(f"Successfully extracted data from {len(uploaded_files)} invoice(s)")

                    # Display preview
                    st.subheader("Extracted Data Preview")
                    st.dataframe(df)

                    # Download button for CSV
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name="extracted_invoice_data.csv",
                        mime="text/csv"
                    )

                    # Show summary
                    st.subheader("Extraction Summary")
                    st.write(f"Total items extracted: {len(extracted_data)}")
                    st.write(f"Total invoices processed: {len(uploaded_files)}")

                    # Show items per invoice with page numbers - WITH ERROR HANDLING
                    st.write("Items per Invoice:")
                    for invoice_num in df['invoice_number'].unique():
                        invoice_data = df[df['invoice_number'] == invoice_num]
                        num_items = len(invoice_data)
                        
                        st.write(f"Invoice {invoice_num}:")
                        st.write(f"  - Total items: {num_items}")
                        
                        # Handle page information - check if column exists
                        if 'page_number' in invoice_data.columns:
                            pages = invoice_data['page_number'].unique()
                            st.write(f"  - Pages with items: {sorted(pages)}")
                        elif 'page' in invoice_data.columns:
                            pages = invoice_data['page'].unique()
                            st.write(f"  - Pages with items: {sorted(pages)}")
                        else:
                            st.write(f"  - Page information: Not available")
                            
                        # Show PO number if available
                        if 'po_number' in invoice_data.columns and not invoice_data['po_number'].isnull().all():
                            po_numbers = invoice_data['po_number'].unique()
                            if len(po_numbers) > 0:
                                st.write(f"  - PO Numbers: {', '.join(map(str, po_numbers))}")
                        
                        # Show order number if available
                        if 'order_number' in invoice_data.columns and not invoice_data['order_number'].isnull().all():
                            order_numbers = invoice_data['order_number'].unique()
                            if len(order_numbers) > 0:
                                st.write(f"  - Order Numbers: {', '.join(map(str, order_numbers))}")
                        
                        st.write("")  # Empty line for spacing

                else:
                    st.warning("No data could be extracted from the invoice(s).")

        except Exception as e:
            st.error(f"Error processing invoice(s): {str(e)}")
            st.text("Full error:")
            st.exception(e)

# Instructions
st.sidebar.header("Instructions")
st.sidebar.write("""
1. Select the vendor from the dropdown menu
2. Upload one or more PDF invoices
3. Click 'Process Invoices' button
4. Review extracted data
5. Download CSV file

Note: The tool can handle:
- Multiple invoices
- Multi-page invoices
- Multiple items per invoice
""")

# Display supported vendors
# st.sidebar.header("Supported Vendors")
# st.sidebar.write("""
# Currently supported vendors:
# - Bumüller GmbH
# - Avalign German Specialty Instruments
# - A. Milazzo Medizintechnik GmbH
# """)

# Debug section (collapsible)
with st.expander("Debug Information"):
    if uploaded_files:
        for i, file in enumerate(uploaded_files):
            st.subheader(f"File {i + 1}: {file.name}")
            with pdfplumber.open(file) as pdf:
                for page_num in range(len(pdf.pages)):
                    st.text(f"\nPage {page_num + 1}:")
                    st.text(pdf.pages[page_num].extract_text())