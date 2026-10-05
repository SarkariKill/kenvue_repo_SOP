import io
import logging
import re
import uuid
from typing import Any, Dict, List, Tuple
import pymupdf  # PyMuPDF for fast, exact PDF parsing

from minio_storage import minio_storage

logger = logging.getLogger(__name__)

# =====================================================================
# HERE PDF EXTRACTION HAPPENS
# Extracts text, embedded raster images (as-is), vector diagrams/figures
# (as-is visual crops), and tables (both data and visual crops as-is)
# from the uploaded SOP PDF document.
# All images, figures, and tables are immediately stored in MinIO.
# =====================================================================


def extract_sop_pdf(
    file_bytes: bytes, conversation_id: str, filename: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Extracts text, images, vector figures, and tables from a PDF document.

    Args:
        file_bytes: Raw bytes of the uploaded PDF.
        conversation_id: Unique chat conversation ID.
        filename: Name of the uploaded SOP PDF file.

    Returns:
        (pages_data, artifacts_data, summary_stats)
    """
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    total_pages = len(doc)
    
    pages_data: List[Dict[str, Any]] = []
    artifacts_data: List[Dict[str, Any]] = []

    caption_re = re.compile(
        r"^(figure|fig\.|diagram|illustration|schematic|flowchart|process\s+flow)\s*(\d+|[a-z])?[:\.\-–\s]",
        re.IGNORECASE,
    )

    logger.info("Starting PDF extraction for '%s' (%d pages)", filename, total_pages)

    for page_num in range(1, total_pages + 1):
        page = doc[page_num - 1]
        
        # -------------------------------------------------------------
        # 1. EXTRACT TEXT FROM PAGE
        # -------------------------------------------------------------
        page_text = page.get_text("text").strip()
        pages_data.append({
            "page": page_num,
            "text": page_text,
        })

        # Pre-scan tables on this page to prevent overlap
        try:
            detected_tables = list(page.find_tables())
            table_bboxes = [pymupdf.Rect(t.bbox) for t in detected_tables]
        except Exception:
            detected_tables = []
            table_bboxes = []

        extracted_bboxes: List[pymupdf.Rect] = []
        drawings = page.get_drawings()
        blocks = page.get_text("blocks")
        fig_counter = 1

        # -------------------------------------------------------------
        # 2. EXTRACT IMAGES AS-IS (RASTER BITMAPS & VECTOR FIGURES)
        # -------------------------------------------------------------
        # 2A. Embedded Raster Images (PNG, JPEG XObjects)
        image_list = page.get_images(full=True)
        for img_idx, img_info in enumerate(image_list, start=1):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image.get("image")
                image_ext = base_image.get("ext", "png").lower()
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # Filter out microscopic 1x1 tracking pixels (< 20x20 px or empty)
                if width < 20 or height < 20 or len(image_bytes) < 50:
                    continue

                artifact_id = f"img_{uuid.uuid4().hex[:8]}"
                object_name = f"images/{conversation_id}/page_{page_num}_img_{img_idx}.{image_ext}"
                content_type = f"image/{'jpeg' if image_ext in ('jpg', 'jpeg') else 'png'}"

                caption = f"Figure on Page {page_num}"
                first_line = (page_text.split("\n")[0][:80] if page_text else "").strip()
                if first_line:
                    caption += f" ({first_line})"

                uploaded = minio_storage.upload_file_bytes(
                    object_name=object_name,
                    data=image_bytes,
                    content_type=content_type,
                    metadata={"conversation_id": conversation_id, "page": str(page_num), "type": "image"},
                )

                if uploaded:
                    artifacts_data.append({
                        "id": artifact_id,
                        "conversation_id": conversation_id,
                        "artifact_type": "image",
                        "object_name": object_name,
                        "caption": caption,
                        "page": page_num,
                        "table_markdown": None,
                        "width": width,
                        "height": height,
                    })
                    for r in page.get_image_rects(xref):
                        extracted_bboxes.append(r)
            except Exception as e:
                logger.warning("Could not extract raster image %d on page %d: %s", img_idx, page_num, e)

        # 2B. Vector Figures & Diagrams with Captions (Flowcharts, schematics, illustrations)
        for b in blocks:
            text = b[4].strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue
            first_line = lines[0]
            if caption_re.match(first_line):
                c_rect = pymupdf.Rect(b[:4])
                caption_text = first_line[:120]

                # Look for candidate drawing frame/cluster above caption
                cand = [
                    d["rect"]
                    for d in drawings
                    if (c_rect.y0 - 450) <= d["rect"].y0
                    and d["rect"].y1 <= (c_rect.y0 + 15)
                    and d["rect"].width > 80
                    and d["rect"].height > 40
                ]
                fig_rect = None
                if cand:
                    fig_rect = max(cand, key=lambda r: (r.width * r.height))
                else:
                    # Fallback vertical zone above caption
                    prev_y1 = 45.0
                    for pb in blocks:
                        pr = pymupdf.Rect(pb[:4])
                        if pr.y1 <= c_rect.y0 - 20 and pr.y1 > prev_y1:
                            if not caption_re.match(pb[4].strip()):
                                prev_y1 = max(prev_y1, pr.y1)
                    if (c_rect.y0 - prev_y1) > 50:
                        fig_rect = pymupdf.Rect(50, prev_y1 + 5, page.rect.width - 50, c_rect.y0 - 5)

                if fig_rect:
                    is_dup_table = any(
                        fig_rect.intersects(tb) and fig_rect.intersect(tb).get_area() > 0.4 * tb.get_area()
                        for tb in table_bboxes
                    )
                    is_dup_img = any(
                        fig_rect.intersects(eb) and fig_rect.intersect(eb).get_area() > 0.6 * fig_rect.get_area()
                        for eb in extracted_bboxes
                    )
                    if not is_dup_table and not is_dup_img:
                        try:
                            pix = page.get_pixmap(clip=fig_rect, dpi=150)
                            img_bytes = pix.tobytes("png")
                            artifact_id = f"img_{uuid.uuid4().hex[:8]}"
                            object_name = f"images/{conversation_id}/page_{page_num}_fig_{fig_counter}.png"
                            fig_counter += 1

                            uploaded = minio_storage.upload_file_bytes(
                                object_name=object_name,
                                data=img_bytes,
                                content_type="image/png",
                                metadata={"conversation_id": conversation_id, "page": str(page_num), "type": "figure"},
                            )
                            if uploaded:
                                artifacts_data.append({
                                    "id": artifact_id,
                                    "conversation_id": conversation_id,
                                    "artifact_type": "image",
                                    "object_name": object_name,
                                    "caption": caption_text,
                                    "page": page_num,
                                    "table_markdown": None,
                                    "width": pix.width,
                                    "height": pix.height,
                                })
                                extracted_bboxes.append(fig_rect)
                        except Exception as e:
                            logger.warning("Could not render vector figure on page %d: %s", page_num, e)

        # 2C. Standalone Graphic Diagram Clusters (Diagrams without explicit caption)
        for d in drawings:
            dr = d["rect"]
            if dr.width > 120 and dr.height > 80 and dr.y0 > 50 and dr.y1 < page.rect.height - 50:
                subs = [sub["rect"] for sub in drawings if dr.contains(sub["rect"]) and sub["rect"] != dr]
                if len(subs) >= 5:
                    is_dup_table = any(
                        dr.intersects(tb) and dr.intersect(tb).get_area() > 0.4 * tb.get_area()
                        for tb in table_bboxes
                    )
                    is_dup_img = any(
                        dr.intersects(eb) and dr.intersect(eb).get_area() > 0.6 * dr.get_area()
                        for eb in extracted_bboxes
                    )
                    if not is_dup_table and not is_dup_img:
                        try:
                            pix = page.get_pixmap(clip=dr, dpi=150)
                            img_bytes = pix.tobytes("png")
                            artifact_id = f"img_{uuid.uuid4().hex[:8]}"
                            object_name = f"images/{conversation_id}/page_{page_num}_diag_{fig_counter}.png"
                            fig_counter += 1

                            uploaded = minio_storage.upload_file_bytes(
                                object_name=object_name,
                                data=img_bytes,
                                content_type="image/png",
                                metadata={"conversation_id": conversation_id, "page": str(page_num), "type": "diagram"},
                            )
                            if uploaded:
                                artifacts_data.append({
                                    "id": artifact_id,
                                    "conversation_id": conversation_id,
                                    "artifact_type": "image",
                                    "object_name": object_name,
                                    "caption": f"Process Diagram (Page {page_num})",
                                    "page": page_num,
                                    "table_markdown": None,
                                    "width": pix.width,
                                    "height": pix.height,
                                })
                                extracted_bboxes.append(dr)
                        except Exception as e:
                            logger.warning("Could not render diagram cluster on page %d: %s", page_num, e)

        # -------------------------------------------------------------
        # 3. EXTRACT TABLES AS-IS FROM PDF & STORE IN MINIO
        # -------------------------------------------------------------
        try:
            # PyMuPDF built-in table finder
            tables = page.find_tables()
            for tbl_idx, table in enumerate(tables, start=1):
                try:
                    # Extract structured table markdown
                    tbl_markdown = table.to_markdown().strip()
                    if not tbl_markdown:
                        continue

                    # Extract visual crop of the table as-is from the page rendering
                    bbox = table.bbox  # (x0, y0, x1, y1)
                    # Render the clipped region with high clarity (DPI=150)
                    pix = page.get_pixmap(clip=bbox, dpi=150)
                    table_img_bytes = pix.tobytes("png")

                    artifact_id = f"tbl_{uuid.uuid4().hex[:8]}"
                    object_name = f"tables/{conversation_id}/page_{page_num}_tbl_{tbl_idx}.png"

                    # Generate table caption from headers or first row
                    header_row = tbl_markdown.split("\n")[0].replace("|", " ").strip()[:80]
                    caption = f"Table on Page {page_num}: {header_row}" if header_row else f"Table on Page {page_num}"

                    # --- HERE MINIO STORAGE FOR TABLES HAPPENS ---
                    uploaded = minio_storage.upload_file_bytes(
                        object_name=object_name,
                        data=table_img_bytes,
                        content_type="image/png",
                        metadata={"conversation_id": conversation_id, "page": str(page_num), "type": "table"},
                    )

                    if uploaded:
                        artifacts_data.append({
                            "id": artifact_id,
                            "conversation_id": conversation_id,
                            "artifact_type": "table",
                            "object_name": object_name,
                            "caption": caption,
                            "page": page_num,
                            "table_markdown": tbl_markdown,
                            "width": pix.width,
                            "height": pix.height,
                        })
                except Exception as e:
                    logger.warning("Failed processing table %d on page %d: %s", tbl_idx, page_num, e)
        except Exception as e:
            logger.warning("Table extraction error on page %d: %s", page_num, e)

    doc.close()

    summary_stats = {
        "filename": filename,
        "page_count": total_pages,
        "images_extracted": len([a for a in artifacts_data if a["artifact_type"] == "image"]),
        "tables_extracted": len([a for a in artifacts_data if a["artifact_type"] == "table"]),
    }
    logger.info("PDF extraction completed: %s", summary_stats)
    return pages_data, artifacts_data, summary_stats
