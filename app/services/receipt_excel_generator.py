from io import BytesIO
from typing import List, Optional

import pandas as pd
from openpyxl.styles import Font

from app.schemas.receipt import ReceiptItem


def generate_receipt_excel(
    items: List[ReceiptItem],
    market_name: Optional[str] = None,
    purchase_date: Optional[str] = None
) -> BytesIO:
    data = []
    for item in items:
        data.append({
            "Market": market_name or "",
            "Purchase Date": purchase_date or "",
            "Item": item.item,
            "Quantity": item.quantidade,
            "Unit Value": item.valor_unitario,
            "Total Value": item.valor_total,
            "Discount": item.desconto
        })

    df = pd.DataFrame(data, columns=[
        "Market", "Purchase Date", "Item", "Quantity", "Unit Value", "Total Value", "Discount"
    ])

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Receipt Items", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Receipt Items"]

        header_font = Font(bold=True)
        for cell in worksheet[1]:
            cell.font = header_font

        for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row, min_col=5, max_col=7):
            for cell in row:
                cell.number_format = 'R$ #,##0.00'

        for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row, min_col=4, max_col=4):
            for cell in row:
                cell.number_format = '0.00'

        column_widths = {
            "A": 25,
            "B": 14,
            "C": 40,
            "D": 10,
            "E": 12,
            "F": 12,
            "G": 10
        }

        for col_letter, width in column_widths.items():
            worksheet.column_dimensions[col_letter].width = width

    output.seek(0)
    return output
