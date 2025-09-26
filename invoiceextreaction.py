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


#Josef Betzler
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
            
            # Find item records
            item_blocks = []
            current_block = []
            in_record = False
            in_items_section = False
            found_first_orderconfirmation = False
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                
                # Look for the start of the items section
                if re.search(r'Pos\s+Article\s+Description\s+Quantity\s+Price', line_clean, re.IGNORECASE):
                    in_items_section = True
                    continue
                
                if not in_items_section:
                    continue
                
                # Skip header lines and "carried over" lines
                if (re.search(r'Pos\s+Article|carried over|to be carried over', line_clean, re.IGNORECASE) or
                    line_clean == 'EUR'):
                    continue
                
                # Skip ONLY the very first Orderconfirmation line (header)
                if re.match(r'^\d+\s+Orderconfirmation', line_clean) and not found_first_orderconfirmation:
                    found_first_orderconfirmation = True
                    continue
                
                # Look for record start: "your Ref.:"
                if re.search(r'your Ref\.:', line_clean, re.IGNORECASE):
                    if current_block and in_record:
                        item_blocks.append((current_block, invoice_data.copy()))
                    current_block = [line_clean]
                    in_record = True
                
                # Continue collecting lines if we're in a record
                elif in_record and current_block:
                    # Stop if we hit summary lines
                    if re.search(r'Value of goods|Packing|Energy|total EUR|payment:', line_clean, re.IGNORECASE):
                        item_blocks.append((current_block, invoice_data.copy()))
                        current_block = []
                        in_record = False
                    else:
                        current_block.append(line_clean)
            
            if current_block and in_record:
                item_blocks.append((current_block, invoice_data.copy()))
            
            # Process each item block
            for block, inv_data in item_blocks:
                item_data = _parse_josef_betzler_item_block(block, inv_data, page_num)
                if item_data:
                    extracted_data.append(item_data)
    
    return extracted_data

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

def _parse_josef_betzler_item_block(block: List[str], invoice_data: Dict, page_num: int) -> Optional[Dict]:
    """Parse an individual item block from Josef Betzler invoice"""
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
    
    # Extract customer reference from first line
    first_line = block[0].strip()
    customer_ref_match = re.search(r'your Ref\.:\s*([^\s]+)', first_line, re.IGNORECASE)
    customer_ref = customer_ref_match.group(1) if customer_ref_match else None
    
    # Find the item line (contains JB- code)
    item_line = None
    for line in block:
        if 'JB-' in line:
            item_line = line.strip()
            break
    
    if not item_line:
        return None
    
    # Parse the item line: "4 JB-5010-01 Heiss Wound Spreader shrp, 4x4 5 35,31 176,55"
    item_match = re.search(r'(\d+)\s+(JB-\d+-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+([\d,]+)$', item_line)
    
    if item_match:
        item_data['item_code'] = item_match.group(2)
        item_data['description'] = item_match.group(3).strip()
        item_data['quantity'] = item_match.group(4)
        item_data['unit_price'] = item_match.group(5).replace(',', '.')
    
    # Extract metadata from the entire block
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
        
        # Quantity from Charge line (more reliable)
        qty_match = re.search(r'Quantity:\s*(\d+)', line, re.IGNORECASE)
        if qty_match:
            item_data['quantity'] = qty_match.group(1)
    
    # Add customer reference to description if found
    if customer_ref and item_data['description']:
        item_data['description'] = f"{customer_ref} - {item_data['description']}"
    
    # Extract order information from the "Your order" line that ends this record
    for line in block:
        order_match = re.search(r'Your order\s+([^\s]+)\s+dtd\.\s+(\d{2}\.\d{2}\.\d{4})', line, re.IGNORECASE)
        if order_match:
            item_data['order_no'] = order_match.group(1)
            item_data['order_date'] = order_match.group(2)
            break
    
    # Only return if we have essential data
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