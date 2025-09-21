import streamlit as st
import pandas as pd
import pdfplumber
import re
from typing import Dict, List, Optional
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